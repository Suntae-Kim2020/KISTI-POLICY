#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""논문1 국내 기준 로지스틱 회귀 — 주분석 + 보조①②③.

결과변수: 국내 기준 상위 10% / 상위 1% 진입 여부
모형    : logit(P) ~ 처치 + C(분야) + C(연도) + C(협력유형)

계산 방식: 공변량이 모두 범주형이므로 (분야×연도×협력×처치) 셀로 집계한 뒤
          이항 GLM(성공/실패 수)으로 추정한다. 개별 논문 단위 로지스틱과
          계수·표준오차가 수학적으로 동일하며, 97만 행을 수천 행으로 줄여
          메모리와 시간을 절약한다.

출력: data_2025/paper1_regression_kr.json
실행: .venv/bin/python build_paper1_regression.py
"""
import json
import numpy as np, pandas as pd
import statsmodels.api as sm
from patsy import dmatrix

P = "/home/user/KISTI_Policy/data_2025"
df = pd.read_pickle(f"{P}/.paper1_df.pkl")
print(f"[0] 분석표 {len(df):,}행 (처치 {int(df.treat.sum()):,})", flush=True)

RES = {}


def grouped(d, y, extra=()):
    """셀 집계 → (셀표, 성공수, 시행수)"""
    keys = ["treat", "field", "year", "collab"] + list(extra)
    g = d.groupby(keys, observed=True)[y].agg(["sum", "size"]).reset_index()
    return g.rename(columns={"sum": "k", "size": "n"})


def fit(d, y, formula="treat + C(field)+C(year)+C(collab)", label=""):
    g = grouped(d, y)
    g = g[g.n > 0]
    X = dmatrix(formula, g, return_type="dataframe")
    m = sm.GLM(np.c_[g.k, g.n - g.k], X, family=sm.families.Binomial()).fit()
    c = m.params["treat"]; ci = m.conf_int().loc["treat"]
    aor = (float(np.exp(c)), float(np.exp(ci[0])), float(np.exp(ci[1])), float(m.pvalues["treat"]))
    t, n = d[d.treat == 1], d[d.treat == 0]
    raw = (float(t[y].mean() * 100), float(n[y].mean() * 100), int(len(t)), int(len(n)))
    if label:
        print(f"  {label:28} 처치 {raw[0]:>5.1f}% vs 비교 {raw[1]:>5.1f}%   "
              f"aOR {aor[0]:.2f} ({aor[1]:.2f}-{aor[2]:.2f})  p={aor[3]:.2g}", flush=True)
    return {"aOR": aor[:3], "p": aor[3], "raw_treat_pct": raw[0], "raw_ctrl_pct": raw[1],
            "n_treat": raw[2], "n_ctrl": raw[3]}


# ── 주분석 ──────────────────────────────────────────────────
print("\n=== 주분석: 처치 21,948 vs 비교 952,864 ===", flush=True)
RES["main"] = {y: fit(df, y, label=f"주분석 {y}") for y in ("kr_top10", "kr_top1")}

# ── 보조① KISTI 단독 ────────────────────────────────────────
print("\n=== 보조① KISTI 단독 ===", flush=True)
k = df[(df.treat == 0) | (df.kisti == 1)].copy()          # 비교군 + KISTI 처치군만
RES["kisti_only"] = {y: fit(k, y, label=f"KISTI {y}") for y in ("kr_top10", "kr_top1")}

# ── 보조③ 기관 소속 저자 논문 전면 제외 ──────────────────────
print("\n=== 보조③ 기관 소속 저자 논문 모집단 제외 ===", flush=True)
e = df[df.org_affil == 0].copy()
print(f"  모집단 {len(df):,} → {len(e):,} (제외 {len(df)-len(e):,})", flush=True)
RES["no_org_affil"] = {y: fit(e, y, label=f"보조③ {y}") for y in ("kr_top10", "kr_top1")}

# ── 보조② 분야별 층화 ───────────────────────────────────────
print("\n=== 보조② 분야별 층화 (상위 10%) ===", flush=True)
strat = {}
for f, g in df.groupby("field"):
    nt = int(g.treat.sum())
    if nt < 100 or g[g.treat == 1].kr_top10.sum() < 10:
        continue
    try:
        r = fit(g, "kr_top10", formula="treat + C(year)+C(collab)")
    except Exception as ex:
        print(f"  {f:26} 실패({type(ex).__name__})"); continue
    strat[f] = r
    a = r["aOR"]
    print(f"  {f:26} 처치 n={nt:>6,}  {r['raw_treat_pct']:>5.1f}% vs {r['raw_ctrl_pct']:>5.1f}%   "
          f"aOR {a[0]:.2f} ({a[1]:.2f}-{a[2]:.2f})", flush=True)
RES["by_field_top10"] = strat

json.dump(RES, open(f"{P}/paper1_regression_kr.json", "w"), ensure_ascii=False, indent=1, default=float)
print(f"\n저장: data_2025/paper1_regression_kr.json", flush=True)
print("※ 국내 기준(분야×연도별 피인용 임계값). 세계 기준은 비교군 수집 완료 후 추가.", flush=True)
