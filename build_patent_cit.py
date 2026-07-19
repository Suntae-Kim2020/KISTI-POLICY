#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lens Scholarly Aggregation API로 4기관 유발논문의 특허 인용(과학→기술 파급) 집계.

배경: 유발논문이 특허에 얼마나 인용됐는가(patent_citations)는 연구의 산업·기술적
파급을 보여주는 지표. Lens Patent API로는 NPL 인용 검색이 막혀 있으나(제약 참조),
Scholarly Aggregation API(/scholarly/aggregate)로 논문 DOI 집합에 대한
patent_citation_count 합계·평균과 '≥1 특허 인용' 편수를 집계할 수 있다.

- 입력: data_2025/.fwci_utdoi_cache.json (UT→DOI), data_2025/{org}_induced_papers.json
- API: POST /scholarly/aggregate (Bearer, .lens_token). 배치 1000 DOI, size:0.
       배치당 2요청: ①sum/avg/total ②range(pcc>=1)로 피인용 편수.
- 출력: data_2025/patent_cit_index.json (기관별 aggregate)
- 한도: ~1000 req/월, ~6 req/분 → 배치 간 대기. 전체 ~76 요청 예상.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJ = Path(__file__).resolve().parent
DATA = PROJ / "data_2025"
TOKEN = (PROJ / ".lens_token").read_text().strip()
OUT = DATA / "patent_cit_index.json"
API = "https://api.lens.org/scholarly/aggregate"
BATCH = 1000
SLEEP = 11        # 6 req/분 → 요청 간 11초
ORGS = ["kisti", "kbsi", "ibs", "pal"]


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {TOKEN}",
                                          "Content-Type": "application/json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 0)) or 65
                print(f"    429 — {wait}s 대기", flush=True)
                time.sleep(min(wait, 90))
                continue
            body_txt = e.read().decode()[:200]
            if attempt == 5:
                print(f"    FAIL {e.code}: {body_txt}", file=sys.stderr)
                return None
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            if attempt == 5:
                print(f"    FAIL: {e}", file=sys.stderr)
                return None
            time.sleep(5 * (attempt + 1))
    return None


def agg_batch(dois):
    """배치 집계 → (matched, pc_sum, cited)."""
    b1 = {"query": {"terms": {"doi": dois}}, "size": 0, "include": ["lens_id"],
          "aggregations": {"pc_sum": {"sum": {"field": "patent_citation_count"}}}}
    r1 = post(b1)
    if r1 is None:
        return None
    matched = r1.get("total") or 0
    pc_sum = (r1.get("aggregations") or {}).get("pc_sum") or 0
    time.sleep(SLEEP)
    b2 = {"query": {"bool": {"must": [{"terms": {"doi": dois}},
          {"range": {"patent_citation_count": {"gte": 1}}}]}}, "size": 0,
          "include": ["lens_id"]}
    r2 = post(b2)
    if r2 is None:
        return None
    cited = r2.get("total") or 0
    return matched, pc_sum, cited


def main():
    ud = json.loads((DATA / ".fwci_utdoi_cache.json").read_text())
    result = {}
    total_req = 0
    for org in ORGS:
        uts = {r["UT"] for r in json.loads((DATA / f"{org}_induced_papers.json").read_text())}
        dois = sorted({ud[u] for u in uts if u in ud})
        n_total = len(json.loads((DATA / f"{org}_induced_papers.json").read_text()))
        matched = pc_sum = cited = 0
        for i in range(0, len(dois), BATCH):
            batch = dois[i:i + BATCH]
            out = agg_batch(batch)
            total_req += 2
            if out is None:
                print(f"  {org.upper()} 배치 {i//BATCH+1} 실패 — 중단(부분저장)", file=sys.stderr)
                break
            m, s, c = out
            matched += m
            pc_sum += s
            cited += c
            print(f"  {org.upper()} 배치 {i//BATCH+1}/{(len(dois)-1)//BATCH+1}: "
                  f"matched {m}, 특허인용 {s}, ≥1편 {c}  (누적 req {total_req})", flush=True)
            time.sleep(SLEEP)
        result[org] = {
            "induced_total": n_total,
            "doi_queried": len(dois),
            "lens_matched": matched,
            "patent_citations": pc_sum,
            "papers_cited_by_patent": cited,
            "avg_patent_cit": round(pc_sum / matched, 3) if matched else None,
            "cited_rate_pct": round(cited / matched * 100, 1) if matched else None,
        }
        print(f"=== {org.upper()}: 특허인용 {pc_sum:,} / 매칭 {matched:,}편 / "
              f"≥1편 {cited:,}({result[org]['cited_rate_pct']}%) ===", flush=True)

    result["_meta"] = {"source": "Lens Scholarly Aggregation API (/scholarly/aggregate)",
                       "field": "patent_citation_count", "batch": BATCH,
                       "requests_used": total_req}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"\n저장: {OUT}  (총 {total_req} 요청)")


if __name__ == "__main__":
    main()
