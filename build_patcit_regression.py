#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본작업 3: 유발 vs 비유발 + 유형별, USPTO 특허인용 로지스틱 회귀.
핵심 검증: 학술 인용(log TC)까지 통제한 뒤에도 유발의 특허인용 우위가 남는가?
  모델A: patent_any ~ induced + C(field)+C(collab)+C(year)              (학술인용 미통제)
  모델B: patent_any ~ induced + log(TC+1) + C(field)+C(collab)+C(year)  (학술인용 통제) ★핵심
대조: 유발 전체 / KISTI / IBS / PAL / KBSI  (각각 vs 비유발)
"""
import os, sys, pickle, json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
import patcit_defs as PD

KB = "/home/user/KISTEP"; P = "/home/user/KISTI_Policy/data_2025"
DFCACHE = f"{P}/.patcit_df.pkl"

def _fresh(cache, *deps):
    """캐시가 모든 입력보다 최신일 때만 True (대조군 갱신 시 자동 재빌드)."""
    if not os.path.exists(cache): return False
    ct = os.path.getmtime(cache)
    return all(os.path.exists(d) and os.path.getmtime(d) <= ct for d in deps)

if _fresh(DFCACHE, f"{P}/oaid_control.json", f"{P}/oaid_induced.json", f"{P}/patcit_paper.json"):
    print("[1-2] df 캐시 로드(입력 최신 확인)", flush=True)
    df = pd.read_pickle(DFCACHE)
else:
    print("[1] wos_data + ESI 재매핑", flush=True)
    wos = pickle.load(open(f"{KB}/generated/2026/wos_data.pkl", "rb"))
    esi = pickle.load(open(f"{KB}/generated/master/esi_journal_map.pkl", "rb"))
    E = {"Environment/Ecology": "Environment Ecology", "Psychiatry/Psychology": "Psychiatry Psychology"}
    def fld(r):
        s = (r.get("SN") or "").strip(); e = (r.get("EI") or "").strip()
        x = esi.get(s) or esi.get(e); return E.get(x, x) if x else r.get("std_field")
    meta = {}
    for r in wos:
        ut = r.get("UT"); py = r.get("PY"); ct = r.get("collab_type"); f = fld(r)
        if ut and isinstance(py, int) and 2011 <= py <= 2025 and ct and f:
            meta[ut] = (f, ct, py, r.get("TC", 0) or 0)
    print(f"    meta UT={len(meta):,}", flush=True)

    print("[2] oaid·특허인용·기관 로드", flush=True)
    ind = json.load(open(f"{P}/oaid_induced.json"))
    ctl = json.load(open(f"{P}/oaid_control.json"))
    cnt = json.load(open(f"{P}/patcit_paper.json"))
    org_ut = {o: {x["UT"] for x in json.load(open(f"{P}/{o}_induced_papers.json"))}
              for o in ("kisti", "kbsi", "ibs", "pal")}
    def patn(oaid): return cnt.get(oaid, [0])[0]
    rows = []
    for ut, v in ind.items():
        if ut not in meta: continue
        f, ct, py, tc = meta[ut]
        rows.append((ut, 1, patn(v["oaid"]), tc, f, ct, py,
                     int(ut in org_ut["kisti"]), int(ut in org_ut["kbsi"]),
                     int(ut in org_ut["ibs"]), int(ut in org_ut["pal"])))
    for ut, v in ctl.items():
        if ut not in meta: continue
        f, ct, py, tc = meta[ut]
        rows.append((ut, 0, patn(v["oaid"]), tc, f, ct, py, 0, 0, 0, 0))
    df = pd.DataFrame(rows, columns=["UT", "induced", "patcit", "TC", "field", "collab", "year",
                                     "kisti", "kbsi", "ibs", "pal"])
    df["patent_any"] = (df["patcit"] >= 1).astype(int)
    df["logTC"] = np.log1p(df["TC"])
    df.to_pickle(DFCACHE)
    print("    df 캐시 저장", flush=True)
n_ind = int(df.induced.sum()); n_ctl = int((df.induced == 0).sum())
print(f"    분석표 n={len(df):,} (유발 {n_ind:,} / 비유발 {n_ctl:,})", flush=True)
print(f"    특허연계율 유발 {df[df.induced==1].patent_any.mean()*100:.2f}% vs 비유발 {df[df.induced==0].patent_any.mean()*100:.2f}%")
print(f"    평균 학술인용(TC) 유발 {df[df.induced==1].TC.mean():.1f} vs 비유발 {df[df.induced==0].TC.mean():.1f}")

def prep(sub):
    """이벤트 희소 분야를 Other로 병합해 완전분리(separation) 방지."""
    sub = sub.copy()
    ev = sub.groupby("field")["patent_any"].sum()
    rare = set(ev[ev < 5].index)
    if rare:
        sub["field"] = sub["field"].where(~sub["field"].isin(rare), "Other")
    return sub

def run(sub, label):
    sub = prep(sub)
    def fit(formula):
        # GLM(IRLS)로 안정 추정
        return smf.glm(formula, data=sub, family=sm.families.Binomial()).fit()
    def orci(m):
        c = m.params["induced"]; ci = m.conf_int().loc["induced"]
        return np.exp(c), np.exp(ci[0]), np.exp(ci[1])
    try:
        oa = orci(fit("patent_any ~ induced + C(field)+C(collab)+C(year)"))
        ob = orci(fit("patent_any ~ induced + logTC + C(field)+C(collab)+C(year)"))
    except Exception as e:
        print(f"  {label:12} | 실패: {e}", flush=True)
        return {"A": None, "B": None, "n": len(sub)}
    print(f"  {label:12} | 모델A aOR {oa[0]:.2f} ({oa[1]:.2f}-{oa[2]:.2f}) "
          f"| 모델B(+학술인용) aOR {ob[0]:.2f} ({ob[1]:.2f}-{ob[2]:.2f})", flush=True)
    return {"A": oa, "B": ob, "n": len(sub)}

MODE = PD.mode()
FLAGS = PD.load_flags() if MODE == "external" else None
LBL = {"external": "개정(외부 유발논문만)", "all": "현행(전체 유발논문)"}[MODE]
print(f"\n[3] 로지스틱 회귀 (결과=특허 ≥1 인용) — 각 vs 비유발  |  정의: {LBL}", flush=True)
nonind = df[df.induced == 0]
res = {}
res["induced_all"] = run(PD.apply(df, None, FLAGS, MODE), "유발 전체")
for o in ("kisti", "ibs", "pal", "kbsi"):
    sub = pd.concat([df[(df.induced == 1) & (df[o] == 1)].assign(induced=1), nonind])
    res[o.upper()] = run(PD.apply(sub, o, FLAGS, MODE), o.upper())

# logTC 계수(참고): 학술인용 1 로그단위↑ 시 특허인용 오즈비
mB = smf.glm("patent_any ~ induced + logTC + C(field)+C(collab)+C(year)",
             data=prep(PD.apply(df, None, FLAGS, MODE)), family=sm.families.Binomial()).fit()
print(f"\n  [참고] logTC 오즈비 = {np.exp(mB.params['logTC']):.2f} (학술인용↑→특허인용↑, 예상대로 강함)")
json.dump({k: {kk: list(vv) if isinstance(vv, tuple) else vv for kk, vv in v.items()}
           for k, v in res.items()}, open(f"{P}/patcit_regression_{MODE}.json", "w"), indent=1)
print(f"\n저장: data_2025/patcit_regression_{MODE}.json")
print("※ 모델B에서 유발 aOR>1·유의 = 학술영향력으로 설명 안 되는 별도 기술파급.")
print(f"※ 유발논문 정의: {LBL}. 다른 정의는 INDUCED_DEF=all|external 로 재실행.")
