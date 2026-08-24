#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""표7 forest plot(그림1)을 matplotlib로 선명하게(300 DPI) 렌더 → fig/forest.png.
한글 폰트: Noto Sans CJK. 실행: /home/user/KISTI_Policy/.venv/bin/python gen_forest.py
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.ticker import NullLocator, FixedLocator, FixedFormatter
from matplotlib.lines import Line2D
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fig", "forest.png")

path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
fm.fontManager.addfont(path)
plt.rcParams["font.family"] = fm.FontProperties(fname=path).get_name()
plt.rcParams["axes.unicode_minus"] = False

rows = [("KISTI · 계산", (2.74, 2.63, 2.85), (3.33, 3.02, 3.69)),
        ("인프라 전체(4기관)", (2.04, 1.98, 2.10), (2.44, 2.26, 2.64)),
        ("IBS · 기초연구", (2.19, 2.08, 2.31), (2.74, 2.41, 3.12)),
        ("PAL · 빔라인", (1.43, 1.29, 1.59), (1.76, 1.32, 2.34)),
        ("KBSI · 분석장비", (1.21, 1.13, 1.29), (0.97, 0.76, 1.23))]
AC, AM, INK, INK2, MUT, LINE = "#2a5db0", "#a9690a", "#1a1f2b", "#46505f", "#7b8494", "#d3d8e2"

fig, ax = plt.subplots(figsize=(10.6, 4.5), dpi=300)
n = len(rows); ys = np.arange(n)[::-1]; off = 0.16
for y, (lab, t10, t1) in zip(ys, rows):
    for (e, lo, hi), color, mk, dy, ms in [(t10, AC, 'o', off, 7), (t1, AM, 'D', -off, 6.5)]:
        ax.errorbar(e, y + dy, xerr=[[e - lo], [hi - e]], fmt=mk, color=color, ecolor=color,
                    elinewidth=1.8, capsize=3.5, capthick=1.8, markersize=ms,
                    markeredgecolor="white", markeredgewidth=0.8, zorder=3)
        ax.text(hi + 0.05, y + dy, f"{e:.2f}", va="center", ha="left", fontsize=9, color=INK2)

ax.axvline(1, ls="--", color=INK2, lw=1.3, zorder=1)
ax.text(1, n - 0.35, "OR=1 (차이 없음)", ha="center", va="bottom", fontsize=9.5, color=INK2, fontweight="bold")

ax.set_xscale("log")
ticks = [0.7, 1, 1.5, 2, 2.5, 3, 3.5]
ax.xaxis.set_minor_locator(NullLocator())
ax.xaxis.set_major_locator(FixedLocator(ticks))
ax.xaxis.set_major_formatter(FixedFormatter([f"{t:g}" for t in ticks]))
ax.set_xlim(0.62, 4.0)
ax.tick_params(axis="x", labelsize=9.5, labelcolor=MUT, length=0)

ax.set_yticks(ys); ax.set_yticklabels([r[0] for r in rows], fontsize=11.5, color=INK, fontweight="bold")
ax.set_ylim(-0.6, n - 0.4)
ax.set_xlabel("조정 오즈비 (aOR, 로그 눈금) · 95% 신뢰구간", fontsize=11, color=INK2)
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(LINE)
ax.tick_params(axis="y", length=0)
ax.grid(axis="x", color=LINE, lw=0.7, zorder=0)
ax.set_axisbelow(True)

leg = [Line2D([0], [0], marker='o', color='w', markerfacecolor=AC, markersize=8, label='상위 10% aOR'),
       Line2D([0], [0], marker='D', color='w', markerfacecolor=AM, markersize=8, label='상위 1% aOR')]
ax.legend(handles=leg, loc="lower right", fontsize=9.5, frameon=False)

plt.tight_layout()
fig.savefig(OUT, dpi=300, facecolor="white", bbox_inches="tight", pad_inches=0.08)
from PIL import Image
print("saved", OUT, Image.open(OUT).size)
