#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
graphical_abstract.py — AI Magazine 그래픽 초록용 개념도 (50 x 60 mm)

50x60mm 에서 완전히 읽혀야 하므로 축·눈금·범례가 있는 데이터 그림은 쓸 수 없다.
이 연구의 핵심은 '같은 크기의 두 코퍼스, 하나는 덮고 하나는 못 덮는다'는 구조적
대비이므로 도식으로 그린다. 칸 하나가 문서 하나, 진한 칸이 정답 근거를 담은 문서다.
두 격자의 칸 수가 같은데 진한 칸의 유무만 다르다는 것이 한눈에 보인다.

텍스트 요소를 일곱 개로 줄여 최소 글자를 6pt(2.1mm)로 유지했고,
저장 전에 캔버스 이탈·텍스트 겹침·격자 침범을 모두 검사한다.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MM = 1 / 25.4
W_MM, H_MM = 50.0, 60.0
C_EVID, C_PERI = "#1f4e79", "#c9d6e2"
C_TEXT, C_HI, C_SUB = "#1a1a1a", "#b3202c", "#555555"
MIN_PT = 6.0
CELL, GAP, COLS = 0.075, 0.013, 4

fig = plt.figure(figsize=(W_MM * MM, H_MM * MM), dpi=600)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
texts, grids = [], []

def T(x, y, s, size, color=C_TEXT, weight="normal"):
    assert size >= MIN_PT, f"{size}pt < {MIN_PT}pt: {s}"
    texts.append(ax.text(x, y, s, fontsize=size, color=color, weight=weight,
                         ha="center", va="center"))

def grid(x0, y_top, n_evid, n_total=12):
    for i in range(n_total):
        r, c = divmod(i, COLS)
        ax.add_patch(Rectangle((x0 + c * (CELL + GAP), y_top - r * (CELL + GAP) - CELL),
                               CELL, CELL,
                               facecolor=C_EVID if i < n_evid else C_PERI,
                               edgecolor="white", linewidth=0.7))
    rows = (n_total + COLS - 1) // COLS
    box = (x0, x0 + COLS * (CELL + GAP) - GAP, y_top - rows * (CELL + GAP) + GAP, y_top)
    grids.append(box); return box

T(0.5, 0.958, "Two corpora, the same size", 7.5, weight="bold")

# 위 — 근거 유지, 주변부 제거
T(0.255, 0.878, "evidence kept", 6.5, C_SUB)
gA = grid(0.055, 0.835, n_evid=3)
T(0.78, 0.878, "correct citations", 6.0, C_SUB)
T(0.78, 0.740, "89%", 17.0, C_EVID, "bold")

ax.plot([0.06, 0.94], [0.545, 0.545], color="#cccccc", linewidth=0.7)

# 아래 — 근거 제거, 주변부 유지
T(0.275, 0.498, "evidence removed", 6.5, C_SUB)
gB = grid(0.055, 0.455, n_evid=0)
T(0.78, 0.335, "12%", 17.0, C_HI, "bold")

T(0.5, 0.075, "Coverage, not corpus size", 7.5, weight="bold")

# ---------------- 검증
fig.canvas.draw()
inv = ax.transData.inverted()
boxes, bad = [], []
for t in texts:
    bb = t.get_window_extent(fig.canvas.get_renderer())
    (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
    boxes.append((t.get_text()[:22], x0, x1, y0, y1))
    if x0 < 0.01 or x1 > 0.99 or y0 < 0.005 or y1 > 0.995:
        bad.append(t.get_text()[:22])

def hit(a, b):
    return a[1] < b[2] and b[1] < a[2] and a[3] < b[4] and b[3] < a[4]

ov = [(a[0], b[0]) for i, a in enumerate(boxes) for b in boxes[i+1:] if hit(a, b)]
gov = [(t[0], f"grid{k+1}") for t in boxes for k, g in enumerate(grids)
       if t[1] < g[1] and g[0] < t[2] and t[3] < g[3] and g[2] < t[4]]
print("캔버스 이탈:", bad or "없음")
print("텍스트 겹침:", ov or "없음")
print("격자 침범:", gov or "없음")
print("최소 글자 %.1fpt = %.2f mm" % (MIN_PT, MIN_PT / 72 * 25.4))
assert not (bad or ov or gov), "배치 충돌"

fig.savefig("graphical_abstract.png", dpi=600, facecolor="white")
fig.savefig("graphical_abstract.pdf", facecolor="white")
print("저장 완료 (%.0f x %.0f mm)" % (W_MM, H_MM))
