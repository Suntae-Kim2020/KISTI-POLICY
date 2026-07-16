#!/usr/bin/env python3
"""HC 필드 기반 HCP 인덱스 재구축 — WoS 원시 TXT의 HC(ESI Highly Cited Status)='Y'를 스캔.

기존 방식(별도 ESI DocumentsExport xlsx, 2014-2024, 현행화 이전)을 대체.
HC 필드는 2011-2025 수집과 동기 → 2025년 HCP 포함, UT 매칭 누락 없음.
(단 ESI HCP 정의상 최근 10년 윈도우라 2011-2015는 HC=Y가 거의 없음 — 데이터 한계 아님)

- 입력(읽기전용): KISTEP/rawdata/report_2026/wos/{SCIE,SSCI,AHCI}, esi_journal_map.pkl
- 출력(프로젝트): KISTI_Policy/data_2025/hcp_index.json (기존 스키마 호환)
"""
import csv
import json
import pickle
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

csv.field_size_limit(10 * 1024 * 1024)

PROJECT = Path(__file__).resolve().parent
WOS = Path("/Users/kimsuntae/KISTEP/rawdata/report_2026/wos")
ESI_MAP = Path("/Users/kimsuntae/KISTEP/generated/master/esi_journal_map.pkl")
OUT = PROJECT / "data_2025" / "hcp_index.json"


def find_txt_files():
    files = []
    scie = WOS / "SCIE"
    if scie.exists():
        for yd in sorted(scie.iterdir()):
            if yd.is_dir():
                files += [("SCIE", f) for f in sorted(yd.glob("*.txt"))]
    for sub in ("SSCI", "AHCI"):
        d = WOS / sub
        if d.exists():
            files += [(sub, f) for f in sorted(d.glob("*.txt"))]
    return files


def main():
    esi = pickle.load(open(ESI_MAP, "rb")) if ESI_MAP.exists() else {}
    print(f"esi_map: {len(esi):,} ISSN")

    def field_of(sn, ei):
        for issn in (sn, ei):
            issn = (issn or "").strip()
            if issn and issn in esi:
                return esi[issn]
        return "UNKNOWN"

    files = find_txt_files()
    print(f"입력 TXT: {len(files):,}개")
    papers = {}
    for n, (db, fp) in enumerate(files, 1):
        try:
            with open(fp, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh, delimiter="\t"):
                    if (row.get("HC") or "").strip() != "Y":
                        continue
                    ut = (row.get("UT") or "").strip()
                    if not ut:
                        continue
                    try:
                        yr = int(row.get("PY"))
                    except (TypeError, ValueError):
                        yr = None
                    try:
                        tc = int(row.get("TC") or 0)
                    except ValueError:
                        tc = 0
                    papers[ut] = {
                        "year": yr,
                        "field": field_of(row.get("SN"), row.get("EI")),
                        "source": (row.get("SO") or "").strip(),
                        "tc": tc,
                        "db": db,
                        "doi": (row.get("DI") or "").strip(),
                        "title": (row.get("TI") or "").strip()[:300],
                    }
        except Exception as e:
            print(f"  ERROR {fp}: {e}", file=sys.stderr)
        if n % 200 == 0 or n == len(files):
            print(f"  {n}/{len(files)}  HCP={len(papers):,}", flush=True)

    by_year, by_field = {}, {}
    for p in papers.values():
        if p["year"]:
            by_year[p["year"]] = by_year.get(p["year"], 0) + 1
        by_field[p["field"]] = by_field.get(p["field"], 0) + 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "WoS HC field (ESI Highly Cited Status) — report_2026",
        "input_dir": str(WOS),
        "total": len(papers),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "by_year": {str(y): by_year[y] for y in sorted(by_year)},
        "by_field": dict(sorted(by_field.items(), key=lambda x: -x[1])),
        "papers": papers,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✅ {OUT} — HCP {len(papers):,}편")
    print("연도별:", {str(y): by_year[y] for y in sorted(by_year)})


if __name__ == "__main__":
    main()
