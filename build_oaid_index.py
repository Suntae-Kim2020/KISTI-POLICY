#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본작업 1: 유발 전량 + 비유발 대조군 표본의 DOI→OpenAlex ID(oaid) 매핑.
paper A(과학→기술 파급, Reliance on Science 특허인용) 준비 단계.

절차:
  1) 원시 report_2026 TXT 1회 스캔 → 전체 UT→DOI (DI 필드)  [data_2025/ut_doi_all.json]
  2) 유발합집합 = 4개 *_induced_papers.json.  대조군풀 = 전체 − 유발.
  3) 대조군 N=100,000 무작위표본(seed=42).
  4) 유발+대조군 DOI를 OpenAlex works API로 oaid 매핑(50/req, polite, 체크포인트)
  5) 출력: data_2025/oaid_induced.json, data_2025/oaid_control.json
실행: KISTEP_BASE=/home/user/KISTEP /home/user/KISTI_Policy/.venv/bin/python build_oaid_index.py
"""
import os, sys, json, time, random, urllib.request, urllib.parse, urllib.error
from pathlib import Path

PROJECT = Path("/home/user/KISTI_Policy")
OUT = PROJECT / "data_2025"
RAW = Path(os.environ.get("KISTEP_BASE", "/home/user/KISTEP")) / "rawdata/report_2026/wos"
MAIL = "kistiman@gmail.com"
CONTROL_N = 100_000
SEED = 42
DOI_CACHE = OUT / ".oaid_doi_cache.json"     # {doi: oaid|""}  재개용

def log(m): print(m, flush=True)

def txt_files():
    fs = []
    scie = RAW / "SCIE"
    if scie.exists():
        for yd in sorted(scie.iterdir()):
            if yd.is_dir(): fs += sorted(yd.glob("*.txt"))
    for sub in ("SSCI", "AHCI"):
        d = RAW / sub
        if d.exists(): fs += sorted(d.glob("*.txt"))
    return fs

def build_ut_doi_all():
    cache = OUT / "ut_doi_all.json"
    if cache.exists():
        log(f"[1] ut_doi_all 캐시 사용")
        return json.load(open(cache))
    log("[1] 원시 TXT 스캔 → 전체 UT→DOI")
    ut_doi = {}
    files = txt_files()
    if not files:
        log(f"[오류] TXT 없음: {RAW}"); sys.exit(1)
    for n, fp in enumerate(files, 1):
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                hdr = f.readline().rstrip("\n\r").split("\t")
                if "UT" not in hdr or "DI" not in hdr: continue
                iu, idi = hdr.index("UT"), hdr.index("DI")
                for line in f:
                    cols = line.rstrip("\n\r").split("\t")
                    if iu >= len(cols): continue
                    ut = cols[iu]
                    if ut and ut not in ut_doi:
                        doi = (cols[idi] if idi < len(cols) else "").strip().lower()
                        if doi: ut_doi[ut] = doi
        except Exception as e:
            log(f"  ERR {fp.name}: {e}")
        if n % 300 == 0 or n == len(files):
            log(f"  TXT {n}/{len(files)}  UT→DOI={len(ut_doi):,}")
    json.dump(ut_doi, open(cache, "w"))
    log(f"  저장 ut_doi_all.json ({len(ut_doi):,})")
    return ut_doi

def induced_union():
    u = set()
    for org in ("kisti", "kbsi", "ibs", "pal"):
        for r in json.load(open(OUT / f"{org}_induced_papers.json")):
            u.add(r["UT"])
    return u

UA = f"KISTI-Policy/1.0 (mailto:{MAIL})"   # polite pool 식별

class BudgetExhausted(Exception):
    pass

def fetch(dois):
    """results(list) 반환. 일일예산 소진(429) → BudgetExhausted(전체 중단).
    기타 하드실패 → None(캐시하지 말고 다음 배치)."""
    flt = "doi:" + "|".join(dois)
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"filter": flt, "select": "id,doi", "per-page": 50, "mailto": MAIL})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["results"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise BudgetExhausted()        # 무료 일일예산 소진 → 리셋까지 무의미
            if attempt == 3:
                log(f"  batch 하드실패(스킵·재시도대상): HTTP {e.code}"); return None
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            if attempt == 3:
                log(f"  batch 하드실패(스킵·재시도대상): {e}"); return None
            time.sleep(3 * (attempt + 1))
    return None

def map_dois(dois):
    """{doi: oaid}. 성공배치만 미검출을 ''로 캐시. 예산소진 시 저장 후 중단(다음 리셋 재개)."""
    cache = json.load(open(DOI_CACHE)) if DOI_CACHE.exists() else {}
    todo = [d for d in dois if d not in cache]
    log(f"[4] OpenAlex 매핑: 대상 {len(dois):,} / 미매핑 {len(todo):,} (캐시 {len(cache):,})")
    hard_fail = 0
    stopped = False
    try:
        for i in range(0, len(todo), 50):
            b = todo[i:i + 50]
            results = fetch(b)
            if results is None:
                hard_fail += 1; continue
            got = {}
            for w in results:
                doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
                oid = (w.get("id") or "").rsplit("/", 1)[-1].lstrip("W")
                if doi and oid: got[doi] = oid
            for d in b:
                cache[d] = got.get(d, "")
            if (i // 50) % 25 == 0:
                json.dump(cache, open(DOI_CACHE, "w"))
                log(f"  {i+len(b):,}/{len(todo):,} (성공누계 {sum(1 for v in cache.values() if v):,})")
            time.sleep(0.25)             # ~4 req/s
    except BudgetExhausted:
        stopped = True
        log("  ※ OpenAlex 일일예산 소진 — 저장 후 중단. 다음 자정 UTC 리셋 뒤 재실행하면 자동 재개.")
    json.dump(cache, open(DOI_CACHE, "w"))
    log(f"  [체크포인트 저장] 성공누계 {sum(1 for v in cache.values() if v):,}"
        + (" (예산소진 중단)" if stopped else " (전량 처리)"))
    return cache

def main():
    ut_doi = build_ut_doi_all()
    ind = induced_union()
    log(f"[2] 유발합집합 UT={len(ind):,}")
    ind_ut_doi = {ut: ut_doi[ut] for ut in ind if ut in ut_doi}
    log(f"    유발 중 DOI 보유 {len(ind_ut_doi):,}")

    control_pool = [ut for ut in ut_doi if ut not in ind]
    random.seed(SEED)
    control = random.sample(control_pool, min(CONTROL_N, len(control_pool)))
    ctl_ut_doi = {ut: ut_doi[ut] for ut in control}
    log(f"[3] 대조군풀 {len(control_pool):,} → 표본 {len(ctl_ut_doi):,} (seed={SEED})")

    # 유발 우선 정렬: 예산 제한 시 유발부터 완료되도록
    ind_list = list(dict.fromkeys(ind_ut_doi.values()))
    seen = set(ind_list)
    ctl_list = [d for d in dict.fromkeys(ctl_ut_doi.values()) if d not in seen]
    all_dois = ind_list + ctl_list
    doi2oaid = map_dois(all_dois)

    def emit(ut_doi_map, name):
        out = {}
        for ut, doi in ut_doi_map.items():
            oaid = doi2oaid.get(doi, "")
            if oaid: out[ut] = {"doi": doi, "oaid": oaid}
        json.dump(out, open(OUT / name, "w"))
        cov = len(out) / len(ut_doi_map) * 100 if ut_doi_map else 0
        log(f"[5] {name}: {len(out):,}/{len(ut_doi_map):,} oaid 보유 ({cov:.1f}%)")
        return out

    emit(ind_ut_doi, "oaid_induced.json")
    emit(ctl_ut_doi, "oaid_control.json")
    log("DONE")

if __name__ == "__main__":
    main()
