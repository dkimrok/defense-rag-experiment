#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fig4_framework.py — 커버리지 감사 절차 흐름도 (Figure 4)

명명 규칙
  'coverage audit' 은 일곱 단계 전체(= 그림 제목)에만 쓴다.
  2단계는 'Evidence check', 2~5단계 묶음은 'Corpus-side audits' 로 구분한다.
  7단계는 표와 동일하게 'Model metacognition test' 이며, model selection 은
  그 시험이 이끄는 하류 결정으로 따로 둔다. Deployment 와 인용 검증은
  본 연구가 근거를 대지 못하므로 점선으로 표시한다.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

C_MAIN, C_AUDIT, C_OPEN = "#1f4e79", "#e8eef4", "#f4f4f4"
C_EDGE, C_TXT, C_SUB, C_GREY = "#1f4e79", "#1a1a1a", "#555555", "#999999"

fig = plt.figure(figsize=(7.0, 4.5), dpi=400)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
rects, labels = [], []

def box(x, y, w, h, text, fill, tcol=C_TXT, fs=9, bold=False, ec=C_EDGE, ls="-", z=1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.009",
                                facecolor=fill, edgecolor=ec, linewidth=0.9,
                                linestyle=ls, zorder=z))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs,
            color=tcol, weight="bold" if bold else "normal", linespacing=1.28, zorder=z+1)
    rects.append((x, x+w, y, y+h)); labels.append(text.split('\n')[0][:30])

def down(x, y0, y1, col=C_EDGE, ls="-"):
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>", mutation_scale=9,
                                 color=col, linewidth=1.0, linestyle=ls,
                                 shrinkA=0, shrinkB=0, zorder=2))

LX, LW = 0.040, 0.365
RX, RW = 0.455, 0.505

ax.text(0.5, 0.977, "A coverage audit precedes model selection",
        ha="center", va="center", fontsize=10.5, color=C_TXT, weight="bold")

# 감사 항목 배경
ax.add_patch(FancyBboxPatch((RX, 0.430), RW, 0.400,
                            boxstyle="round,pad=0.004,rounding_size=0.009",
                            facecolor=C_AUDIT, edgecolor=C_EDGE, linewidth=0.9, zorder=0))

# 주 흐름
box(LX, 0.865, LW, 0.070, "1  Task enumeration", "white", C_MAIN, 9.0, True)
down(LX+LW/2, 0.863, 0.832)
box(LX, 0.505, LW, 0.325, "2\u20135\nCorpus-side audits", C_MAIN, "white", 10.0, True)
down(LX+LW/2, 0.503, 0.472)
box(LX, 0.400, LW, 0.070, "6  Corpus refinement", "white", C_MAIN, 9.0, True)
down(LX+LW/2, 0.398, 0.367)
box(LX, 0.278, LW, 0.087, "7  Model metacognition\ntest", "white", C_MAIN, 9.0, True)
down(LX+LW/2, 0.276, 0.245)
box(LX, 0.173, LW, 0.070, "Model selection", "white", C_SUB, 8.8, False)
down(LX+LW/2, 0.171, 0.140, C_GREY, "--")
box(LX, 0.062, LW, 0.070, "Deployment", C_OPEN, C_SUB, 8.6, False, C_GREY, "--")

# 감사 네 항목
items = [("2  Evidence check", "evidence for each query is in the index",
          "coverage OR 1.34 on attribution (p < .001)"),
         ("3  Boundary audit", "documents cited but not held",
          "49.6% of citation edges point outside"),
         ("4  Duplication audit", "near-duplicate content across documents",
          "14.6% of chunks"),
         ("5  Periphery audit", "documents never cited internally",
          "71.6% of documents")]
y = 0.786
for head, l1, l2 in items:
    ax.text(RX+0.020, y,       head, ha="left", va="center", fontsize=8.5, color=C_MAIN, weight="bold", zorder=2)
    ax.text(RX+0.020, y-0.030, l1,   ha="left", va="center", fontsize=7.3, color=C_SUB,  zorder=2)
    ax.text(RX+0.020, y-0.056, l2,   ha="left", va="center", fontsize=7.3, color=C_MAIN, zorder=2)
    y -= 0.098
ax.add_patch(FancyArrowPatch((LX+LW, 0.630), (RX, 0.630), arrowstyle="-",
                             color=C_EDGE, linewidth=0.9, zorder=2))

# 열린 문제
box(RX, 0.173, RW, 0.070,
    "Open problem  Attribution verification\npresence testing catches under 2% of failures",
    C_OPEN, C_SUB, 7.4, False, C_GREY, "--")
ax.add_patch(FancyArrowPatch((LX+LW, 0.208), (RX, 0.208), arrowstyle="-",
                             color=C_GREY, linewidth=0.8, linestyle="--", zorder=2))
ax.text(0.5, 0.020, "Dashed elements are not established by this study.",
        ha="center", va="center", fontsize=7.2, color=C_SUB, style="italic")

# ------------- 검증
oob = [l for (x0,x1,y0,y1),l in zip(rects,labels) if x0<0 or x1>1 or y0<0 or y1>1]
def hit(a,b): return a[0]<b[1] and b[0]<a[1] and a[2]<b[3] and b[2]<a[3]
ov = [(labels[i],labels[j]) for i in range(len(rects)) for j in range(i+1,len(rects))
      if hit(rects[i],rects[j])]
print("경계 이탈:", oob or "없음"); print("상자 겹침:", ov or "없음")
assert not oob and not ov
fig.savefig("fig4_framework.png", dpi=400, facecolor="white")
print("saved")
