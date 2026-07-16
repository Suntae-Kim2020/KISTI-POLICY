#!/usr/bin/env python3
"""
통합 유발논문 스캐너 (2026 현행화) — report_2026 원시 TXT를 1회 패스하며
KISTI / KBSI / IBS / PAL 4개 키워드 세트를 동시 적용해 유발논문 JSON 4종을 생성한다.

- 입력(읽기전용): KISTEP/rawdata/report_2026/wos/{SCIE,SSCI,AHCI}  (2011~2025)
- 출력(이 프로젝트): KISTI_Policy/data_2025/{kisti,kbsi,ibs,pal}_induced_papers.json
        (compute.py 가 프로젝트 로컬 → KISTEP 순으로 탐색하므로 우선 인식)
- 포맷: 기존 scan_*_induced.py 와 동일 (UT, PY, SO, TI, WC, TC, db, keywords, FU, FX)

KISTEP 폴더에는 일절 쓰지 않는다(원시 데이터는 입력으로만 사용).
기존 per-org 스캐너는 보존. KISTI 스캐너는 부재하여 본 통합본이 summary(by_keyword)
기준으로 KISTI 키워드를 재구성한다.
"""
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
WOS = Path("/Users/kimsuntae/KISTEP/rawdata/report_2026/wos")  # 입력(읽기전용)
OUT_DIR = PROJECT / "data_2025"                                # 출력(이 프로젝트)

# ── 키워드 세트 (대소문자 무관) ──
PATTERNS = {
    "KISTI": [
        re.compile(r'\bKISTI\b', re.I),
        re.compile(r'KSC-', re.I),
        re.compile(r'\bNURION\b', re.I),
        re.compile(r'\bKREONET\b', re.I),
        re.compile(r'\bEDISON\b', re.I),
        re.compile(r'\bPLSI\b', re.I),
        re.compile(r'\bKIAF\b', re.I),
        re.compile(r'\bGSDC\b', re.I),   # 글로벌 과학 데이터 허브(KISTI 고유 시설) — 탐지+직접 겸용
        re.compile(r'Korea\s+Institute\s+of\s+Science\s+and\s+Technology\s+Information', re.I),
    ],
    "KBSI": [
        re.compile(r'\bKBSI\b', re.I),
        re.compile(r'Korea\s+Basic\s+Science\s+Inst', re.I),
    ],
    "IBS": [
        re.compile(r'\bIBS\b', re.I),
        re.compile(r'Institute\s+for\s+Basic\s+Science', re.I),
        re.compile(r'\bRAON\b', re.I),   # IBS 중이온가속기(고유 시설) — 탐지+직접 겸용
    ],
    "PAL": [
        re.compile(r'Pohang\s+Accelerat', re.I),
        re.compile(r'Pohang\s+Light\s+Source', re.I),
        re.compile(r'PAL.XFEL', re.I),
        re.compile(r'PLS.?II', re.I),
    ],
}
OUT_FILE = {org: OUT_DIR / f"{org.lower()}_induced_papers.json" for org in PATTERNS}


def find_txt_files():
    """report_2026 구조: SCIE/WoS-SCIE-YYYY/*.txt, SSCI/*.txt, AHCI/*.txt"""
    files = []
    scie = WOS / "SCIE"
    if scie.exists():
        for yd in sorted(scie.iterdir()):
            if yd.is_dir():
                for f in sorted(yd.glob("*.txt")):
                    files.append(("SCIE", f))
    for sub in ("SSCI", "AHCI"):
        d = WOS / sub
        if d.exists():
            for f in sorted(d.glob("*.txt")):
                files.append((sub, f))
    return files


def match_keywords(text, pats):
    """매칭된 키워드(원문 그대로, 중복 제거) 목록 반환. 없으면 빈 리스트."""
    matched, seen = [], set()
    for pat in pats:
        for m in pat.finditer(text):
            kw = m.group(0).strip()
            if kw.upper() not in seen:
                seen.add(kw.upper())
                matched.append(kw)
    return matched


def parse_file(filepath, db, accum):
    """탭 구분 WoS TXT 1개 파싱 → 4개 키워드 세트 동시 매칭, accum[org][UT]에 누적."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            header_line = f.readline().rstrip("\n\r")
            if not header_line:
                return
            headers = header_line.split("\t")
            idx = {c: headers.index(c) for c in
                   ["UT", "PY", "SO", "TI", "WC", "TC", "FU", "FX", "DT"] if c in headers}
            if "FU" not in idx and "FX" not in idx:
                return

            def get(fields, col):
                i = idx.get(col, -1)
                return fields[i] if 0 <= i < len(fields) else ""

            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                fields = line.split("\t")
                fu, fx = get(fields, "FU"), get(fields, "FX")
                combined = (fu + " " + fx).strip()
                if not combined:
                    continue
                if "Early Access" in get(fields, "DT"):
                    continue
                ut = get(fields, "UT")
                if not ut:
                    continue

                hits = {}
                for org, pats in PATTERNS.items():
                    kws = match_keywords(combined, pats)
                    if kws:
                        hits[org] = kws
                if not hits:
                    continue

                try:
                    py = int(get(fields, "PY") or 0)
                except ValueError:
                    py = 0
                try:
                    tc = int(get(fields, "TC") or 0)
                except ValueError:
                    tc = 0

                for org, kws in hits.items():
                    bucket = accum[org]
                    if ut not in bucket:
                        bucket[ut] = {
                            "UT": ut, "PY": py,
                            "SO": get(fields, "SO"), "TI": get(fields, "TI"),
                            "WC": get(fields, "WC"), "TC": tc,
                            "db": db, "keywords": kws, "FU": fu, "FX": fx,
                        }
                    else:
                        existing = set(k.upper() for k in bucket[ut]["keywords"])
                        for kw in kws:
                            if kw.upper() not in existing:
                                bucket[ut]["keywords"].append(kw)
    except Exception as e:
        print(f"  ERROR {filepath}: {e}", file=sys.stderr)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = find_txt_files()
    print(f"입력 TXT: {len(files):,}개  (WOS={WOS})")
    if not files:
        print("입력 파일 없음 — 경로 확인 필요", file=sys.stderr)
        sys.exit(1)
    accum = {org: {} for org in PATTERNS}

    for n, (db, fp) in enumerate(files, 1):
        parse_file(fp, db, accum)
        if n % 100 == 0 or n == len(files):
            sizes = " ".join(f"{o}={len(accum[o]):,}" for o in PATTERNS)
            print(f"  {n}/{len(files)}  {sizes}", flush=True)

    summary = {}
    for org in PATTERNS:
        recs = sorted(accum[org].values(), key=lambda x: (x["PY"], x["UT"]))
        OUT_FILE[org].write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        by_year, by_db, by_kw = {}, {}, {}
        for r in recs:
            by_year[r["PY"]] = by_year.get(r["PY"], 0) + 1
            by_db[r["db"]] = by_db.get(r["db"], 0) + 1
            for kw in r["keywords"]:
                by_kw[kw.upper()] = by_kw.get(kw.upper(), 0) + 1
        summary[org] = {"total": len(recs), "by_db": by_db,
                        "by_year": {str(y): by_year[y] for y in sorted(by_year)},
                        "by_keyword": dict(sorted(by_kw.items(), key=lambda x: -x[1]))}
        print(f"\n=== {org}: {len(recs):,}건 → {OUT_FILE[org].name} ({OUT_FILE[org].stat().st_size/1024:.0f} KB) ===")
        print("  DB:", dict(sorted(by_db.items())))
        print("  연도:", {y: by_year[y] for y in sorted(by_year)})

    (OUT_DIR / "induced_summary_2026.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n요약 저장: {OUT_DIR/'induced_summary_2026.json'}")


if __name__ == "__main__":
    main()
