#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""본작업 3 강건성: 결과변수 변형(front/intext/고신뢰도) + 카운트모델(Poisson/NB).
핵심 질문 유지: 학술인용(logTC) 통제 후에도 유발 특허파급이 남는가 — 특히 IBS.
현재 데이터(대조군 64%)로 예비. 대조군 완료 후 재실행 가능.
"""
import os, json
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
import patcit_defs as PD

P = "/home/user/KISTI_Policy/data_2025"
PCS = "/media/user/df9db4f3-386b-4bd4-b1bf-fcebb530b180/reliance_on_science/pcs_oa_uspto.csv"

df = pd.read_pickle(f"{P}/.patcit_df.pkl")   # UT,induced,patcit,TC,field,collab,year,kisti..pal,patent_any,logTC
# UT -> oaid
ind = json.load(open(f"{P}/oaid_induced.json")); ctl = json.load(open(f"{P}/oaid_control.json"))
ut2oaid = {ut: v["oaid"] for ut, v in {**ctl, **ind}.items()}
df["oaid"] = df["UT"].map(ut2oaid)
want = set(df["oaid"].dropna())

# patcit_paper: oaid->[total,front,intext]
pp = json.load(open(f"{P}/patcit_paper.json"))
df["front"] = df["oaid"].map(lambda o: pp.get(o, [0, 0, 0])[1] if o in pp else 0)
df["intext"] = df["oaid"].map(lambda o: pp.get(o, [0, 0, 0])[2] if o in pp else 0)

# 고신뢰도(confscore>=8) 재스트리밍
print("[*] confscore>=8 재집계(35M행 스트리밍)", flush=True)
hi = {}
with open(PCS) as f:
    next(f)
    for line in f:
        p = line.split(",")
        if len(p) < 5: continue
        if p[2] in want:
            try: sc = int(p[1])
            except: sc = 0
            if sc >= 8: hi[p[2]] = hi.get(p[2], 0) + 1
df["hiconf"] = df["oaid"].map(lambda o: hi.get(o, 0))
for c in ("front", "intext", "hiconf"):
    df[c + "_any"] = (df[c] >= 1).astype(int)

def prep(sub):
    sub = sub.copy()
    ev = sub.groupby("field")["patent_any"].sum()
    rare = set(ev[ev < 5].index)
    if rare: sub["field"] = sub["field"].where(~sub["field"].isin(rare), "Other")
    return sub

FML = "{y} ~ induced + logTC + C(field)+C(collab)+C(year)"
def logit_or(sub, y):
    try:
        m = smf.glm(FML.format(y=y), data=sub, family=sm.families.Binomial()).fit()
        c = m.params["induced"]; ci = m.conf_int().loc["induced"]
        return f"{np.exp(c):.2f} ({np.exp(ci[0]):.2f}-{np.exp(ci[1]):.2f})"
    except Exception as e:
        return f"실패({type(e).__name__})"
def nb_irr(sub, alpha=1.0):
    try:
        m = smf.glm("patcit ~ induced + logTC + C(field)+C(collab)+C(year)",
                    data=sub, family=sm.families.NegativeBinomial(alpha=alpha)).fit()
        c = m.params["induced"]; ci = m.conf_int().loc["induced"]
        return f"{np.exp(c):.2f} ({np.exp(ci[0]):.2f}-{np.exp(ci[1]):.2f})"
    except Exception as e:
        return f"실패({type(e).__name__})"

MODE = PD.mode()
FLAGS = PD.load_flags() if MODE == "external" else None
LBL = {"external": "개정(외부 유발논문만)", "all": "현행(전체 유발논문)"}[MODE]
print(f"[*] 유발논문 정의: {LBL}", flush=True)
nonind = df[df.induced == 0]
groups = [("유발전체", PD.apply(df, None, FLAGS, MODE))]
for o in ("kisti", "ibs", "pal", "kbsi"):
    sub = pd.concat([df[(df.induced == 1) & (df[o] == 1)], nonind])
    groups.append((o.upper(), PD.apply(sub, o, FLAGS, MODE)))

print("\n=== 강건성① 결과변수 변형 (모델B: +학술인용 통제, aOR) ===", flush=True)
print(f"  {'그룹':10} {'≥1인용':>16} {'front≥1':>16} {'intext≥1':>16} {'고신뢰≥1':>16}")
rob = {}
for name, sub in groups:
    s = prep(sub)
    r = {y: logit_or(s, y) for y in ("patent_any", "front_any", "intext_any", "hiconf_any")}
    rob[name] = r
    print(f"  {name:10} {r['patent_any']:>16} {r['front_any']:>16} {r['intext_any']:>16} {r['hiconf_any']:>16}", flush=True)

print("\n=== 강건성② 카운트 모델 (음이항, 특허인용 횟수, IRR) ===", flush=True)
for name, sub in groups[:3]:
    print(f"  {name:10} NB IRR = {nb_irr(prep(sub))}", flush=True)

json.dump(rob, open(f"{P}/patcit_robust_{MODE}.json", "w"), ensure_ascii=False, indent=1)
print(f"\n저장: data_2025/patcit_robust_{MODE}.json")
print("※ intext(본문인용)=더 강한 reliance 신호. IBS가 여기서도 유의하면 견고.")
