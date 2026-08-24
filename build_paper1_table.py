#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""논문1 분석표 생성 — 국내 기준 상위 10%·1% 임계값 산출 포함.

확정안:
  처치군 ⓒ = 4기관 인프라 사사표기 O + 해당 기관 소속 저자 X   (21,967편)
  비교군    = 나머지 국내 논문 전체                              (958,430편)
  주지표    = 상위 10%·1% 진입 여부 (국내 기준: 분야×연도별 피인용 임계값)

국내 기준 임계값은 외부 데이터 없이 WoS 피인용수로 직접 산출한다(전수 사용 가능).
세계 기준(OpenAlex)은 build_fwci_control.py 수집 완료 후 별도 결합.

출력: data_2025/.paper1_df.pkl        분석표
      data_2025/kr_top_thresholds.json 분야×연도별 상위10%/1% 임계값
실행: KISTEP_BASE=/home/user/KISTEP .venv/bin/python build_paper1_table.py
"""
import os, json, pickle
import numpy as np, pandas as pd
from pathlib import Path

KB = Path(os.environ.get("KISTEP_BASE", "/home/user/KISTEP"))
P = Path("/home/user/KISTI_Policy/data_2025")

print("[1] wos_data + ESI 분야 매핑 로딩", flush=True)
wos = pickle.load(open(KB / "generated/2026/wos_data.pkl", "rb"))
esi = pickle.load(open(KB / "generated/master/esi_journal_map.pkl", "rb"))
E = {"Environment/Ecology": "Environment Ecology", "Psychiatry/Psychology": "Psychiatry Psychology"}


def fld(r):
    s = (r.get("SN") or "").strip(); e = (r.get("EI") or "").strip()
    x = esi.get(s) or esi.get(e)
    return E.get(x, x) if x else r.get("std_field")


rows = []
for r in wos:
    ut, py, ct = r.get("UT"), r.get("PY"), r.get("collab_type")
    f = fld(r)
    if ut and isinstance(py, int) and 2011 <= py <= 2025 and ct and f:
        rows.append((ut, py, r.get("TC", 0) or 0, f, ct))
df = pd.DataFrame(rows, columns=["UT", "year", "TC", "field", "collab"])
del wos
print(f"    모집단 {len(df):,}편 (2011-2025, 분야·협력유형 결측 제외)", flush=True)

print("[2] 처치군·소속 플래그 결합", flush=True)
ind = json.load(open(P / "induced_external.json"))       # 유발논문 판정
aff = json.load(open(P / "org_affiliation.json"))        # 전수 소속 판정
ext_uts = {u for u, v in ind.items() if v["ext_any"]}    # ⓒ
df["treat"] = df.UT.isin(ext_uts).astype(int)            # 처치군
df["induced"] = df.UT.isin(ind).astype(int)              # 사사표기 유무
df["org_affil"] = df.UT.isin(aff).astype(int)            # 기관 소속 저자 유무
for o in ("kisti", "kbsi", "ibs", "pal"):
    df[o] = df.UT.map(lambda u, o=o: int(o in ind.get(u, {}).get("orgs", [])))
print(f"    처치군 {int(df.treat.sum()):,} / 사사표기 {int(df.induced.sum()):,} / "
      f"기관소속 {int(df.org_affil.sum()):,}", flush=True)

print("[3] 국내 기준 상위 10%·1% 임계값 산출 (분야×연도)", flush=True)
th = {}
top10 = np.zeros(len(df), dtype=np.int8); top1 = np.zeros(len(df), dtype=np.int8)
for (f, y), g in df.groupby(["field", "year"]):
    if len(g) < 30:                      # 표본 과소 셀은 임계값 불안정 → 제외 표시
        th[f"{f}|{y}"] = None
        continue
    t10 = float(np.percentile(g.TC, 90)); t1 = float(np.percentile(g.TC, 99))
    th[f"{f}|{y}"] = {"n": int(len(g)), "t10": t10, "t1": t1}
    idx = g.index
    top10[idx] = (g.TC >= t10).astype(np.int8)
    top1[idx] = (g.TC >= t1).astype(np.int8)
df["kr_top10"] = top10; df["kr_top1"] = top1
df["logTC"] = np.log1p(df.TC)

ok = sum(1 for v in th.values() if v)
print(f"    셀 {len(th):,}개 중 임계값 산출 {ok:,}개", flush=True)
print(f"    전체 상위10% 판정 {int(df.kr_top10.sum()):,}편 ({df.kr_top10.mean()*100:.1f}%) "
      f"/ 상위1% {int(df.kr_top1.sum()):,}편 ({df.kr_top1.mean()*100:.2f}%)", flush=True)
print("    ※ 동점 처리로 명목 10%/1%를 다소 상회할 수 있음(임계값 이상 전부 포함)", flush=True)

df.to_pickle(P / ".paper1_df.pkl")
json.dump(th, open(P / "kr_top_thresholds.json", "w"), ensure_ascii=False)
print(f"\n저장: .paper1_df.pkl ({len(df):,}행), kr_top_thresholds.json", flush=True)

print("\n[참고] 처치군 vs 비교군 원시 비교 (조정 전)")
for lab, g in [("처치군(외부 연계)", df[df.treat == 1]), ("비교군(나머지 전체)", df[df.treat == 0])]:
    print(f"  {lab:20} n={len(g):>8,}  상위10% {g.kr_top10.mean()*100:>5.1f}%  "
          f"상위1% {g.kr_top1.mean()*100:>4.2f}%  평균TC {g.TC.mean():>5.1f}", flush=True)
