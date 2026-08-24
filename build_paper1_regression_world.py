#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""논문1 세계 기준 로지스틱 회귀 (OpenAlex 상위 10%·1%).

국내 기준(build_paper1_regression.py)과 동일한 모형·보조분석을 세계 기준으로 반복.

비교군 구성 주의:
  · fwci_control_index.json = 무작위 10만 표본 중 수집분 → 2×2의 ⓑ+ⓓ에 해당
  · 확정안의 비교군은 ⓐ+ⓑ+ⓓ이므로, 이미 확보된 ⓐ(내부 유발논문, fwci_index.json)를
    모집단 비율(1.382%)에 맞춰 무작위로 합류시켜 구성을 재현한다.
출력: data_2025/paper1_regression_world.json
"""
import json
import numpy as np, pandas as pd
import statsmodels.api as sm
from patsy import dmatrix

P = "/home/user/KISTI_Policy/data_2025"
SEED = 42
df = pd.read_pickle(f"{P}/.paper1_df.pkl").set_index("UT")
fw_ind = json.load(open(f"{P}/fwci_index.json"))            # 유발논문(ⓐ+ⓒ)
fw_ctl = json.load(open(f"{P}/fwci_control_index.json"))    # 표본(ⓑ+ⓓ) 수집분
ind = json.load(open(f"{P}/induced_external.json"))

def rows(uts, fw, treat):
    out = []
    for u in uts:
        if u not in df.index or u not in fw:
            continue
        e = fw[u]; r = df.loc[u]
        out.append((u, treat, int(e["top10"]), int(e["top1"]), r.field, r.year, r.collab,
                    int(r.org_affil), int(r.kisti)))
    return out

treat_uts = [u for u, v in ind.items() if v["ext_any"]]
inner_uts = [u for u, v in ind.items() if not v["ext_any"]]
T = rows(treat_uts, fw_ind, 1)
C_bd = rows(list(fw_ctl), fw_ctl, 0)
rng = np.random.default_rng(SEED)
n_a = int(round(len(C_bd) * 0.01382 / 0.98618))             # ⓐ 비율 맞춰 합류
a_pool = [u for u in inner_uts if u in fw_ind and u in df.index]
C_a = rows(list(rng.choice(a_pool, size=min(n_a, len(a_pool)), replace=False)), fw_ind, 0)
d = pd.DataFrame(T + C_bd + C_a,
                 columns=["UT", "treat", "w_top10", "w_top1", "field", "year", "collab",
                          "org_affil", "kisti"])
print(f"[0] 처치 {len(T):,} / 비교 {len(C_bd)+len(C_a):,} (ⓑⓓ {len(C_bd):,} + ⓐ {len(C_a):,})", flush=True)
print(f"    ※ 비교군 수집 진행률 {len(fw_ctl)/99484*100:.1f}% — 미완료 시 예비치", flush=True)

def fit(data, y, formula="treat + C(field)+C(year)+C(collab)", label=""):
    g = data.groupby(["treat", "field", "year", "collab"], observed=True)[y] \
            .agg(["sum", "size"]).reset_index().rename(columns={"sum": "k", "size": "n"})
    g = g[g.n > 0]
    X = dmatrix(formula, g, return_type="dataframe")
    m = sm.GLM(np.c_[g.k, g.n - g.k], X, family=sm.families.Binomial()).fit()
    c = m.params["treat"]; ci = m.conf_int().loc["treat"]
    t, n = data[data.treat == 1], data[data.treat == 0]
    if label:
        print(f"  {label:26} 처치 {t[y].mean()*100:>5.1f}% vs 비교 {n[y].mean()*100:>5.1f}%   "
              f"aOR {np.exp(c):.2f} ({np.exp(ci[0]):.2f}-{np.exp(ci[1]):.2f})  p={m.pvalues['treat']:.2g}",
              flush=True)
    return {"aOR": [float(np.exp(c)), float(np.exp(ci[0])), float(np.exp(ci[1]))],
            "p": float(m.pvalues["treat"]), "raw_treat_pct": float(t[y].mean()*100),
            "raw_ctrl_pct": float(n[y].mean()*100), "n_treat": int(len(t)), "n_ctrl": int(len(n))}

RES = {"coverage": len(fw_ctl)/99484}
print("\n=== 주분석 (세계 기준) ===", flush=True)
RES["main"] = {y: fit(d, y, label=f"주분석 {y}") for y in ("w_top10", "w_top1")}
print("\n=== 보조① KISTI 단독 ===", flush=True)
k = d[(d.treat == 0) | (d.kisti == 1)]
RES["kisti_only"] = {y: fit(k, y, label=f"KISTI {y}") for y in ("w_top10", "w_top1")}
print("\n=== 보조③ 기관 소속 저자 논문 제외 ===", flush=True)
e = d[d.org_affil == 0]
print(f"  비교 {int((d.treat==0).sum()):,} → {int((e.treat==0).sum()):,}", flush=True)
RES["no_org_affil"] = {y: fit(e, y, label=f"보조③ {y}") for y in ("w_top10", "w_top1")}
print("\n=== 보조② 분야별 층화 (세계 상위 10%) ===", flush=True)
strat = {}
for f, g in d.groupby("field"):
    if int(g.treat.sum()) < 100 or g[g.treat == 1].w_top10.sum() < 10 or (g.treat == 0).sum() < 100:
        continue
    try:
        r = fit(g, "w_top10", formula="treat + C(year)+C(collab)")
    except Exception as ex:
        continue
    strat[f] = r; a = r["aOR"]
    print(f"  {f:26} 처치 n={int(g.treat.sum()):>6,}  {r['raw_treat_pct']:>5.1f}% vs "
          f"{r['raw_ctrl_pct']:>5.1f}%   aOR {a[0]:.2f} ({a[1]:.2f}-{a[2]:.2f})", flush=True)
RES["by_field_top10"] = strat
json.dump(RES, open(f"{P}/paper1_regression_world.json", "w"), ensure_ascii=False, indent=1, default=float)
print(f"\n저장: data_2025/paper1_regression_world.json (비교군 수집률 {RES['coverage']*100:.1f}%)", flush=True)
