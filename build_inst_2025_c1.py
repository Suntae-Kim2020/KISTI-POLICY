#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2025년 논문×기관 연결(inst_data) 복원 스크립트.

배경: KISTEP의 기관명데이터.xlsx(Clarivate 기관 export)는 2025년 논문을 ~11%만
포함(20,982행). 나머지 2025 기관 연결 xlsx는 더 이상 수집되지 않음. 그러나 WoS 논문
데이터(wos_data.pkl)의 C1(저자주소) 필드에는 2025년 전체 기관 주소가 들어있음.

전략: 2025년 논문의 C1을 파싱하여 "South Korea" 주소의 기관을 추출하고,
  (1) 기존 inst_data에서 학습한 org->org_alias 사전,
  (2) institution_mappings.json(관리도구 수동 이명매핑)
으로 정규화하여 inst_data 행을 복원한다. 기존 행은 보존하고 (UT, org_alias) 기준
UNION(추가만) 한다.

입력(KISTEP):
  generated/master/wos_institutions.pkl   기존 inst_data (2011~2024 + 2025 부분)
  generated/2025/wos_data.pkl             WoS 논문 (C1, PY)
  generated/master/institution_mappings.json  관리도구 수동 이명매핑

출력(KISTEP):
  generated/2025/wos_institutions.pkl     기존 + 2025 복원 (compute.py가 master보다
                                          우선 인식하는 버전 슬롯)

검증(프로토타입): KISTI 8->153, KBSI 55->429, IBS 91->1058 (평년 추세 부합).
"""
import argparse
import json
import pickle
import re
import time
from pathlib import Path
from collections import Counter, defaultdict

# 검증용 대상 기관 org_alias
TARGETS = {
    "KOREA INST SCI & TECHNOL INFORMAT": "KISTI",
    "KOREA BASIC SCI INST": "KBSI",
    "INST BASIC SCI KOREA": "IBS",
}

BRACKET = re.compile(r"\[([^\]]*)\]\s*([^\[]*)")


def parse_sk_orgs(c1):
    """C1(저자주소) → South Korea 주소 블록의 기관명 리스트.

    WoS C1 형식: '[저자1; 저자2] 기관, [부서,] 도시, 국가; [저자3] 기관2, ...'
    대괄호 안 저자도 ';'로 구분되므로 대괄호 구조를 존중해 파싱한다.
    한 저자그룹이 복수 주소를 가지면(';'로 이어짐) 각각 처리한다.
    """
    if not c1:
        return []
    out = []
    matches = BRACKET.findall(c1)
    blocks = [addr for _auth, addr in matches] if matches else [c1]
    for addr in blocks:
        for sub in addr.split(";"):
            sub = sub.strip()
            if not sub:
                continue
            if sub.lower().rstrip(". ").endswith("south korea"):
                org = sub.split(",")[0].strip()
                if org:
                    out.append(org)
    return out


def main(year, version, base):
    t0 = time.time()
    base = Path(base)
    inst_in = base / "generated" / "master" / "wos_institutions.pkl"
    wos_in = base / "generated" / version / "wos_data.pkl"
    mappings = base / "generated" / "master" / "institution_mappings.json"
    inst_out = base / "generated" / version / "wos_institutions.pkl"
    print(f"=== 대상: {year}년 (version={version}) ===")
    print(f"  inst_in : {inst_in}")
    print(f"  wos_in  : {wos_in}")
    print(f"  out     : {inst_out}")
    print("=== 1) 기존 inst_data 로딩 ===")
    inst = pickle.load(open(inst_in, "rb"))
    print(f"  기존 행: {len(inst):,}")

    # org(대문자) -> org_alias (다수결), org_alias -> 속성
    org2alias_c = defaultdict(Counter)
    attr_by_alias = {}
    aliases = set()
    for r in inst:
        oa = r.get("org_alias", "")
        org = (r.get("org") or "").strip().upper()
        if oa:
            aliases.add(oa)
        if org and oa:
            org2alias_c[org][oa] += 1
        if oa and oa not in attr_by_alias:
            attr_by_alias[oa] = {
                "institution_type": r.get("institution_type", "") or "",
                "institution_type_7": r.get("institution_type_7", "기타") or "기타",
            }
    org2alias = {k: v.most_common(1)[0][0] for k, v in org2alias_c.items()}
    alias_up = {a.upper(): a for a in aliases if a}
    print(f"  org->alias 사전: {len(org2alias):,} | 고유 alias: {len(aliases):,}")

    # === 2) institution_mappings.json 오버레이 (수동 이명매핑) ===
    map_added = 0
    if mappings.exists():
        um = json.loads(mappings.read_text(encoding="utf-8"))
        for entry in um.get("new_aliases", []) + um.get("variant_additions", []):
            org = (entry.get("org") or "").strip().upper()
            alias = (entry.get("alias") or "").strip()
            itype = (entry.get("type") or "기타").strip()
            if not (org and alias):
                continue
            org2alias.setdefault(org, alias)          # 기존 학습 매핑 우선
            alias_up.setdefault(alias.upper(), alias)
            # 매핑에만 있는 신규 alias는 type을 institution_type(_7)로 사용 (build_report와 동일)
            attr_by_alias.setdefault(alias, {"institution_type": itype,
                                             "institution_type_7": itype})
            map_added += 1
        print(f"  institution_mappings.json 오버레이: {map_added:,}건 ({mappings.name})")
    else:
        print(f"  [경고] {mappings} 없음 — 오버레이 생략")

    def lookup(org):
        ou = org.upper()
        if ou in org2alias:
            return org2alias[ou]
        if ou in alias_up:
            return alias_up[ou]
        return ou  # 미매칭 국내기관: 대문자 org를 alias로 폴백

    # === 3) 기존 대상연도 (UT, org_alias) 집합 (UNION 중복 방지) ===
    print("=== 3) wos_data 로딩 (C1/PY 추출) ===")
    wos = pickle.load(open(wos_in, "rb"))
    py_by_ut = {r["UT"]: r.get("PY") for r in wos if "UT" in r}
    c1_year = {r["UT"]: (r.get("C1") or "") for r in wos
               if r.get("PY") == year and "UT" in r}
    del wos
    print(f"  {year}년 논문: {len(c1_year):,}")

    existing_pairs = set()
    existing_rows = 0
    for r in inst:
        ut = r.get("UT", "")
        if py_by_ut.get(ut) == year:
            existing_rows += 1
            existing_pairs.add((ut, r.get("org_alias", "")))
    print(f"  기존 {year}년 행: {existing_rows:,}")

    # === 4) C1 복원 → 신규 행 생성 (UNION 추가) ===
    print(f"=== 4) {year}년 C1 복원 ===")
    new_rows = []
    seen_pairs = set(existing_pairs)
    matched = unmatched = 0
    for ut, c1 in c1_year.items():
        isi_loc = ut[4:] if ut.startswith("WOS:") else ut
        for org in parse_sk_orgs(c1):
            alias = lookup(org)
            key = (ut, alias)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            attr = attr_by_alias.get(alias)
            if attr:
                matched += 1
                itype = attr["institution_type"] or "기타"
                itype7 = attr["institution_type_7"] or "기타"
            else:
                unmatched += 1
                itype = "기타"
                itype7 = "기타"
            new_rows.append({
                "isi_loc": isi_loc,
                "position": 0,
                "org": org,
                "org_alias": alias,
                "others": "",
                "state": "",
                "zip_code": "",
                "description": itype,
                "decription2": itype,
                "UT": ut,
                "state_norm": "",
                "state_raw": "",
                "region_3": None,
                "region_6": None,
                "institution_type": itype,
                "institution_type_7": itype7,
            })
    print(f"  신규 행: {len(new_rows):,} (매칭 {matched:,} / 미매칭폴백 {unmatched:,})")

    # === 5) 검증 ===
    print(f"=== 5) {year}년 직접 소속 UT 검증 ===")
    combined_pairs_by_alias = defaultdict(set)
    for (ut, oa) in existing_pairs:
        combined_pairs_by_alias[oa].add(ut)
    for row in new_rows:
        combined_pairs_by_alias[row["org_alias"]].add(row["UT"])
    for oa, label in TARGETS.items():
        before = len({ut for (ut, a) in existing_pairs if a == oa})
        after = len(combined_pairs_by_alias[oa])
        print(f"  {label}: {before} -> {after}")

    # === 6) 저장 ===
    inst.extend(new_rows)
    print(f"=== 6) 저장: {inst_out} ({len(inst):,}행) ===")
    with open(inst_out, "wb") as f:
        pickle.dump(inst, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  완료. 총 소요 {time.time() - t0:.1f}초")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="WoS C1(저자주소)에서 특정 연도의 논문×기관 연결(inst_data) 복원")
    ap.add_argument("--year", type=int, default=2025,
                    help="복원 대상 연도 (기본: 2025)")
    ap.add_argument("--version", type=str, default=None,
                    help="generated/{version} 폴더명 (기본: year와 동일)")
    ap.add_argument("--base", type=str, default="/Users/kimsuntae/KISTEP",
                    help="KISTEP 루트 경로")
    args = ap.parse_args()
    main(args.year, args.version or str(args.year), args.base)
    main()
