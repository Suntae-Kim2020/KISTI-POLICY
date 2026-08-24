#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""논문1 기술통계 — FWCI 평균·중앙값(처치/비교/기관별) + 상위 진입률.

정 박사 문의 "국내 전체 논문의 FWCI 평균·중앙값"에 답하기 위한 산출.
비교군 수집(fwci_control_index.json) 완료로 이제 국내 기준값 제시가 가능하다.
출력: data_2025/paper1_descriptives.json
"""
import json, statistics as st
import pandas as pd

P = "/home/user/KISTI_Policy/data_2025"
df = pd.read_pickle(f"{P}/.paper1_df.pkl").set_index("UT")
fw_i = json.load(open(f"{P}/fwci_index.json"))
fw_c = json.load(open(f"{P}/fwci_control_index.json"))
ind = json.load(open(f"{P}/induced_external.json"))
RES = {}


def stats(items, label):
    v = [e["fwci"] for e in items if e.get("fwci") is not None]
    if not v:
        return None
    r = {"n": len(v), "mean": st.mean(v), "median": st.median(v), "max": max(v),
         "top10": sum(e["top10"] for e in items) / len(items) * 100,
         "top1": sum(e["top1"] for e in items) / len(items) * 100}
    print(f"  {label:30} n={r['n']:>7,}  평균 {r['mean']:>5.2f}  중앙 {r['median']:>5.2f}  "
          f"상위10% {r['top10']:>5.1f}%  상위1% {r['top1']:>4.1f}%", flush=True)
    return r


print("=== FWCI 기술통계 (세계 평균 = 1.0) ===", flush=True)
ext = [u for u, v in ind.items() if v["ext_any"]]
inn = [u for u, v in ind.items() if not v["ext_any"]]
RES["treat"] = stats([fw_i[u] for u in ext if u in fw_i], "처치군: 외부 연계논문")
RES["control_sample"] = stats(list(fw_c.values()), "비교군: 국내 일반논문(10만 표본)")
RES["internal"] = stats([fw_i[u] for u in inn if u in fw_i], "(참고) 기관 소속 저자 포함 유발논문")

print("\n=== 기관별 외부 연계논문 ===", flush=True)
RES["by_org"] = {}
for o in ("kisti", "kbsi", "ibs", "pal"):
    uts = [u for u in ext if o in ind[u]["orgs"] and u in fw_i]
    RES["by_org"][o] = stats([fw_i[u] for u in uts], f"{o.upper()}")

print("\n=== 국내 기준 상위 진입률 (분야×연도 임계값) ===", flush=True)
for lab, g in [("처치군", df[df.treat == 1]), ("비교군(전수)", df[df.treat == 0])]:
    r = {"n": int(len(g)), "top10": float(g.kr_top10.mean() * 100),
         "top1": float(g.kr_top1.mean() * 100), "mean_tc": float(g.TC.mean()),
         "median_tc": float(g.TC.median())}
    RES[f"kr_{lab}"] = r
    print(f"  {lab:30} n={r['n']:>7,}  상위10% {r['top10']:>5.1f}%  상위1% {r['top1']:>4.2f}%  "
          f"평균TC {r['mean_tc']:>5.1f}  중앙TC {r['median_tc']:>4.0f}", flush=True)

json.dump(RES, open(f"{P}/paper1_descriptives.json", "w"), ensure_ascii=False, indent=1, default=float)
print(f"\n저장: data_2025/paper1_descriptives.json", flush=True)
