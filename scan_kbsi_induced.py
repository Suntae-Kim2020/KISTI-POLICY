#!/usr/bin/env python3
"""
KBSI 유발논문 스캐너 — WoS 원시 TXT에서 FU/FX 필드에 KBSI 키워드가 있는 논문을 추출한다.
출력: /Users/kimsuntae/KISTEP/kbsi_induced_papers.json (kisti_induced_papers.json과 동일 포맷)
1회성 실행 (~3-5분)
"""
import json
import os
import re
import sys
from pathlib import Path

BASE = Path("/Users/kimsuntae/KISTEP/수집데이터(논문)")
OUT = Path("/Users/kimsuntae/KISTEP/kbsi_induced_papers.json")

# KBSI 키워드 (대소문자 무관)
KBSI_PATTERNS = [
    re.compile(r'\bKBSI\b', re.IGNORECASE),
    re.compile(r'Korea\s+Basic\s+Science\s+Inst', re.IGNORECASE),
]


def find_txt_files():
    """SCIE/SSCI/AHCI TXT 파일 경로를 수집한다."""
    txt_files = []

    # SCIE: 연도별 하위 폴더 구조 (WoS-SCIE-2008/TXT/*.txt 또는 WoS-SCIE-2024/*.txt)
    scie_dir = BASE / "SCIE"
    if scie_dir.exists():
        for year_dir in sorted(scie_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            # 직접 .txt 파일
            for f in year_dir.glob("*.txt"):
                txt_files.append(("SCIE", f))
            # TXT 하위 폴더
            txt_sub = year_dir / "TXT"
            if txt_sub.exists():
                for f in txt_sub.glob("*.txt"):
                    txt_files.append(("SCIE", f))

    # SSCI
    ssci_dir = BASE / "SSCI-ALL-TXT"
    if ssci_dir.exists():
        for f in sorted(ssci_dir.glob("*.txt")):
            txt_files.append(("SSCI", f))

    # AHCI
    ahci_dir = BASE / "AHCI-ALL-TXT"
    if ahci_dir.exists():
        for f in sorted(ahci_dir.glob("*.txt")):
            txt_files.append(("AHCI", f))

    return txt_files


def extract_kbsi_keywords(text):
    """텍스트에서 매칭된 KBSI 키워드 목록을 반환한다."""
    matched = []
    for pat in KBSI_PATTERNS:
        for m in pat.finditer(text):
            kw = m.group(0).strip()
            if kw.upper() not in [k.upper() for k in matched]:
                matched.append(kw)
    return matched


def parse_tab_delimited(filepath, db):
    """탭 구분 WoS TXT 파일을 파싱하여 KBSI 유발논문을 추출한다."""
    results = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            header_line = f.readline().strip()
            if not header_line:
                return results
            headers = header_line.split("\t")

            # 필요한 컬럼 인덱스 찾기
            col_idx = {}
            for col in ["UT", "PY", "SO", "TI", "WC", "TC", "FU", "FX", "DT"]:
                if col in headers:
                    col_idx[col] = headers.index(col)

            if "FU" not in col_idx and "FX" not in col_idx:
                return results

            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                fields = line.split("\t")

                # FU/FX 필드 추출
                fu = fields[col_idx["FU"]] if "FU" in col_idx and col_idx["FU"] < len(fields) else ""
                fx = fields[col_idx["FX"]] if "FX" in col_idx and col_idx["FX"] < len(fields) else ""

                combined = fu + " " + fx
                if not combined.strip():
                    continue

                keywords = extract_kbsi_keywords(combined)
                if not keywords:
                    continue

                # Early Access 제외
                dt = fields[col_idx.get("DT", -1)] if "DT" in col_idx and col_idx["DT"] < len(fields) else ""
                if "Early Access" in dt:
                    continue

                ut = fields[col_idx.get("UT", -1)] if "UT" in col_idx and col_idx["UT"] < len(fields) else ""
                if not ut:
                    continue

                try:
                    py = int(fields[col_idx["PY"]]) if "PY" in col_idx and col_idx["PY"] < len(fields) else 0
                except ValueError:
                    py = 0

                try:
                    tc = int(fields[col_idx["TC"]]) if "TC" in col_idx and col_idx["TC"] < len(fields) else 0
                except ValueError:
                    tc = 0

                results.append({
                    "UT": ut,
                    "PY": py,
                    "SO": fields[col_idx.get("SO", -1)] if "SO" in col_idx and col_idx["SO"] < len(fields) else "",
                    "TI": fields[col_idx.get("TI", -1)] if "TI" in col_idx and col_idx["TI"] < len(fields) else "",
                    "WC": fields[col_idx.get("WC", -1)] if "WC" in col_idx and col_idx["WC"] < len(fields) else "",
                    "TC": tc,
                    "db": db,
                    "keywords": keywords,
                    "FU": fu,
                    "FX": fx,
                })

    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")

    return results


def main():
    print("KBSI 유발논문 스캐너")
    print("=" * 60)

    txt_files = find_txt_files()
    print(f"TXT 파일 수: {len(txt_files)}")

    all_papers = {}  # UT -> record (중복 제거)
    file_count = 0

    for db, filepath in txt_files:
        file_count += 1
        papers = parse_tab_delimited(filepath, db)
        for p in papers:
            ut = p["UT"]
            if ut not in all_papers:
                all_papers[ut] = p
            else:
                # 기존 키워드와 합치기
                existing_kws = set(k.upper() for k in all_papers[ut]["keywords"])
                for kw in p["keywords"]:
                    if kw.upper() not in existing_kws:
                        all_papers[ut]["keywords"].append(kw)
        if file_count % 50 == 0:
            print(f"  {file_count}/{len(txt_files)} 파일 처리... ({len(all_papers):,}건)")

    results = sorted(all_papers.values(), key=lambda x: (x["PY"], x["UT"]))

    print(f"\n총 KBSI 유발논문: {len(results):,}건")

    # DB별 통계
    db_counts = {}
    for p in results:
        db_counts[p["db"]] = db_counts.get(p["db"], 0) + 1
    for db, cnt in sorted(db_counts.items()):
        print(f"  {db}: {cnt:,}건")

    # 연도별 통계
    year_counts = {}
    for p in results:
        year_counts[p["PY"]] = year_counts.get(p["PY"], 0) + 1
    for y in sorted(year_counts.keys()):
        print(f"  {y}: {year_counts[y]:,}건")

    # 키워드별 통계
    kw_counts = {}
    for p in results:
        for kw in p["keywords"]:
            kw_upper = kw.upper()
            kw_counts[kw_upper] = kw_counts.get(kw_upper, 0) + 1
    print("\n키워드별 매칭:")
    for kw, cnt in sorted(kw_counts.items(), key=lambda x: -x[1]):
        print(f"  {kw}: {cnt:,}건")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n출력: {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
