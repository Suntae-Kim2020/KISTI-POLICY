#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""국내 논문 전수의 4기관(KISTI·KBSI·IBS·PAL) 소속 저자 판정.

유발논문(사사 기반)뿐 아니라 '사사표기는 없지만 기관 소속 저자가 있는 논문'(2×2의 ⓑ칸)을
식별하기 위해 원시 TXT 전수를 판정한다. 보조분석③(기관 소속 저자 논문 전면 제외)의 전제.

판정 기준은 build_induced_external.py와 동일 (C3 기관표준명 ∪ C1 주소 원문, 엄격안).
출력: data_2025/org_affiliation.json  {UT: [소속기관...]}   (소속 없는 논문은 미수록)
실행: KISTEP_BASE=/home/user/KISTEP .venv/bin/python build_org_affiliation.py
"""
import os, json, re
from pathlib import Path

PROJ = Path("/home/user/KISTI_Policy")
OUT = PROJ / "data_2025" / "org_affiliation.json"
RAW = Path(os.environ.get("KISTEP_BASE", "/home/user/KISTEP")) / "rawdata/report_2026/wos"
ORGS = ("kisti", "kbsi", "ibs", "pal")

C3_PAT = {
    "kisti": "Korea Institute of Science & Technology Information",
    "kbsi": "Korea Basic Science Institute",
    "ibs": "Institute for Basic Science",
    "pal": None,
}
C1_PAT = {
    "kisti": re.compile(r"Korea Inst Sci & Technol Informat|KISTI", re.I),
    "kbsi": re.compile(r"Korea Basic Sci Inst|\bKBSI\b", re.I),
    "ibs": re.compile(r"Inst Basic Sci|\bIBS\b(?!-R)", re.I),
    "pal": re.compile(r"Pohang Accelerat|Pohang Light Source|PLS-?II|PAL-?XFEL", re.I),
}

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
print(f"TXT {len(files)}개 전수 스캔", flush=True)

affil, seen = {}, set()
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
                if not ut or ut in seen:
                    continue
                seen.add(ut)
                c1 = cols[i1] if i1 < len(cols) else ""
                c3 = cols[i3] if i3 < len(cols) else ""
                if not c1 and not c3:
                    continue
                hit = [o for o in ORGS
                       if (C3_PAT[o] and C3_PAT[o] in c3) or C1_PAT[o].search(c1)]
                if hit:
                    affil[ut] = hit
    except Exception as e:
        print(f"  ERR {fp.name}: {e}", flush=True)
    if n % 300 == 0 or n == len(files):
        print(f"  {n}/{len(files)}  논문 {len(seen):,} / 소속적중 {len(affil):,}", flush=True)

json.dump(affil, open(OUT, "w"), ensure_ascii=False)
print(f"\n저장 {OUT}  (전체 {len(seen):,}편 중 4기관 소속 {len(affil):,}편)", flush=True)

# ── 2×2 집계 ────────────────────────────────────────────────
ind = json.load(open(PROJ / "data_2025/induced_external.json"))
ind_uts = set(ind)
a = sum(1 for u in ind_uts if not ind[u]["ext_any"])          # 사사O 소속O
c = sum(1 for u in ind_uts if ind[u]["ext_any"])              # 사사O 소속X
b = sum(1 for u in affil if u not in ind_uts)                 # 사사X 소속O
d = len(seen) - a - b - c
print("\n=== 2×2 분할 (국내 논문 전수) ===")
print(f"                     사사표기 있음      사사표기 없음")
print(f"  기관 소속 저자 있음   ⓐ {a:>9,}      ⓑ {b:>9,}")
print(f"  기관 소속 저자 없음   ⓒ {c:>9,}      ⓓ {d:>9,}")
print(f"  합계 {len(seen):,}편")
print("\n  주분석  처치 ⓒ {:,} vs 대조 ⓐⓑⓓ {:,}".format(c, a + b + d))
print("  보조③  처치 ⓒ {:,} vs 대조 ⓓ {:,}  (ⓐ+ⓑ {:,}편 모집단에서 제외)".format(c, d, a + b))
for o in ORGS:
    tot = sum(1 for v in affil.values() if o in v)
    nob = sum(1 for u, v in affil.items() if o in v and u not in ind_uts)
    print(f"    {o.upper():6} 소속 논문 {tot:>7,}편 (그중 사사표기 없음 {nob:>7,}편)")
