#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
38_analyze.py — 채점 결과 통계 분석

지금까지의 결과는 전부 서술 통계(표를 눈으로 비교)다. 심사에서 반드시
지적된다. 이 스크립트가 세 가지를 채운다.

  (1) 비율에 신뢰구간
      기권율·과신오답률·인용정확도는 모두 이항 비율이다. Wilson 구간을 붙인다.
      특히 범위밖 문항은 17개뿐이라 구간이 매우 넓다. 그 사실을 숨기지 않는다.

  (2) 커버리지와 분량을 분리하는 회귀   ★이 논문의 핵심 검정★
        결과 ~ 커버리지% + 문자비율% + 모델
      커버리지 축에서는 둘이 같이 움직이지만(교락), 분량 축은 커버리지를
      100%로 고정한 채 문자비율만 낮춘다. 두 축을 함께 넣으면 분리된다.
      '커버리지 계수는 유의, 문자비율 계수는 0 근처'가 나와야
      Coverage > Volume 이 서술이 아니라 검정 결과가 된다.

      분석 단위는 (문항 × 조건)이고 같은 문항이 여러 조건에 반복 등장하므로
      독립이 아니다. 문항을 클러스터로 묶은 강건표준오차를 쓴다.
      statsmodels 가 있으면 GEE(독립 작업상관 + 클러스터 강건), 없으면
      직접 구현한 로지스틱 + 클러스터 샌드위치 추정량을 쓴다.

  (3) 짝지음 대조의 대응표본 검정
      'vol055(문자55%, 커버리지100%)' 와 'cov0(문자57.9%, 커버리지0%)' 는
      같은 97문항이다. 독립표본 검정이 아니라 McNemar 가 맞다.

입력
  grade_out/graded.jsonl        23 의 출력
  cov_*/coverage_manifest.json  조건별 실제 커버리지·문자비율

출력
  analysis/analysis_report.md   본문에 붙일 표
  analysis/cell_stats.csv       조건별 비율 + CI
  analysis/regression.csv       회귀 계수

사용법
  py 38_analyze.py grade_out/graded.jsonl \\
      --covdirs cov_core,cov_periph,cov_random,cov_vol --out analysis
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

Z = 1.959963984540054          # 95%


# ---------------------------------------------------------------- 기초 통계

def short_name(m) -> str:
    t = str(m).lower()
    for k, v in [("32b", "Qwen3-32B"), ("14b", "Qwen3-14B"),
                 ("8b", "Qwen3-8B"), ("4b", "Qwen3-4B-Inst")]:
        if k in t:
            return v
    return str(m)[:18]


def wilson(k: int, n: int) -> tuple[float, float, float]:
    """Wilson 점수구간. 비율이 0/1 에 붙어도 안정적이다."""
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def fmt_ci(k: int, n: int) -> str:
    if n == 0:
        return "—"
    p, lo, hi = wilson(k, n)
    return f"{p*100:.1f}% [{lo*100:.0f}–{hi*100:.0f}] ({k}/{n})"


def mcnemar(b: int, c: int) -> tuple[float, str]:
    """대응표본 이항 검정. b, c 는 불일치 칸."""
    n = b + c
    if n == 0:
        return 1.0, "불일치 0"
    p = float(stats.binomtest(b, n, 0.5).pvalue)
    return p, f"b={b} c={c}"


# ---------------------------------------------------------------- 회귀

def logit_cluster(X: np.ndarray, y: np.ndarray, groups: np.ndarray,
                  names: list[str], maxit: int = 60):
    """로지스틱 회귀 + 문항 클러스터 강건표준오차(샌드위치).

    같은 문항이 여러 조건에 반복 등장하므로 관측치가 독립이 아니다.
    보통의 표준오차를 쓰면 과소추정되어 유의성이 부풀려진다.
    """
    n, k = X.shape
    b = np.zeros(k)
    for _ in range(maxit):                      # 뉴턴-랩슨
        eta = X @ b
        mu = 1 / (1 + np.exp(-np.clip(eta, -30, 30)))
        W = mu * (1 - mu)
        g = X.T @ (y - mu)
        H = (X * W[:, None]).T @ X
        try:
            step = np.linalg.solve(H + 1e-8 * np.eye(k), g)
        except np.linalg.LinAlgError:
            break
        b += step
        if np.max(np.abs(step)) < 1e-9:
            break
    eta = X @ b
    mu = 1 / (1 + np.exp(-np.clip(eta, -30, 30)))
    W = mu * (1 - mu)
    bread = np.linalg.pinv((X * W[:, None]).T @ X)
    meat = np.zeros((k, k))
    resid = (y - mu)[:, None] * X
    for gI in np.unique(groups):                # 클러스터별 점수 합
        s = resid[groups == gI].sum(axis=0)
        meat += np.outer(s, s)
    G = len(np.unique(groups))
    adj = G / max(G - 1, 1)
    V = bread @ meat @ bread * adj
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    z = np.divide(b, se, out=np.zeros_like(b), where=se > 0)
    p = 2 * (1 - stats.norm.cdf(np.abs(z)))
    return pd.DataFrame(dict(term=names, coef=b, se=se, z=z, p=p,
                             odds_ratio=np.exp(b),
                             ci_lo=np.exp(b - Z * se), ci_hi=np.exp(b + Z * se)))


# ---------------------------------------------------------------- 그림

def make_figures(rag, df, out: Path) -> None:
    """본문 그림 3장.

    전략(core/periph/random)은 같은 커버리지 수준에서도 문자비율이 조금씩
    달라, 그대로 그리면 선이 톱니처럼 튄다. 커버리지 수준으로 묶어
    응답을 합산(pooled)하고 문자비율은 평균을 쓴다. 오차막대는 Wilson 95%.
    라벨은 영문(한글 폰트 의존 제거).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 150, "font.size": 9,
                         "axes.grid": True, "grid.alpha": .3,
                         "axes.spines.top": False, "axes.spines.right": False})

    rag = rag.copy()
    rag["is_vol"] = rag["condition"].str.contains("vol")
    rag["cov_lv"] = rag["condition"].str.extract(r'cov(\d+)_')[0].astype(int)
    rag["vol_lv"] = rag["condition"].str.extract(r'vol(\d+)')[0]

    models = sorted(rag["model"].unique(),
                    key=lambda m: 0 if "4b" in str(m).lower() else
                    (1 if "8b" in str(m).lower() else 2))

    def short(m):
        m = str(m).lower()
        for k, v in [("4b", "Qwen3-4B-Instruct"), ("8b", "Qwen3-8B"),
                     ("14b", "Qwen3-14B"), ("32b", "Qwen3-32B")]:
            if k in m:
                return v
        return str(m)[:18]

    def pooled(sub, group, col):
        """그룹별 pooled 비율 + Wilson 구간 + 평균 문자비율."""
        recs = []
        for g, d in sub.groupby(group):
            d = d[d[col].notna()]
            if not len(d):
                continue
            k = int(d[col].astype(float).sum())
            pv, lo, hi = wilson(k, len(d))
            recs.append(dict(group=g, char=d["char_pct"].mean(),
                             cov=d["cov_pct"].mean(), p=pv * 100,
                             lo=lo * 100, hi=hi * 100, k=k, n=len(d)))
        return pd.DataFrame(recs).sort_values("char")

    C_COV, C_VOL = "#1f4e79", "#e07b39"

    # ---------------- 그림 1: 같은 코퍼스 크기, 다른 커버리지
    fig, axes = plt.subplots(1, len(models), figsize=(4.6 * len(models), 3.7),
                             sharey=True, squeeze=False)
    axes = axes[0]
    rec1 = []
    for ax, m in zip(axes, models):
        base = rag[rag["model"] == m]
        for is_vol, grp, col, lab, mk in [
                (False, "cov_lv", C_COV, "Coverage axis", "o-"),
                (True, "vol_lv", C_VOL, "Volume axis (coverage fixed at 100%)", "s--")]:
            t = pooled(base[base["is_vol"] == is_vol], grp, "citation_ok")
            if not len(t):
                continue
            ax.errorbar(t["char"], t["p"], yerr=[t["p"] - t["lo"], t["hi"] - t["p"]],
                        fmt=mk, color=col, ms=5, lw=1.6, capsize=2, label=lab)
            for _, r in t.iterrows():
                rec1.append(dict(model=short(m), axis=lab, char_pct=r["char"],
                                 coverage_pct=r["cov"], citation_acc=r["p"],
                                 ci_lo=r["lo"], ci_hi=r["hi"], k=r["k"], n=r["n"]))
        ax.set_title(short(m), fontsize=10)
        ax.set_xlabel("Corpus size (% of characters)")
        ax.set_xlim(35, 105); ax.set_ylim(0, 100)
    axes[0].set_ylabel("Citation accuracy (%)")
    axes[0].legend(fontsize=7.5, loc="lower right", framealpha=.9)
    fig.suptitle("At the same corpus size, coverage determines attribution",
                 y=1.03, fontsize=10.5)
    fig.tight_layout()
    fig.savefig(out / "fig1_coverage_vs_volume.png", bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(rec1).to_csv(out / "fig1_coverage_vs_volume.csv",
                              index=False, encoding="utf-8-sig")

    # ---------------- 그림 2: 커버리지별 확신도 + 폐쇄북 기준선
    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    rec2 = []
    cb = df[df.get("arm", "rag") == "closedbook"]
    palette = ["#1f4e79", "#e07b39", "#4c9a52"]
    cb_vals = []
    for i, m in enumerate(models):
        sub = rag[(rag["model"] == m) & (~rag["is_vol"])].copy()
        sub["hi"] = (sub["confidence"] == "높음")
        t = pooled(sub, "cov_lv", "hi").sort_values("cov")
        ax.errorbar(t["cov"], t["p"], yerr=[t["p"] - t["lo"], t["hi"] - t["p"]],
                    fmt="o-", color=palette[i % 3], ms=5, lw=1.6, capsize=2,
                    label=short(m))
        for _, r in t.iterrows():
            rec2.append(dict(model=short(m), coverage_pct=r["cov"],
                             pct_high=r["p"], ci_lo=r["lo"], ci_hi=r["hi"],
                             n=r["n"]))
        c0 = cb[cb["model"] == m]
        if len(c0):
            v = (c0["confidence"] == "높음").mean() * 100
            cb_vals.append((short(m), v))
            rec2.append(dict(model=short(m), coverage_pct="closed-book",
                             pct_high=v, ci_lo=np.nan, ci_hi=np.nan, n=len(c0)))
    # 폐쇄북 값이 서로 가까우면 선 하나에 라벨 하나만 (주석 겹침 방지)
    if cb_vals:
        vs = [v for _, v in cb_vals]
        if max(vs) - min(vs) < 5:
            ax.axhline(np.mean(vs), ls=":", lw=1.2, color="#666")
            ax.annotate(f"closed-book, both models: {np.mean(vs):.0f}%",
                        xy=(52, np.mean(vs) + 3), fontsize=8, color="#444")
        else:
            for i, (nm, v) in enumerate(cb_vals):
                ax.axhline(v, ls=":", lw=1.2, color=palette[i % 3])
                ax.annotate(f"{nm} closed-book: {v:.0f}%", xy=(3, v + 3),
                            fontsize=7.5, color=palette[i % 3])
    ax.set_xlabel("Task-relative knowledge coverage (%)")
    ax.set_ylabel('Answers marked "high confidence" (%)')
    ax.set_xlim(-4, 104); ax.set_ylim(0, 107)
    ax.legend(fontsize=8, loc="center right", framealpha=.9)
    fig.tight_layout()
    fig.savefig(out / "fig2_confidence.png", bbox_inches="tight"); plt.close(fig)
    pd.DataFrame(rec2).to_csv(out / "fig2_confidence.csv", index=False,
                              encoding="utf-8-sig")

    # ---------------- 그림 3: 인용 정확도와 인용 건수
    fig, axes = plt.subplots(1, len(models), figsize=(4.6 * len(models), 3.7),
                             sharey=True, squeeze=False)
    axes = axes[0]
    rec3 = []
    for ax, m in zip(axes, models):
        sub = rag[(rag["model"] == m) & (~rag["is_vol"])]
        t = pooled(sub, "cov_lv", "citation_ok").sort_values("cov")
        tot = sub.groupby("cov_lv").size()
        share = (t["n"].to_numpy() /
                 tot.reindex(t["group"]).to_numpy() * 100)
        ax.bar(t["cov"], share, width=7, color="#b9d4ea", edgecolor="none",
               label="Answers containing a citation (%)")
        ax.errorbar(t["cov"], t["p"], yerr=[t["p"] - t["lo"], t["hi"] - t["p"]],
                    fmt="o-", color="#b3202c", ms=5, lw=1.8, capsize=2,
                    label="Citation accuracy (%)")
        ax.set_title(short(m), fontsize=10)
        ax.set_xlabel("Coverage (%)"); ax.set_xlim(-8, 108); ax.set_ylim(0, 100)
        for cv, sh, acc, n in zip(t["cov"], share, t["p"], t["n"]):
            rec3.append(dict(model=short(m), coverage_pct=cv,
                             pct_answers_with_citation=sh,
                             citation_acc=acc, n_cited=int(n)))
    axes[0].set_ylabel("%")
    axes[0].legend(fontsize=7.5, loc="upper left", framealpha=.9)
    fig.suptitle("Citations keep coming after the evidence is gone",
                 y=1.03, fontsize=10.5)
    fig.tight_layout()
    fig.savefig(out / "fig3_citation.png", bbox_inches="tight"); plt.close(fig)
    pd.DataFrame(rec3).to_csv(out / "fig3_citation.csv", index=False,
                              encoding="utf-8-sig")
    print(f"  그림 3장 저장: {out}/fig1..fig3 (+ .csv)")


# ---------------------------------------------------------------- 메인

def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    rows = [json.loads(l) for l in
            Path(a[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    out = Path(opt("--out", "analysis"))
    out.mkdir(parents=True, exist_ok=True)

    # 조건 메타(실제 커버리지·문자비율)
    meta = {}
    for d in opt("--covdirs", "cov_core,cov_periph,cov_random,cov_vol").split(","):
        mf = Path(d) / "coverage_manifest.json"
        if mf.exists():
            for c in json.loads(mf.read_text(encoding="utf-8"))["conditions"]:
                meta[f"cov{c['target_cov']}_{c['strategy']}_{c['unit']}"] = (
                    c["actual_cov"], c["char_ratio"] * 100)
    df["cov_pct"] = df["condition"].map(lambda c: meta.get(c, (np.nan,) * 2)[0])
    df["char_pct"] = df["condition"].map(lambda c: meta.get(c, (np.nan,) * 2)[1])

    # 결과 변수
    df["abstain"] = (df["state"] == "honest_abstain").astype(int)
    df["overconf"] = (df["state"] == "overconfident").astype(int)
    df["judged"] = ~df["state"].isin(["review", "error"])
    # 채점 규칙상 근거가 없는 조건(none/oos)에서는 기권이 '정답'이다.
    # 그래서 correct 에는 '맞게 답함'과 '맞게 기권함'이 섞인다.
    # 커버리지가 낮을수록 후자가 늘어 두 효과가 상쇄되므로,
    # correct 를 전체 표본에 회귀하면 커버리지 효과가 사라진다(실측 OR 1.02, ns).
    # 답변한 것만 따로 본다.
    df["answered"] = df["judged"] & (df["state"] != "honest_abstain")
    df["is_oos"] = df["q_status"] == "oos"
    rag = df[df.get("arm", "rag") == "rag"].copy()
    rag = rag[rag["cov_pct"].notna()]

    # 표본 한정 옵션.
    #  --models      쉼표로 구분한 부분문자열. 균형 설계로 주 회귀를 돌릴 때.
    #  --conditions  쉼표로 구분한 조건명. 세 모델이 모두 있는 조건만 남길 때.
    #  --balanced    모든 모델이 공통으로 가진 조건만 자동 선택.
    if "--models" in a:
        keys = [x.strip().lower() for x in opt("--models", "").split(",") if x.strip()]
        # '4b' 가 '14b' 에 걸리지 않도록 앞자리에 숫자가 오면 배제한다
        pats = [re.compile(r'(?<![0-9a-z])' + re.escape(k)) for k in keys]
        sel = lambda m: any(pt.search(str(m).lower()) for pt in pats)
        rag = rag[rag["model"].apply(sel)]
        df = df[df["model"].apply(sel)]
    if "--conditions" in a:
        keep = {x.strip() for x in opt("--conditions", "").split(",") if x.strip()}
        rag = rag[rag["condition"].isin(keep)]
    if "--balanced" in a:
        by = rag.groupby("condition")["model"].nunique()
        keep = set(by[by == rag["model"].nunique()].index)
        rag = rag[rag["condition"].isin(keep)]
        print(f"균형 설계: 모든 모델이 공통으로 가진 조건 {len(keep)}개만 사용")
    if rag.empty:
        print("필터 결과 표본이 없습니다.")
        return 1
    print(f"분석 표본: RAG {len(rag):,} | 모델 "
          + ", ".join(f"{short_name(m)}({n})" for m, n
                      in rag['model'].value_counts().items())
          + f" | 조건 {rag['condition'].nunique()}")

    L = ["# 통계 분석", "",
         f"- 응답 {len(df):,} (RAG {len(rag):,} / 폐쇄북 {len(df)-len(rag):,})",
         f"- 문항 {df['qid'].nunique()} · 조건 {rag['condition'].nunique()} "
         f"· 모델 {df['model'].nunique()}",
         f"- 판정보류 {(df['state']=='review').sum():,} "
         f"({(df['state']=='review').mean()*100:.1f}%)", "",
         "구간은 Wilson 95%. 회귀 표준오차는 문항 클러스터 강건.",
         "모델이 k 종이면 더미를 k-1 개 넣는다(기준: "
         + short_name(sorted(rag['model'].unique(),
                             key=lambda x: ('4b' not in str(x).lower(),
                                            str(x)))[0]) + ").", ""]

    # ------------------------------------------------ 1. 조건별 비율 + CI
    recs = []
    for (m, c), g in rag.groupby(["model", "condition"]):
        j = g[g["judged"]]
        ans = g[g["answered"] & g["correct"].notna()]
        cite = g[g["citation_ok"].notna()]
        oos = g[g["is_oos"]]
        recs.append(dict(
            model=m, condition=c, cov=g["cov_pct"].iloc[0], char=g["char_pct"].iloc[0],
            n=len(g),
            abstain=fmt_ci(int(g["abstain"].sum()), len(g)),
            overconf=fmt_ci(int(j["overconf"].sum()), len(j)),
            correct_ans=fmt_ci(int(ans["correct"].sum()), len(ans)),
            correct_all=fmt_ci(int((j["correct"] == True).sum()), len(j)),
            cite_acc=fmt_ci(int(cite["citation_ok"].sum()), len(cite)),
            oos_abstain=fmt_ci(int(oos["abstain"].sum()), len(oos))))
    cell = pd.DataFrame(recs).sort_values(["model", "char"])
    cell.to_csv(out / "cell_stats.csv", index=False, encoding="utf-8-sig")

    L += ["## 1. 조건별 비율 (95% 신뢰구간)", "",
          "정확도는 **답변한 것 중** 정답률이다(기권 제외). 괄호 안은 사건/표본.", "",
          "| 모델 | 조건 | 커버 | 문자% | 기권 | 과신오답 | 정확(답변중) | 인용정확 | OOS기권 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in cell.iterrows():
        L.append(f"| {str(r['model'])[:22]} | {r['condition']} | {r['cov']:.0f} | "
                 f"{r['char']:.1f} | {r['abstain']} | {r['overconf']} | "
                 f"{r['correct_ans']} | {r['cite_acc']} | {r['oos_abstain']} |")

    # ------------------------------------------------ 2. 회귀
    L += ["", "## 2. 커버리지 대 분량 — 클러스터 강건 로지스틱 회귀", "",
          "예측변수는 커버리지%와 문자비율%를 10 단위로 나눈 값이다.",
          "따라서 오즈비는 **10%p 증가당** 효과다.",
          "커버리지 축에서는 두 변수가 함께 움직이지만, 분량 축은 커버리지를",
          "100%로 고정한 채 문자비율만 낮추므로 두 효과가 분리된다.", "",
          "**주 명세는 기권을 제외한다.** 채점 규칙상 근거가 없는 조건에서는",
          "기권이 정답으로 처리되므로, 전체 표본에 회귀하면 '맞게 답함'과",
          "'맞게 기권함'이 상쇄되어 커버리지 효과가 사라진다. 참고 명세를",
          "함께 실어 그 상쇄를 드러낸다.", ""]

    reg_all = []
    targets = [
        # --- 주 명세: 기권을 제외한 '답변한 것' 기준 ---
        ("cite_ok", "인용 정확 (인용한 답 중)",
         lambda d: d[d["citation_ok"].notna()],
         lambda d: d["citation_ok"].astype(int)),
        ("correct_answered", "정답 — 답변한 것 중 ★주 명세★",
         lambda d: d[d["answered"] & d["correct"].notna()],
         lambda d: d["correct"].astype(int)),
        ("overconf_answered", "과신오답 — 답변한 것 중 ★주 명세★",
         lambda d: d[d["answered"]], lambda d: d["overconf"]),
        ("abstain", "기권 (전체 중)", lambda d: d, lambda d: d["abstain"]),
        # --- 참고 명세: 기권을 정답으로 세는 전체 표본 기준 ---
        ("correct_all", "[참고] 정답 — 기권 포함. 상쇄로 커버리지 효과가 가려진다",
         lambda d: d[d["judged"] & d["correct"].notna()],
         lambda d: d["correct"].astype(int)),
        ("overconf_all", "[참고] 과신오답 — 기권 포함(분모에 기권이 들어감)",
         lambda d: d[d["judged"]], lambda d: d["overconf"]),
    ]

    models = sorted(rag["model"].unique())
    for key, label, sub, yf in targets:
        d = sub(rag).dropna(subset=["cov_pct", "char_pct"])
        if len(d) < 50:
            continue
        y = yf(d).to_numpy(dtype=float)
        # 사건이 거의 없거나 거의 전부면 완전분리로 추정이 발산한다.
        n1 = int(y.sum())
        if n1 < 10 or len(y) - n1 < 10:
            L += [f"### {label}", "",
                  f"사건 {n1}/{len(y)} — 표본이 한쪽으로 쏠려 회귀를 생략한다.", ""]
            continue
        X = [np.ones(len(d)), d["cov_pct"].to_numpy() / 10,
             d["char_pct"].to_numpy() / 10]
        names = ["절편", "커버리지(+10%p)", "문자비율(+10%p)"]
        # 모델이 k 종이면 더미는 k-1 개여야 한다. 하나만 넣으면 그 모델을
        # '나머지 전부를 합친 것' 과 비교하게 되어, 조건 구성이 모델마다
        # 다를 때(14B 는 7조건에만 있다) 커버리지·문자비율 계수까지 오염된다.
        present = [m for m in models if (d["model"] == m).any()]
        for m in present[1:]:
            X.append((d["model"] == m).to_numpy(dtype=float))
            names.append(f"모델={short_name(m)}")
        res = logit_cluster(np.column_stack(X), y,
                            d["qid"].to_numpy(), names)
        res.insert(0, "outcome", key)
        reg_all.append(res)
        L += [f"### {label}  (n={len(d):,}, 문항 {d['qid'].nunique()})", "",
              "| 항 | 오즈비 [95% CI] | p |", "|---|---|---|"]
        for _, r in res.iterrows():
            if r["term"] == "절편":
                continue
            sig = "***" if r["p"] < .001 else "**" if r["p"] < .01 else \
                  "*" if r["p"] < .05 else ""
            L.append(f"| {r['term']} | {r['odds_ratio']:.3f} "
                     f"[{r['ci_lo']:.3f}–{r['ci_hi']:.3f}] | "
                     f"{r['p']:.2e}{sig} |")
        L.append("")
    if reg_all:
        pd.concat(reg_all).to_csv(out / "regression.csv", index=False,
                                  encoding="utf-8-sig")

    # ------------------------------------------------ 2b. 범위밖 전용 회귀
    oos = rag[rag["is_oos"]].dropna(subset=["cov_pct", "char_pct"])
    L += ["", "## 2b. 범위 밖 문항 전용 — 분량이 정직성을 억제하는가", "",
          "범위 밖 문항은 답할 근거가 애초에 코퍼스에 없다. 기권이 유일한",
          "정답이다. 커버리지 조작은 이 문항들의 근거를 건드리지 않으므로,",
          "여기서 문자비율 계수는 **무관한 내용이 정직성에 미치는 효과**를",
          "직접 잰다. 5단계 추세를 조건 쌍 비교 대신 하나의 검정으로 제시한다.", ""]
    if len(oos) >= 50 and oos["qid"].nunique() >= 5:
        y = oos["abstain"].to_numpy(dtype=float)
        n1 = int(y.sum())
        if 10 <= n1 <= len(y) - 10:
            X = [np.ones(len(oos)), oos["cov_pct"].to_numpy() / 10,
                 oos["char_pct"].to_numpy() / 10]
            nm = ["절편", "커버리지(+10%p)", "문자비율(+10%p)"]
            present = [m for m in models if (oos["model"] == m).any()]
            for m in present[1:]:
                X.append((oos["model"] == m).to_numpy(dtype=float))
                nm.append(f"모델={short_name(m)}")
            r2 = logit_cluster(np.column_stack(X), y, oos["qid"].to_numpy(), nm)
            r2.insert(0, "outcome", "oos_abstain")
            reg_all.append(r2)
            L += [f"결과변수: 기권 (n={len(oos):,}, 문항 {oos['qid'].nunique()})", "",
                  "| 항 | 오즈비 [95% CI] | p |", "|---|---|---|"]
            for _, r in r2.iterrows():
                if r["term"] == "절편":
                    continue
                sig = "***" if r["p"] < .001 else "**" if r["p"] < .01 else \
                      "*" if r["p"] < .05 else ""
                L.append(f"| {r['term']} | {r['odds_ratio']:.3f} "
                         f"[{r['ci_lo']:.3f}–{r['ci_hi']:.3f}] | {r['p']:.2e}{sig} |")
            L += ["", f"**주의: 클러스터가 {oos['qid'].nunique()}개(문항 수)뿐이다.** "
                  "클러스터 강건표준오차는 클러스터 수가 적으면 과소추정될 수 있다.",
                  "이 결과는 확정적 검정이 아니라 추세의 보조 증거로 제시한다.", ""]
        else:
            L += [f"사건 {n1}/{len(y)} — 쏠림으로 회귀를 생략한다.", ""]

    # ------------------------------------------------ 2c. 과신 오답 분해
    L += ["", "## 2c. 과신 오답 분해 — 범위 안 대 범위 밖", "",
          "범위 밖 문항은 확신 있게 답하면 자동으로 과신 오답이 된다.",
          "둘을 합쳐 보고하면 값이 부풀려 보이므로 나누어 제시한다.", "",
          "| 모델 | 조건 | 커버 | 문자% | 범위 안 과신 | 범위 밖 과신 |",
          "|---|---|---|---|---|---|"]
    for (m, c), g in rag.groupby(["model", "condition"]):
        j = g[g["judged"]]
        ins, outs = j[~j["is_oos"]], j[j["is_oos"]]
        L.append(f"| {str(m)[:20]} | {c} | {g['cov_pct'].iloc[0]:.0f} | "
                 f"{g['char_pct'].iloc[0]:.1f} | "
                 f"{fmt_ci(int(ins['overconf'].sum()), len(ins))} | "
                 f"{fmt_ci(int(outs['overconf'].sum()), len(outs))} |")

    # ------------------------------------------------ 3. 짝지음 McNemar
    L += ["## 3. 짝지음 대조 — 대응표본 검정(McNemar)", "",
          "코퍼스 크기가 비슷한데 커버리지만 다른 조건 쌍. 같은 97문항이므로",
          "독립표본이 아니라 대응표본 검정이 맞다.", "",
          "| 모델 | 조건 A (커버 낮음) | 조건 B (커버 100%) | 지표 | A | B | p |",
          "|---|---|---|---|---|---|---|"]
    pairs = [("cov0_core_doc", "cov100_vol055_doc"),
             ("cov0_core_doc", "cov100_vol030_doc"),
             ("cov0_periph_doc", "cov100_vol055_doc"),
             ("cov25_core_doc", "cov100_vol070_doc"),
             ("cov40_core_doc", "cov100_vol085_doc")]
    for m in models:
        sub = rag[rag["model"] == m]
        for ca, cb in pairs:
            A = sub[sub["condition"] == ca].set_index("qid")
            B = sub[sub["condition"] == cb].set_index("qid")
            common = A.index.intersection(B.index)
            if len(common) < 10:
                continue
            A = A.assign(correct_ans=A["correct"].where(A["answered"]))
            B = B.assign(correct_ans=B["correct"].where(B["answered"]))
            for var, lab in [("citation_ok", "인용정확"),
                             ("correct_ans", "정답(답변중)"),
                             ("correct", "정답(기권포함)"), ("abstain", "기권")]:
                x = A.loc[common, var]
                z = B.loc[common, var]
                ok = x.notna() & z.notna()
                x, z = x[ok].astype(bool), z[ok].astype(bool)
                if len(x) < 10:
                    continue
                b = int((x & ~z).sum())
                c = int((~x & z).sum())
                p, note = mcnemar(b, c)
                L.append(f"| {str(m)[:20]} | {ca} | {cb} | {lab} | "
                         f"{x.sum()}/{len(x)} | {z.sum()}/{len(z)} | "
                         f"{p:.2e} ({note}) |")

    # ------------------------------------------------ 4. 폐쇄북 대조
    cb = df[df.get("arm", "rag") == "closedbook"]
    if len(cb):
        L += ["", "## 4. 폐쇄북 대조 — 확신도 분포", "",
              "같은 모델·같은 프롬프트에서 검색 컨텍스트 유무만 다르다.", "",
              "| 모델 | 조건 | 확신도 '높음' | p (Fisher) |", "|---|---|---|---|"]
        for m in cb["model"].unique():
            c0 = cb[cb["model"] == m]
            r0 = rag[(rag["model"] == m) & (rag["condition"] == "cov100_core_doc")]
            if not len(r0):
                continue
            k1 = int((c0["confidence"] == "높음").sum())
            k2 = int((r0["confidence"] == "높음").sum())
            _, p = stats.fisher_exact([[k1, len(c0) - k1], [k2, len(r0) - k2]])
            L.append(f"| {str(m)[:22]} | 폐쇄북 | {fmt_ci(k1, len(c0))} | {p:.2e} |")
            L.append(f"| {str(m)[:22]} | RAG cov100 | {fmt_ci(k2, len(r0))} | |")

    L += ["", "## 해석 지침", "",
          "- 2절의 **주 명세**(기권 제외)를 본문에 싣는다. 참고 명세는",
          "  각주나 부록으로 돌리고, 상쇄가 왜 생기는지 한 줄로 설명한다.",
          "- 2절에서 **커버리지 오즈비는 1에서 멀고 유의**, **문자비율 오즈비는",
          "  1에 가깝고 비유의**여야 'Coverage > Volume'이 검정으로 성립한다.",
          "- 문자비율 오즈비가 1보다 크게 나오면(=분량이 줄수록 좋아짐)",
          "  4.4절의 '주변부 제거의 역설적 효용'이 회귀로도 뒷받침된다.",
          "- OOS 기권의 신뢰구간이 넓다면(표본 17) 해당 발견은 탐색적으로 서술한다."]

    # ------------------------------------------------ 5. 그림
    try:
        make_figures(rag, df, out)
        L += ["", "## 그림", "",
              "- `fig1_coverage_vs_volume.png` 같은 코퍼스 크기에서 두 축이 갈라진다",
              "- `fig2_confidence.png` 커버리지별 확신도 + 폐쇄북 기준선",
              "- `fig3_citation.png` 인용 정확도와 인용 건수(지어낸 인용의 규모)",
              "- 각 그림의 원자료는 같은 이름의 .csv 로 저장된다"]
    except Exception as e:                               # noqa: BLE001
        L += ["", f"(그림 생성 실패: {type(e).__name__}: {e})"]

    (out / "analysis_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"-> {out}/analysis_report.md, cell_stats.csv, regression.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
