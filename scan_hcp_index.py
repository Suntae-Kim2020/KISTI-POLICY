#!/usr/bin/env python3
"""
KISTEP의 Clarivate HCP (Highly Cited Papers) 엑셀을 파싱하여
정책 인사이트 모듈에서 쓸 수 있는 JSON 인덱스를 생성한다.

입력:  /Users/kimsuntae/KISTEP/rawdata/hcp/1. DocumentsExport-HCP-WORLD-SC-SOUTH KOREA-7614건-자료정리.xlsx
출력:  /Users/kimsuntae/KISTEP/hcp_index.json

스키마:
{
  "source": "Clarivate HCP WORLD SC South Korea",
  "total": 7614,
  "generated_at": "...",
  "papers": {
    "WOS:000686117000001": {
      "year": 2021,
      "field": "BIOLOGY & BIOCHEMISTRY",
      "source": "NATURE 596 (7873): 583-+",
      "tc": 12635,
      "countries": "ENGLAND;SOUTH KOREA;",
      "doi": "10.1038/s41586-021-03819-2",
      "title": "HIGHLY ACCURATE PROTEIN STRUCTURE PREDICTION WITH ALPHAFOLD"
    },
    ...
  }
}
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

SRC = Path("/Users/kimsuntae/KISTEP/rawdata/hcp/1. DocumentsExport-HCP-WORLD-SC-SOUTH KOREA-7614건-자료정리.xlsx")
OUT = Path("/Users/kimsuntae/KISTEP/hcp_index.json")

SHEET = "논문(7614건)-정리"


def main():
    if not SRC.exists():
        print(f"❌ 입력 파일 없음: {SRC}")
        sys.exit(1)

    print(f"읽는 중: {SRC.name}")
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb[SHEET]

    # 컬럼 인덱스 (헤더 1행 스캔)
    # 주의: 엑셀에 "Publication Date", "Countries" 등 중복 헤더가 있어
    # 첫 번째 출현만 기록 (두번째는 집계용 보조 컬럼)
    col = {}
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    for i, h in enumerate(header):
        if h is None:
            continue
        key = str(h).strip()
        if key not in col:   # 첫 출현만 기록
            col[key] = i

    required = ["Accession Number", "DOI", "Article Name", "Source",
                "Research Field", "Times Cited", "Countries",
                "Publication Date"]
    missing = [k for k in required if k not in col]
    if missing:
        print(f"⚠️ 누락된 컬럼: {missing}")

    papers = {}
    skipped = 0
    for row in rows:
        try:
            ut = row[col["Accession Number"]]
            if not ut:
                skipped += 1
                continue
            ut = str(ut).strip()
            if not ut.startswith("WOS:"):
                # 일부는 WOS: 접두사 없을 수 있음
                ut = "WOS:" + ut.replace("WOS:", "")
            # 연도는 integer 또는 YYYY 형식 문자열
            yr = row[col["Publication Date"]]
            try:
                yr = int(yr)
            except (TypeError, ValueError):
                # 날짜 객체나 문자열일 수 있음
                m = re.search(r"(20\d{2})", str(yr)) if yr else None
                yr = int(m.group(1)) if m else None

            papers[ut] = {
                "year": yr,
                "field": (row[col["Research Field"]] or "").strip() if col.get("Research Field") is not None else "",
                "source": (row[col["Source"]] or "").strip() if col.get("Source") is not None else "",
                "tc": int(row[col["Times Cited"]]) if row[col["Times Cited"]] else 0,
                "countries": (row[col.get("Countries", 9)] or "").strip() if col.get("Countries") is not None else "",
                "doi": (row[col["DOI"]] or "").strip() if col.get("DOI") is not None else "",
                "title": (row[col["Article Name"]] or "").strip()[:300] if col.get("Article Name") is not None else "",
            }
        except Exception as e:
            skipped += 1
            continue

    # 통계
    by_year = {}
    by_field = {}
    for ut, p in papers.items():
        y = p.get("year")
        if y:
            by_year[y] = by_year.get(y, 0) + 1
        f = p.get("field") or "UNKNOWN"
        by_field[f] = by_field.get(f, 0) + 1

    output = {
        "source": "Clarivate HCP WORLD SC South Korea",
        "input_file": str(SRC),
        "total": len(papers),
        "skipped": skipped,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
        "by_field": dict(sorted(by_field.items(), key=lambda x: -x[1])),
        "papers": papers,
    }

    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 저장: {OUT}")
    print(f"   HCP 논문 {len(papers):,}편 (건너뜀 {skipped})")
    print(f"\n   연도별:")
    for y, n in sorted(by_year.items()):
        print(f"     {y}: {n:,}편")
    print(f"\n   분야별 Top 5:")
    for f, n in list(output["by_field"].items())[:5]:
        print(f"     {f}: {n}편")


if __name__ == "__main__":
    main()
