#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비교군(국내 일반논문 표본)의 OpenAlex 세계 상위 10%·1% 판정 + FWCI 수집.

논문1 확정안 (나)안: 세계 기준 로지스틱 회귀를 하려면 비교군 논문에도 논문별
상위 진입 판정값이 있어야 한다(무작위 기대치 10%와의 단순 비교로는 공변량 통제 불가).

대상: data_2025/oaid_control.json (무작위 10만 표본, UT→DOI 확보분)
      ※ 이 표본은 유발논문을 제외한 풀에서 추출되어 2×2의 ⓑ+ⓓ에 해당한다.
        ⓐ(내부 유발논문)는 fwci_index.json에 이미 수집되어 있으므로 분석 시 합류시킨다.
출력: data_2025/fwci_control_index.json  {UT: {fwci, top1, top10, cited_by, oa_year}}

한도: OpenAlex 무료 1,000요청/일(자정 UTC 리셋), 50건/요청 → 약 2,000요청(이틀).
      429를 만나면 체크포인트 저장 후 종료하며, 재실행하면 이어받는다.
실행: .venv/bin/python build_fwci_control.py
"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

OUT_DIR = Path("/home/user/KISTI_Policy/data_2025")
OUT_FILE = OUT_DIR / "fwci_control_index.json"
CKPT = OUT_DIR / ".fwci_control_rec.ckpt.json"
MAILTO = "kistiman@gmail.com"
BATCH = 50
SELECT = "doi,fwci,citation_normalized_percentile,cited_by_count,publication_year"


class BudgetExhausted(Exception):
    pass


def fetch(dois):
    q = urllib.parse.urlencode({
        "filter": "doi:" + "|".join(dois), "select": SELECT,
        "per_page": BATCH, "mailto": MAILTO,
    })
    req = urllib.request.Request(
        f"https://api.openalex.org/works?{q}",
        headers={"User-Agent": f"KISTI-Policy/1.0 (mailto:{MAILTO})"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["results"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise BudgetExhausted()      # 일일 예산 소진 → 리셋까지 재시도 무의미
            if attempt == 4:
                print(f"  배치 실패(HTTP {e.code}) — 건너뜀", file=sys.stderr)
                return None
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            if attempt == 4:
                print(f"  배치 실패({e}) — 건너뜀", file=sys.stderr)
                return None
            time.sleep(3 * (attempt + 1))
    return None


ctl = json.load(open(OUT_DIR / "oaid_control.json"))       # {UT: {doi, oaid}}
doi_uts = {}
for ut, v in ctl.items():
    d = (v.get("doi") or "").lower()
    if d:
        doi_uts.setdefault(d, []).append(ut)
print(f"비교군 대상 {len(ctl):,}편 / 고유 DOI {len(doi_uts):,}", flush=True)

rec = json.loads(CKPT.read_text()) if CKPT.exists() else {}
todo = [d for d in doi_uts if d not in rec]
print(f"기수집 {len(rec):,} / 남은 조회 {len(todo):,} (예상 {len(todo)//BATCH+1:,}요청)", flush=True)

stopped = False
try:
    for i in range(0, len(todo), BATCH):
        res = fetch(todo[i:i + BATCH])
        if res is not None:
            for w in res:
                d = (w.get("doi") or "").replace("https://doi.org/", "").lower()
                if d:
                    rec[d] = w
        else:
            for d in todo[i:i + BATCH]:
                rec.setdefault(d, None)      # 하드실패분은 재시도 대상에서 제외
        if (i // BATCH) % 25 == 0 or i + BATCH >= len(todo):
            CKPT.write_text(json.dumps(rec, ensure_ascii=False))
            print(f"  {min(i+BATCH,len(todo)):,}/{len(todo):,}  누적 {len(rec):,}", flush=True)
        time.sleep(0.2)
except BudgetExhausted:
    stopped = True
    print("  ※ OpenAlex 일일 예산 소진 — 체크포인트 저장 후 종료. 자정(UTC) 이후 재실행하면 이어받음.",
          flush=True)
CKPT.write_text(json.dumps(rec, ensure_ascii=False))

index = {}
for doi, uts in doi_uts.items():
    w = rec.get(doi)
    if not w:
        continue
    cnp = w.get("citation_normalized_percentile") or {}
    entry = {"fwci": w.get("fwci"),
             "top1": bool(cnp.get("is_in_top_1_percent")),
             "top10": bool(cnp.get("is_in_top_10_percent")),
             "cited_by": w.get("cited_by_count"),
             "oa_year": w.get("publication_year")}
    for ut in uts:
        index[ut] = entry
json.dump(index, open(OUT_FILE, "w"), ensure_ascii=False)
print(f"\n저장 {OUT_FILE}  ({len(index):,}편, 커버리지 {len(index)/len(ctl)*100:.1f}%)"
      + ("  [예산소진 중단 — 재실행 필요]" if stopped else "  [전량 완료]"), flush=True)
