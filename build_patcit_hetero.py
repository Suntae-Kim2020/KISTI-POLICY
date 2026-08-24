#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본작업 3 강건성 II: 회귀 조정의 3대 가정을 직접 검증.

build_patcit_regression.py는 무작위 대조군 + 공변량 조정(C(field)+C(collab)+C(year))
방식이라, 균형을 표본이 아니라 모형이 담당한다. 그 대가로 붙는 가정 세 가지를 각각 검사:

  ① 모형 의존성  → 분야별 층화 회귀 + induced×field 교호작용 LR검정 (효과 동질성?)
  ② 공통 지지    → field×collab×year 셀 커버리지 + 성향점수 겹침 진단
                   + 캘리퍼 1:1 성향점수매칭(PSM) 재현 (외삽 없이 같은 결론인가?)
  ③ 함수형       → logTC 선형 vs 십분위 더미 vs 스플라인 (모델B 결론이 형태에 의존?)

입력: data_2025/.patcit_df.pkl (build_patcit_regression.py가 생성)
출력: data_2025/patcit_hetero_{external|all}.json
실행: /home/user/KISTI_Policy/.venv/bin/python build_patcit_hetero.py
"""
import json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from patsy import dmatrix
import patcit_defs as PD

P = "/home/user/KISTI_Policy/data_2025"
SEED = 42
COV = "C(field)+C(collab)+C(year)"

df_all = pd.read_pickle(f"{P}/.patcit_df.pkl")
MODE = PD.mode()
FLAGS = PD.load_flags() if MODE == "external" else None
LBL = {"external": "개정(외부 유발논문만)", "all": "현행(전체 유발논문)"}[MODE]
df_all = df_all.copy()
# TC 십분위는 정의 필터 전에 계산해 기관별 부분집합에도 열이 남도록 한다
df_all["tcdec"] = pd.qcut(df_all["logTC"], 10, labels=False, duplicates="drop")
df = PD.apply(df_all, None, FLAGS, MODE)
print(f"[0] 유발논문 정의: {LBL}", flush=True)
print(f"[0] 분석표 n={len(df):,} (유발 {int(df.induced.sum()):,} / 비유발 {int((df.induced==0).sum()):,})",
      flush=True)


def prep(sub):
    """이벤트 희소 분야를 Other로 병합해 완전분리 방지 (회귀 스크립트와 동일 규칙)."""
    sub = sub.copy()
    ev = sub.groupby("field")["patent_any"].sum()
    rare = set(ev[ev < 5].index)
    if rare:
        sub["field"] = sub["field"].where(~sub["field"].isin(rare), "Other")
    return sub


def orci(m, term="induced"):
    c = m.params[term]; ci = m.conf_int().loc[term]
    return float(np.exp(c)), float(np.exp(ci[0])), float(np.exp(ci[1]))


def fit(formula, data):
    return smf.glm(formula, data=data, family=sm.families.Binomial()).fit()


def fmt(t):
    return "실패" if t is None else f"{t[0]:.2f} ({t[1]:.2f}-{t[2]:.2f})"


def groups():
    nonind = df[df.induced == 0]
    out = [("유발전체", df)]
    for o in ("kisti", "ibs", "pal", "kbsi"):
        sub = pd.concat([df_all[(df_all.induced == 1) & (df_all[o] == 1)], nonind])
        out.append((o.upper(), PD.apply(sub, o, FLAGS, MODE)))
    return out


RES = {}

# ─────────────────────────────────────────────────────────────
# ① 모형 의존성 — 분야별 층화 회귀 + 교호작용 검정
# ─────────────────────────────────────────────────────────────
print("\n=== ① 이질성: 분야별 층화 회귀 (분야 안에서만 유발 vs 비유발) ===", flush=True)
print(f"  {'분야':26} {'유발n':>7} {'대조n':>7} {'유발%특허':>9} {'대조%특허':>9} "
      f"{'모델A aOR':>18} {'모델B aOR':>18}", flush=True)

strat = {}
for f, g in df.groupby("field"):
    ni, nc = int(g.induced.sum()), int((g.induced == 0).sum())
    ev_i = int(g[g.induced == 1].patent_any.sum()); ev_c = int(g[g.induced == 0].patent_any.sum())
    if ni < 200 or nc < 200 or min(ev_i, ev_c) < 10:
        continue                      # 층 내 추정 불가능한 소규모 분야는 제외(별도 집계)
    try:
        a = orci(fit("patent_any ~ induced + C(collab)+C(year)", g))
        b = orci(fit("patent_any ~ induced + logTC + C(collab)+C(year)", g))
    except Exception as e:
        print(f"  {f:26} 실패: {type(e).__name__}"); continue
    strat[f] = {"n_ind": ni, "n_ctl": nc, "pat_ind": float(g[g.induced == 1].patent_any.mean()),
                "pat_ctl": float(g[g.induced == 0].patent_any.mean()), "A": a, "B": b}
    print(f"  {f:26} {ni:>7,} {nc:>7,} {strat[f]['pat_ind']*100:>8.1f}% "
          f"{strat[f]['pat_ctl']*100:>8.1f}% {fmt(a):>18} {fmt(b):>18}", flush=True)

# 교호작용 LR검정: 유발효과가 분야마다 다른가?
print("\n  [교호작용 LR검정] H0: 유발효과가 모든 분야에서 동일", flush=True)
inter = {}
big = [f for f in strat]
sub = prep(df[df.field.isin(big)])
for lab, f0, f1 in [
    ("모델A", f"patent_any ~ induced + {COV}", f"patent_any ~ induced*C(field) + C(collab)+C(year)"),
    ("모델B", f"patent_any ~ induced + logTC + {COV}",
     f"patent_any ~ induced*C(field) + logTC + C(collab)+C(year)"),
]:
    m0, m1 = fit(f0, sub), fit(f1, sub)
    lr = float(m0.deviance - m1.deviance); ddf = int(m0.df_resid - m1.df_resid)
    p = float(sm.stats.stattools.stats.chi2.sf(lr, ddf)) if ddf > 0 else float("nan")
    inter[lab] = {"LR": lr, "df": ddf, "p": p}
    print(f"    {lab}: LR={lr:.1f}, df={ddf}, p={p:.2e}  "
          f"→ {'분야별로 다름(이질성 있음)' if p < .05 else '동질성 기각 못함'}", flush=True)

RES["strat_field"] = strat
RES["interaction"] = inter

# IBS 핵심 결과의 분야별 재확인
print("\n  [IBS 분야별 모델B] 핵심 결과가 특정 분야에서만 나오는가?", flush=True)
ibs_strat = {}
nonind = df[df.induced == 0]
ibs = PD.apply(df_all[(df_all.induced == 1) & (df_all.ibs == 1)], "ibs", FLAGS, MODE)
for f in sorted(set(ibs.field)):
    gi = ibs[ibs.field == f]; gc = nonind[nonind.field == f]
    if len(gi) < 200 or len(gc) < 200 or gi.patent_any.sum() < 10 or gc.patent_any.sum() < 10:
        continue
    g = pd.concat([gi, gc])
    try:
        b = orci(fit("patent_any ~ induced + logTC + C(collab)+C(year)", g))
    except Exception:
        continue
    ibs_strat[f] = {"n_ind": len(gi), "B": b}
    print(f"    {f:26} n={len(gi):>6,}  모델B aOR {fmt(b)}", flush=True)
RES["strat_field_ibs"] = ibs_strat

# ─────────────────────────────────────────────────────────────
# ② 공통 지지 — 셀 커버리지 진단
# ─────────────────────────────────────────────────────────────
print("\n=== ② 공통 지지: field×collab×year 셀 커버리지 ===", flush=True)
cell = df.groupby(["field", "collab", "year"]).agg(ni=("induced", "sum"),
                                                   n=("induced", "size")).reset_index()
cell["nc"] = cell["n"] - cell["ni"]
orphan_i = cell[(cell.ni > 0) & (cell.nc == 0)]
orphan_c = cell[(cell.ni == 0) & (cell.nc > 0)]
sup = {
    "cells": int(len(cell)),
    "cells_both": int(((cell.ni > 0) & (cell.nc > 0)).sum()),
    "ind_in_orphan_cells": int(orphan_i.ni.sum()),
    "ind_orphan_pct": float(orphan_i.ni.sum() / cell.ni.sum() * 100),
    "ctl_in_orphan_cells": int(orphan_c.nc.sum()),
    "ctl_orphan_pct": float(orphan_c.nc.sum() / cell.nc.sum() * 100),
}
print(f"  전체 셀 {sup['cells']:,} / 양쪽 다 존재 {sup['cells_both']:,}", flush=True)
print(f"  대조군 짝이 전혀 없는 셀의 유발논문: {sup['ind_in_orphan_cells']:,}편 "
      f"({sup['ind_orphan_pct']:.2f}%)", flush=True)
print(f"  유발 짝이 전혀 없는 셀의 대조논문:   {sup['ctl_in_orphan_cells']:,}편 "
      f"({sup['ctl_orphan_pct']:.2f}%)", flush=True)
RES["support"] = sup

# ─────────────────────────────────────────────────────────────
# ②-b 성향점수매칭 (캘리퍼 1:1, 비복원) — 외삽 없는 재현
# ─────────────────────────────────────────────────────────────
def _find(a, i):
    r = i
    while a[r] != r:
        r = a[r]
    while a[i] != r:
        a[i], i = r, a[i]
    return r


def psmatch(sub, ps_formula, seed=SEED, caliper_sd=0.2):
    """선형성향점수(logit) 기준 캘리퍼 1:1 비복원 최근접 매칭. 반환: 매칭표, 진단."""
    sub = sub.reset_index(drop=True)
    X = dmatrix(ps_formula, sub, return_type="dataframe")
    ps = sm.GLM(sub["induced"].values, X, family=sm.families.Binomial()).fit()
    lp = np.asarray(X @ ps.params, dtype=float)            # 선형예측자 = logit(PS)
    cal = caliper_sd * lp.std()

    t = np.where(sub.induced.values == 1)[0]
    c = np.where(sub.induced.values == 0)[0]
    order_c = c[np.argsort(lp[c])]
    cv = lp[order_c]; n = len(order_c)
    R = np.arange(n + 1); L = np.arange(n + 1)             # R: ≥i 최소가용, L: ≤i-1 최대가용
    rng = np.random.default_rng(seed)
    pairs_t, pairs_c = [], []
    for ti in rng.permutation(t):
        pos = int(np.searchsorted(cv, lp[ti]))
        rj = _find(R, min(pos, n)); best, bd = -1, np.inf
        if rj < n:
            best, bd = rj, abs(cv[rj] - lp[ti])
        lj = _find(L, pos)
        if lj > 0:
            d = abs(cv[lj - 1] - lp[ti])
            if d < bd:
                best, bd = lj - 1, d
        if best >= 0 and bd <= cal:
            pairs_t.append(ti); pairs_c.append(order_c[best])
            R[best] = best + 1; L[best + 1] = best         # 사용 처리
    m = pd.concat([sub.iloc[pairs_t], sub.iloc[pairs_c]])

    # 균형: 설계행렬 표준화평균차(SMD)
    def smd(idx_t, idx_c):
        A, B = X.values[idx_t], X.values[idx_c]
        s = np.sqrt((A.var(0) + B.var(0)) / 2)
        with np.errstate(divide="ignore", invalid="ignore"):
            d = np.abs(A.mean(0) - B.mean(0)) / s
        return float(np.nanmax(np.where(np.isfinite(d), d, np.nan)[1:]))

    return m, {"n_treated": int(len(t)), "n_matched": int(len(pairs_t)),
               "match_rate": float(len(pairs_t) / len(t) * 100),
               "caliper": float(cal),
               "smd_before": smd(t, c), "smd_after": smd(np.array(pairs_t), np.array(pairs_c)),
               "lp_overlap": [float(max(lp[t].min(), lp[c].min())),
                              float(min(lp[t].max(), lp[c].max()))]}


print("\n=== ②-b 성향점수매칭(캘리퍼 0.2·1:1·비복원) 재현 ===", flush=True)
print(f"  {'그룹':10} {'매칭률':>8} {'maxSMD 전→후':>16} {'PSM 모델A':>18} {'PSM 모델B':>18} "
      f"{'회귀 모델B(참고)':>18}", flush=True)
psm_res = {}
for name, sub in groups():
    s = prep(sub)
    try:
        mA, dA = psmatch(s, COV)                       # 모델A: 분야·협력·연도만 매칭
        mB, dB = psmatch(s, f"{COV}+logTC")            # 모델B: 학술인용까지 매칭
        # 매칭표본 내 이중강건 추정(매칭 후 잔여 불균형을 회귀로 한 번 더 조정)
        oa = orci(fit(f"patent_any ~ induced + {COV}", prep(mA)))
        ob = orci(fit(f"patent_any ~ induced + logTC + {COV}", prep(mB)))
        oref = orci(fit(f"patent_any ~ induced + logTC + {COV}", s))
        psm_res[name] = {"A": oa, "B": ob, "reg_B": oref, "diagA": dA, "diagB": dB,
                         "raw_A": [float(mA[mA.induced == 1].patent_any.mean()),
                                   float(mA[mA.induced == 0].patent_any.mean())]}
        print(f"  {name:10} {dB['match_rate']:>7.1f}% "
              f"{dB['smd_before']:>7.2f}→{dB['smd_after']:<8.2f} {fmt(oa):>18} {fmt(ob):>18} "
              f"{fmt(oref):>18}", flush=True)
    except Exception as e:
        print(f"  {name:10} 실패: {type(e).__name__}: {e}", flush=True)
RES["psm"] = psm_res

# ─────────────────────────────────────────────────────────────
# ③ 함수형 유연화 — logTC 선형 vs 십분위 더미 vs 스플라인
# ─────────────────────────────────────────────────────────────
print("\n=== ③ 함수형: 모델B의 학술인용 통제 방식 변경 ===", flush=True)
print(f"  {'그룹':10} {'선형 logTC':>18} {'TC 십분위더미':>18} {'스플라인(df=5)':>18}", flush=True)
fnl = {}
for name, sub in groups():
    s = prep(sub)
    r = {}
    for lab, term in [("linear", "logTC"), ("decile", "C(tcdec)"), ("spline", "bs(logTC, df=5)")]:
        try:
            r[lab] = orci(fit(f"patent_any ~ induced + {term} + {COV}", s))
        except Exception:
            r[lab] = None
    fnl[name] = r
    print(f"  {name:10} {fmt(r['linear']):>18} {fmt(r['decile']):>18} {fmt(r['spline']):>18}",
          flush=True)
RES["functional"] = fnl

json.dump(RES, open(f"{P}/patcit_hetero_{MODE}.json", "w"), ensure_ascii=False, indent=1, default=float)
print(f"\n저장: data_2025/patcit_hetero_{MODE}.json", flush=True)
print("※ ①에서 교호작용 유의 = 분야별 층화표를 본문/부록에 함께 제시할 것.", flush=True)
print("※ ②에서 PSM 결과가 회귀와 같은 방향·유의성이면 외삽 의존 아님.", flush=True)
print("※ ③에서 세 방식 aOR이 유사하면 함수형 가정에 강건.", flush=True)
