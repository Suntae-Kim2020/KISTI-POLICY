#!/usr/bin/env python3
"""문헌유형(DT) 정규화 적용 전/후 MNCS 비교 (분석용, 대시보드 미반영).

- before: 분야×연도 정규화 (현재 대시보드 방식)
- after : 분야×연도×문헌유형(Article/Review) 정규화 (표준 FWCI 방식)
          dt 셀 표본 < MIN_DT 이면 분야×연도 베이스라인으로 폴백.
입력은 읽기전용(KISTEP wos_data + 프로젝트 data_2025 유발 JSON).
"""
import pickle, json
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
WOS = "/Users/kimsuntae/KISTEP/generated/2025/wos_data.pkl"
SY, EY = 2011, 2025
MIN_DT = 10  # dt 셀 최소 표본 (미만 시 분야×연도 폴백)


def dt_class(dt):
    return "Review" if "Review" in (dt or "") else "Article"


def is_pop(r):
    return "Early Access" not in (r.get("DT") or "")


print("wos_data 로딩…")
w = pickle.load(open(WOS, "rb"))
by_ut = {r["UT"]: r for r in w if "UT" in r}

# ── 베이스라인 구축 ──
tc_yf = defaultdict(lambda: defaultdict(list))            # [y][f] -> [tc]
tc_yfd = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # [y][f][dt] -> [tc]
for r in w:
    if not is_pop(r):
        continue
    py = r.get("PY")
    if not isinstance(py, int) or py < SY or py > EY:
        continue
    f = r.get("std_field")
    if not f:
        continue
    tc = r.get("TC", 0) or 0
    tc_yf[py][f].append(tc)
    tc_yfd[py][f][dt_class(r.get("DT"))].append(tc)

avg_yf = {y: {f: (sum(v) / len(v) if v else 0) for f, v in fs.items()} for y, fs in tc_yf.items()}
avg_yfd = {}
for y, fs in tc_yfd.items():
    avg_yfd[y] = {}
    for f, ds in fs.items():
        avg_yfd[y][f] = {}
        for dc, v in ds.items():
            if len(v) >= MIN_DT:
                avg_yfd[y][f][dc] = sum(v) / len(v)


def exp_tc_old(y, f, dc):
    return avg_yf.get(y, {}).get(f, 0)


def exp_tc_new(y, f, dc):
    cell = avg_yfd.get(y, {}).get(f, {}).get(dc)
    return cell if cell else avg_yf.get(y, {}).get(f, 0)  # 폴백


def mncs(records, exp_fn):
    vals = []
    for r in records:
        y, f, tc = r["PY"], r["std_field"], r["TC"]
        e = exp_fn(y, f, dt_class(r["DT"]))
        if e and e > 0:
            vals.append(tc / e)
    return (round(sum(vals) / len(vals), 3), len(vals)) if vals else (None, 0)


print(f"\n{'='*64}\n문헌유형 정규화 적용 전/후 MNCS 비교 (MIN_DT={MIN_DT}, 폴백)\n{'='*64}")
inst_files = {
    "KISTI": "kisti_induced_papers.json", "KBSI": "kbsi_induced_papers.json",
    "IBS": "ibs_induced_papers.json", "PAL": "pal_induced_papers.json",
}
inst_recs = {}
print(f"\n{'기관':6} {'before':>8} {'after':>8} {'Δ':>8}  {'Review%':>8}")
for inst, fn in inst_files.items():
    papers = json.load(open(PROJECT / "data_2025" / fn))
    recs = []
    for p in papers:
        r = by_ut.get(p["UT"])
        if r and is_pop(r) and isinstance(r.get("PY"), int) and SY <= r["PY"] <= EY and r.get("std_field"):
            recs.append({"PY": r["PY"], "std_field": r["std_field"],
                         "TC": r.get("TC", 0) or 0, "DT": r.get("DT", "")})
    inst_recs[inst] = recs
    mo, no = mncs(recs, exp_tc_old)
    mn, nn = mncs(recs, exp_tc_new)
    revpct = 100 * sum(1 for r in recs if dt_class(r["DT"]) == "Review") / len(recs) if recs else 0
    d = round(mn - mo, 3) if (mo and mn) else None
    print(f"{inst:6} {mo:>8} {mn:>8} {str(d):>8}  {revpct:>7.1f}%")

# ── KISTI 분야별 변화 Top ──
print(f"\n{'-'*64}\nKISTI 분야별 MNCS 변화 Top (표본 30편+)\n{'-'*64}")
byf = defaultdict(list)
for r in inst_recs["KISTI"]:
    byf[r["std_field"]].append(r)
rows = []
for f, rs in byf.items():
    if len(rs) < 30:
        continue
    mo, _ = mncs(rs, exp_tc_old)
    mn, _ = mncs(rs, exp_tc_new)
    if mo and mn:
        rows.append((f, mo, mn, round(mn - mo, 3), len(rs)))
rows.sort(key=lambda x: -abs(x[3]))
print(f"{'분야':32} {'before':>8} {'after':>8} {'Δ':>8} {'n':>6}")
for f, mo, mn, d, n in rows[:12]:
    print(f"{f:32} {mo:>8} {mn:>8} {d:>+8} {n:>6}")
