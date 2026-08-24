#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본작업 2: 논문별 USPTO 특허피인용수 집계 (Reliance on Science) + 유발/유형/대조군 비교.
입력: data_2025/oaid_induced.json, oaid_control.json, {org}_induced_papers.json,
      pcs_oa_uspto.csv (특허→논문 인용)
출력: data_2025/patcit_paper.json (oaid→{total,front,intext}), 콘솔 요약표
"""
import json
from pathlib import Path

OUT = Path("/home/user/KISTI_Policy/data_2025")
PCS = "/media/user/df9db4f3-386b-4bd4-b1bf-fcebb530b180/reliance_on_science/pcs_oa_uspto.csv"

ind = json.load(open(OUT / "oaid_induced.json"))     # {UT:{doi,oaid}}
ctl = json.load(open(OUT / "oaid_control.json"))
# 기관별 UT
org_ut = {o: {r["UT"] for r in json.load(open(OUT / f"{o}_induced_papers.json"))}
          for o in ("kisti", "kbsi", "ibs", "pal")}

# oaid → 그룹 매핑
ind_oaid = {v["oaid"] for v in ind.values()}
ctl_oaid = {v["oaid"] for v in ctl.values() if v["oaid"] not in ind_oaid}
# 기관별 oaid
org_oaid = {o: set() for o in org_ut}
for ut, v in ind.items():
    for o, uts in org_ut.items():
        if ut in uts: org_oaid[o].add(v["oaid"])

want = ind_oaid | ctl_oaid
print(f"대상 oaid — 유발 {len(ind_oaid):,} / 대조군 {len(ctl_oaid):,}", flush=True)

# pcs 스트리밍: oaid→{total, front, intext}  (우리 oaid만)
cnt = {}
with open(PCS) as f:
    next(f)
    for line in f:
        p = line.split(",")
        if len(p) < 5: continue
        oid = p[2]
        if oid in want:
            d = cnt.setdefault(oid, [0, 0, 0])   # total, front, intext(body/both)
            d[0] += 1
            if p[4].strip() == "frontonly": d[1] += 1
            else: d[2] += 1
print(f"특허인용 보유 논문(≥1): {len(cnt):,}", flush=True)
json.dump(cnt, open(OUT / "patcit_paper.json", "w"))

def stat(oaids, name):
    n = len(oaids)
    cited = sum(1 for o in oaids if o in cnt)
    tot = sum(cnt.get(o, [0])[0] for o in oaids)
    front = sum(cnt.get(o, [0, 0])[1] if o in cnt else 0 for o in oaids)
    intext = sum(cnt.get(o, [0, 0, 0])[2] if o in cnt else 0 for o in oaids)
    print(f"  {name:16} n={n:>6,} | 연계율 {cited/n*100:5.2f}% | 총인용 {tot:>6,} "
          f"| 논문당 {tot/n:.3f} | front {front:>5,} intext {intext:>5,}")
    return dict(n=n, cited=cited, rate=cited/n, total=tot, avg=tot/n)

print("\n=== USPTO 특허인용: 유형별 (유발) vs 대조군 ===", flush=True)
res = {}
res["induced_all"] = stat(ind_oaid, "유발 전체")
for o in ("kisti", "ibs", "pal", "kbsi"):
    res[o] = stat(org_oaid[o], o.upper())
res["control"] = stat(ctl_oaid, "대조군(비유발)")

pc = res["control"]["rate"]
print("\n=== 특허연계율 crude 오즈비 (vs 비유발) ===", flush=True)
for k, lbl in [("induced_all", "유발 전체"), ("kisti", "KISTI"), ("ibs", "IBS"),
               ("pal", "PAL"), ("kbsi", "KBSI")]:
    pi = res[k]["rate"]
    orr = (pi / (1 - pi)) / (pc / (1 - pc)) if 0 < pi < 1 else float("nan")
    avgratio = res[k]["avg"] / res["control"]["avg"]
    print(f"  {lbl:10} 연계율 {pi*100:5.2f}%  OR {orr:4.2f}  | 논문당평균 {avgratio:.2f}배")
json.dump(res, open(OUT / "patcit_summary.json", "w"), ensure_ascii=False, indent=1)
print("\n저장: data_2025/patcit_paper.json, patcit_summary.json")
print("※ 예비치(대조군 64%, 연도 미보정). 확정은 대조군 완료 + 회귀(연도·분야·협력·학술인용 통제) 후.")
