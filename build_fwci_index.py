#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAlex 글로벌 FWCI 인덱스 생성 → data_2025/fwci_index.json

배경: 대시보드의 영향력 지표(MNCS)는 "한국 평균" 분모라 국제표준(CNCI/FWCI)이 아니다
(제약 #5). OpenAlex는 논문별 글로벌 FWCI와 세계 피인용 백분위(top1%/top10%)를 무료로
제공하므로, 유발논문 DOI를 조회해 UT별 인덱스를 만들어 compute.py가 소비하게 한다.

흐름:
  1) 원시 report_2026 TXT 1회 스캔 → 대상 UT의 UT→DOI 맵 (DI 필드)
  2) OpenAlex works API 배치 조회(doi OR 필터, 50개/req, polite pool) → fwci/백분위/피인용
  3) data_2025/fwci_index.json = {UT: {"fwci","top1","top10","cited_by","oa_year"}}

입력(읽기전용): KISTEP/rawdata/report_2026/wos/{SCIE,SSCI,AHCI}, data_2025/*_induced_papers.json
출력(이 프로젝트): data_2025/fwci_index.json

주의: 순수 부가지표 인덱스. compute.py는 resolve_file(optional=True)로 로드하므로
없으면 조용히 스킵(FWCI 미표시). 유발논문 UT 집합만 대상(직접논문은 후속 확장).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
DEFAULT_RAW = Path(os.environ.get("KISTEP_BASE", "/Users/kimsuntae/KISTEP")) / "rawdata/report_2026/wos"
OUT_DIR = PROJECT / "data_2025"
OUT_FILE = OUT_DIR / "fwci_index.json"
MAILTO = "kistiman@gmail.com"
BATCH = 50


def load_target_uts():
    uts = set()
    for org in ("kisti", "kbsi", "ibs", "pal"):
        p = OUT_DIR / f"{org}_induced_papers.json"
        for r in json.load(open(p)):
            uts.add(r["UT"])
    return uts


def build_ut_doi(raw, targets):
    def txt_files():
        fs = []
        scie = raw / "SCIE"
        if scie.exists():
            for yd in sorted(scie.iterdir()):
                if yd.is_dir():
                    fs += sorted(yd.glob("*.txt"))
        for sub in ("SSCI", "AHCI"):
            d = raw / sub
            if d.exists():
                fs += sorted(d.glob("*.txt"))
        return fs

    ut_doi = {}
    files = txt_files()
    if not files:
        print(f"[오류] 원시 TXT 없음: {raw}", file=sys.stderr)
        sys.exit(1)
    for n, fp in enumerate(files, 1):
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                hdr = f.readline().rstrip("\n\r").split("\t")
                if "UT" not in hdr or "DI" not in hdr:
                    continue
                iu, idi = hdr.index("UT"), hdr.index("DI")
                for line in f:
                    cols = line.rstrip("\n\r").split("\t")
                    if iu >= len(cols):
                        continue
                    ut = cols[iu]
                    if ut in targets and ut not in ut_doi:
                        doi = cols[idi] if idi < len(cols) else ""
                        if doi:
                            ut_doi[ut] = doi.strip().lower()
        except Exception as e:
            print(f"  ERR {fp.name}: {e}", file=sys.stderr)
        if n % 300 == 0 or n == len(files):
            print(f"  TXT {n}/{len(files)}  UT→DOI={len(ut_doi):,}", flush=True)
    return ut_doi


def fetch_openalex(dois):
    q = urllib.parse.urlencode({
        "filter": "doi:" + "|".join(dois),
        "select": "doi,fwci,citation_normalized_percentile,cited_by_count,publication_year",
        "per_page": BATCH,
        "mailto": MAILTO,
    })
    url = f"https://api.openalex.org/works?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": f"KISTI-Policy/1.0 (mailto:{MAILTO})"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())["results"]
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limit — retry-after 존중 + 긴 백오프
                wait = int(e.headers.get("Retry-After", 0)) or (5 * (attempt + 1) ** 2)
                print(f"  429 rate limit — {wait}s 대기 (attempt {attempt+1})", flush=True)
                time.sleep(min(wait, 90))
                continue
            if attempt == 5:
                print(f"  FAIL batch (HTTP {e.code}): {e}", file=sys.stderr)
                return None
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            if attempt == 5:
                print(f"  FAIL batch: {e}", file=sys.stderr)
                return None
            time.sleep(3 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser(description="OpenAlex 글로벌 FWCI 인덱스 생성")
    ap.add_argument("--raw", default=str(DEFAULT_RAW), help="report_2026/wos 경로")
    args = ap.parse_args()
    raw = Path(args.raw)

    t0 = time.time()
    targets = load_target_uts()
    print(f"대상 유발 UT(합집합): {len(targets):,}", flush=True)

    # UT→DOI 캐시 (원시 TXT 재스캔 회피, 재실행 시 재사용)
    utdoi_cache = OUT_DIR / ".fwci_utdoi_cache.json"
    print("=== 1) UT→DOI (원시 TXT 스캔) ===")
    if utdoi_cache.exists():
        ut_doi = json.loads(utdoi_cache.read_text())
        print(f"  캐시 재사용: {utdoi_cache.name} ({len(ut_doi):,})")
    else:
        ut_doi = build_ut_doi(raw, targets)
        utdoi_cache.write_text(json.dumps(ut_doi, ensure_ascii=False))
    print(f"  UT→DOI: {len(ut_doi):,} / {len(targets):,} ({len(ut_doi)/len(targets)*100:.1f}%)")

    print("=== 2) OpenAlex 배치 조회 (체크포인트/재개) ===")
    doi_uts = {}
    for ut, doi in ut_doi.items():
        doi_uts.setdefault(doi, []).append(ut)
    dois = list(doi_uts.keys())

    # 체크포인트: DOI→레코드 부분 결과. 재실행 시 이어받음(429로 죽어도 손실 최소화).
    ckpt = OUT_DIR / ".fwci_doi_rec.ckpt.json"
    doi_rec = json.loads(ckpt.read_text()) if ckpt.exists() else {}
    if doi_rec:
        print(f"  체크포인트 재개: 이미 {len(doi_rec):,} DOI 확보", flush=True)
    done = set(doi_rec.keys())
    todo = [d for d in dois if d not in done]
    print(f"  남은 조회: {len(todo):,}", flush=True)

    for i in range(0, len(todo), BATCH):
        res = fetch_openalex(todo[i:i + BATCH])
        if res is None:  # 하드 실패(재시도 소진) → 체크포인트 저장 후 중단(재실행으로 이어받기)
            ckpt.write_text(json.dumps(doi_rec, ensure_ascii=False))
            print(f"  [중단] 배치 실패 — 체크포인트 저장({len(doi_rec):,}). 재실행하면 이어받음.", file=sys.stderr)
            sys.exit(2)
        for w in res:
            d = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            if d:
                doi_rec[d] = w
        if (i // BATCH) % 25 == 0 or i + BATCH >= len(todo):
            print(f"  OA {min(i+BATCH,len(todo)):,}/{len(todo):,}  누적매칭={len(doi_rec):,}", flush=True)
            ckpt.write_text(json.dumps(doi_rec, ensure_ascii=False))  # 주기적 체크포인트
        time.sleep(0.2)
    ckpt.write_text(json.dumps(doi_rec, ensure_ascii=False))

    print("=== 3) UT 인덱스 작성 ===")
    index = {}
    for doi, uts in doi_uts.items():
        w = doi_rec.get(doi)
        if not w:
            continue
        cnp = w.get("citation_normalized_percentile") or {}
        entry = {
            "fwci": w.get("fwci"),
            "top1": bool(cnp.get("is_in_top_1_percent")),
            "top10": bool(cnp.get("is_in_top_10_percent")),
            "cited_by": w.get("cited_by_count"),
            "oa_year": w.get("publication_year"),
        }
        for ut in uts:
            index[ut] = entry
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json.dump(index, open(OUT_FILE, "w"), ensure_ascii=False)
    cov = len(index) / len(targets) * 100
    print(f"=== 완료: {OUT_FILE} ({len(index):,} UT, 커버리지 {cov:.1f}%, {time.time()-t0:.0f}초) ===")


if __name__ == "__main__":
    main()
