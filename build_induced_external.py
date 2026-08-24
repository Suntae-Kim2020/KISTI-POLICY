#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""유발논문의 '기관 소속 저자 포함 여부' 판정 → data_2025/induced_external.json

개정 정의(외부 유발논문 = 해당 기관 소속 저자가 없는 유발논문)를 적용하기 위한 상류 단계.
WoS C3(기관표준명)와 C1(저자 주소 원문)을 함께 사용한다.
  · C3 : 대학 내 입주 연구단 등 하위조직을 모기관으로 정규화해 줌 (IBS에 필수)
  · C1 : WoS 표준명이 없는 기관을 잡아 줌 (PAL에 필수 — C3에 PAL 항목 자체가 없음)
판정 기준: 공저자 1인이라도 해당 기관 소속이면 '내부'(엄격안).

출력 스키마: {UT: {"orgs": [유발기관...], "internal": [소속저자 있는 기관...],
               "ext_any": bool}}   ext_any = 어느 기관에도 소속 저자가 없음
실행: KISTEP_BASE=/home/user/KISTEP .venv/bin/python build_induced_external.py
"""
import os, json, re, sys
from pathlib import Path

PROJ = Path("/home/user/KISTI_Policy")
OUT = PROJ / "data_2025" / "induced_external.json"
RAW = Path(os.environ.get("KISTEP_BASE", "/home/user/KISTEP")) / "rawdata/report_2026/wos"
ORGS = ("kisti", "kbsi", "ibs", "pal")

# C3(기관표준명) 포함 문자열
C3_PAT = {
    "kisti": "Korea Institute of Science & Technology Information",
    "kbsi": "Korea Basic Science Institute",
    "ibs": "Institute for Basic Science",
    "pal": None,                      # WoS 표준명 부재 → C1으로만 판정
}
# C1(주소 원문) 정규식 — WoS는 축약형 기관명 사용
C1_PAT = {
    "kisti": re.compile(r"Korea Inst Sci & Technol Informat|KISTI", re.I),
    "kbsi": re.compile(r"Korea Basic Sci Inst|\bKBSI\b", re.I),
    "ibs": re.compile(r"Inst Basic Sci|\bIBS\b(?!-R)", re.I),
    "pal": re.compile(r"Pohang Accelerat|Pohang Light Source|PLS-?II|PAL-?XFEL", re.I),
}

want = {}
for o in ORGS:
    for r in json.load(open(PROJ / f"data_2025/{o}_induced_papers.json")):
        want.setdefault(r["UT"], set()).add(o)
print(f"유발 합집합 UT={len(want):,}", flush=True)

files = []
scie = RAW / "SCIE"
if scie.exists():
    for yd in sorted(scie.iterdir()):
        if yd.is_dir():
            files += sorted(yd.glob("*.txt"))
for sub in ("SSCI", "AHCI"):
    d = RAW / sub
    if d.exists():
        files += sorted(d.glob("*.txt"))
print(f"TXT {len(files)}개 스캔", flush=True)

out = {}
for n, fp in enumerate(files, 1):
    try:
        with open(fp, encoding="utf-8-sig") as f:
            hdr = f.readline().rstrip("\n\r").split("\t")
            if any(c not in hdr for c in ("UT", "C1", "C3")):
                continue
            iu, i1, i3 = hdr.index("UT"), hdr.index("C1"), hdr.index("C3")
            for line in f:
                cols = line.rstrip("\n\r").split("\t")
                if iu >= len(cols):
                    continue
                ut = cols[iu]
                if ut not in want or ut in out:
                    continue
                c1 = cols[i1] if i1 < len(cols) else ""
                c3 = cols[i3] if i3 < len(cols) else ""
                orgs = sorted(want[ut])
                inn = [o for o in orgs
                       if (C3_PAT[o] and C3_PAT[o] in c3) or C1_PAT[o].search(c1)]
                out[ut] = {"orgs": orgs, "internal": inn, "ext_any": not inn}
    except Exception as e:
        print(f"  ERR {fp.name}: {e}", flush=True)
    if n % 300 == 0 or n == len(files):
        print(f"  {n}/{len(files)}  판정 {len(out):,}/{len(want):,}", flush=True)

# 미매칭 UT(원시 TXT에서 못 찾은 경우)는 보수적으로 내부 처리하지 않고 별도 표기
miss = [u for u in want if u not in out]
for u in miss:
    out[u] = {"orgs": sorted(want[u]), "internal": [], "ext_any": True, "unmatched": True}

json.dump(out, open(OUT, "w"), ensure_ascii=False)
ext = sum(1 for v in out.values() if v["ext_any"])
print(f"\n저장 {OUT}", flush=True)
print(f"  전체 {len(out):,} / 외부 {ext:,} ({ext/len(out)*100:.1f}%) / 미매칭 {len(miss):,}", flush=True)
for o in ORGS:
    tot = sum(1 for v in out.values() if o in v["orgs"])
    e = sum(1 for v in out.values() if o in v["orgs"] and o not in v["internal"])
    print(f"  {o.upper():6} {tot:>6,} → 외부 {e:>6,} ({e/tot*100:.1f}%)", flush=True)
