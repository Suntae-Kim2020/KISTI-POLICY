#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""논문1 개정 설계 그림 3종 생성 → fig/paper1_fig{1,2,3}.png

그림1 집단 구성 흐름도 (2×2 개념도)
그림2 분야별 조정 오즈비 숲그림 (국내·세계 기준 병기)   ★ 본문
그림3 상위 진입률 비교 막대그림 (무작위 기대치 기준선 표시)

색: 기본 카테고리 팔레트 slot1(파랑)·slot2(주황) 고정 순서 사용.
    두 계열은 색뿐 아니라 마커 모양(원/마름모)으로도 구분해 색 단독 식별을 피한다.
실행: .venv/bin/python gen_paper1_figs.py
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "fig"); os.makedirs(FIG, exist_ok=True)
P = os.path.join(HERE, "data_2025")

path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
fm.fontManager.addfont(path)
plt.rcParams["font.family"] = fm.FontProperties(fname=path).get_name()
plt.rcParams["axes.unicode_minus"] = False

KR, WD = "#2a78d6", "#eb6834"          # 카테고리 slot1 / slot2
INK, INK2, MUT, LINE = "#0b0b0b", "#52514e", "#8a8880", "#dcdcd8"
SURF = "#ffffff"

kr = json.load(open(f"{P}/paper1_regression_kr.json"))
wd = json.load(open(f"{P}/paper1_regression_world.json"))
KO = {"Agricultural Sciences": "농업과학", "Biology & Biochemistry": "생물·생화학",
      "Chemistry": "화학", "Clinical Medicine": "임상의학", "Computer Science": "전산학",
      "Engineering": "공학", "Environment Ecology": "환경·생태", "Geosciences": "지구과학",
      "Materials Science": "재료과학", "Mathematics": "수학", "Microbiology": "미생물학",
      "Molecular Biology & Genetics": "분자생물·유전", "Multidisciplinary": "다학제",
      "Neuroscience & Behavior": "신경과학", "Pharmacology & Toxicology": "약리·독성",
      "Physics": "물리", "Plant & Animal Science": "식물·동물", "Space Science": "우주과학"}


# ── 그림 1. 집단 구성 (2×2 행렬) ─────────────────────────────
def fig1():
    fig, ax = plt.subplots(figsize=(9.4, 4.9), dpi=300)
    ax.set_xlim(0, 12); ax.set_ylim(0, 7.2); ax.axis("off")
    X0, Y0, W, H, GX, GY = 3.05, 1.15, 3.9, 1.95, 0.28, 0.28
    cells = [(0, 1, "ⓐ", "13,242편", False), (1, 1, "ⓑ", "14,640편", False),
             (0, 0, "ⓒ", "21,967편", True), (1, 0, "ⓓ", "930,548편", False)]
    for col, row, tag, cnt, hi in cells:
        x = X0 + col * (W + GX); y = Y0 + row * (H + GY)
        ax.add_patch(FancyBboxPatch((x, y), W, H, boxstyle="round,pad=0.02,rounding_size=0.14",
                                    facecolor=(KR if hi else SURF), edgecolor=(KR if hi else LINE),
                                    linewidth=1.3))
        ax.text(x + W / 2, y + H * (0.60 if hi else 0.50), f"{tag}  {cnt}",
                ha="center", va="center", fontsize=15,
                color=("white" if hi else INK), fontweight="bold")
        if hi:
            ax.text(x + W / 2, y + H * 0.26, "처치군 · 외부 연계논문", ha="center", va="center",
                    fontsize=10.5, color="white")
    # 열 머리글
    for col, lab in [(0, "인프라 사사표기  있음"), (1, "인프라 사사표기  없음")]:
        ax.text(X0 + col * (W + GX) + W / 2, Y0 + 2 * H + GY + 0.30, lab,
                ha="center", va="bottom", fontsize=11.5, color=INK2, fontweight="bold")
    # 행 머리글
    for row, lab in [(1, "기관 소속 저자\n있음"), (0, "기관 소속 저자\n없음")]:
        ax.text(X0 - 0.38, Y0 + row * (H + GY) + H / 2, lab, ha="right", va="center",
                fontsize=11.5, color=INK2, fontweight="bold", linespacing=1.6)
    ax.text(0.0, 6.62, "국내 논문 980,397편 (2011–2025)", fontsize=13, color=INK, fontweight="bold")
    ax.text(0.0, 0.18, "주) 회귀분석에는 연구분야·협력유형 결측 5,585편(0.6%)을 제외한 974,812편 사용. "
                       "비교군은 ⓐ+ⓑ+ⓓ.", fontsize=9, color=MUT)
    fig.savefig(f"{FIG}/paper1_fig1.png", facecolor=SURF, bbox_inches="tight")
    plt.close(fig); print("  fig/paper1_fig1.png")


# ── 그림 2. 분야별 숲그림 ────────────────────────────────────
def fig2():
    fs = sorted(kr["by_field_top10"], key=lambda f: -kr["by_field_top10"][f]["aOR"][0])
    n = len(fs)
    fig, ax = plt.subplots(figsize=(9.4, 7.4), dpi=300)
    off = 0.19
    for i, f in enumerate(fs):
        y = n - 1 - i
        for src, color, mk, dy, lab in ((kr, KR, "o", off, "국내"), (wd, WD, "D", -off, "세계")):
            r = src["by_field_top10"].get(f)
            if not r:
                continue
            e, lo, hi = r["aOR"]
            ax.errorbar(e, y + dy, xerr=[[e - lo], [hi - e]], fmt=mk, color=color, ecolor=color,
                        elinewidth=1.6, capsize=0, markersize=6.5,
                        markeredgecolor=SURF, markeredgewidth=0.9, zorder=3)
            ax.text(hi + 0.06, y + dy, f"{e:.2f}", va="center", ha="left", fontsize=8.2, color=INK2)
    ax.axvline(1, ls="--", color=INK2, lw=1.2, zorder=1)
    ax.text(1, n - 0.25, "aOR = 1 (차이 없음)", ha="center", va="bottom",
            fontsize=9, color=INK2, fontweight="bold")
    ax.set_xscale("log")
    ticks = [0.8, 1, 1.5, 2, 3, 4, 6]
    ax.set_xticks(ticks); ax.set_xticklabels([str(t) for t in ticks], fontsize=9.5, color=MUT)
    ax.set_xlim(0.72, 8.6)
    ax.set_yticks(range(n)); ax.set_yticklabels([KO.get(f, f) for f in fs][::-1],
                                                fontsize=10.5, color=INK)
    ax.set_ylim(-0.7, n - 0.3)
    ax.tick_params(length=0)
    ax.set_xlabel("조정 오즈비 (로그 눈금) · 95% 신뢰구간", fontsize=10.5, color=INK2)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.grid(axis="x", color=LINE, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    leg = [Line2D([0], [0], marker="o", color="w", markerfacecolor=KR, markersize=8,
                  label="국내 기준 상위 10%"),
           Line2D([0], [0], marker="D", color="w", markerfacecolor=WD, markersize=7.5,
                  label="세계 기준 상위 10%")]
    ax.legend(handles=leg, loc="lower right", fontsize=9.5, frameon=False)
    fig.tight_layout(); fig.savefig(f"{FIG}/paper1_fig2.png", facecolor=SURF, bbox_inches="tight")
    plt.close(fig); print("  fig/paper1_fig2.png")


# ── 그림 3. 상위 진입률 비교 (척도별 2패널) ─────────────────
def fig3():
    panels = [("상위 10% 진입률", 10,
               [("국내 기준", kr["main"]["kr_top10"]), ("세계 기준", wd["main"]["w_top10"])], 42),
              ("상위 1% 진입률", 1,
               [("국내 기준", kr["main"]["kr_top1"]), ("세계 기준", wd["main"]["w_top1"])], 6.2)]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.3), dpi=300,
                             gridspec_kw={"wspace": 0.28})
    for ax, (title, ref, items, ymax) in zip(axes, panels):
        x = np.arange(len(items)); w = 0.32
        for xs, key, color, lab in ((x - w / 2 - 0.015, "raw_treat_pct", KR, "처치군 (외부 연계논문)"),
                                    (x + w / 2 + 0.015, "raw_ctrl_pct", MUT, "비교군 (나머지 국내 논문)")):
            v = [d[key] for _, d in items]
            ax.bar(xs, v, w, color=color, label=lab, zorder=3, linewidth=0)
            for xi, val in zip(xs, v):
                ax.text(xi, val + ymax * 0.018, f"{val:.1f}%", ha="center", va="bottom",
                        fontsize=10, color=INK2)
        ax.axhline(ref, ls=":", color=INK2, lw=1.3, zorder=4)
        ax.text(len(items) - 0.42, ref + ymax * 0.015, f"무작위 기대치 {ref}%",
                ha="right", va="bottom", fontsize=8.8, color=INK2)
        ax.set_title(title, fontsize=12, color=INK, fontweight="bold", pad=10)
        ax.set_xticks(x); ax.set_xticklabels([n for n, _ in items], fontsize=11, color=INK)
        ax.set_ylim(0, ymax)
        ax.tick_params(length=0, labelsize=9.5, labelcolor=MUT)
        ax.tick_params(axis="x", labelcolor=INK)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(LINE)
        ax.grid(axis="y", color=LINE, lw=0.6, zorder=0); ax.set_axisbelow(True)
    axes[0].set_ylabel("진입률 (%)", fontsize=10.5, color=INK2, labelpad=16)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, fontsize=10, frameon=False, loc="lower center",
               ncol=2, bbox_to_anchor=(0.5, -0.04))
    fig.savefig(f"{FIG}/paper1_fig3.png", facecolor=SURF, bbox_inches="tight")
    plt.close(fig); print("  fig/paper1_fig3.png")


print("그림 생성:")
fig1(); fig2(); fig3()
print("완료")
