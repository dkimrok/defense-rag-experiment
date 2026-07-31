#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
30_regen.py — 변형 코퍼스·중복감사 일괄 재생성 + 검증 + 실행계획

언제 쓰나
  corpus_final.jsonl, question_final.jsonl, refs.jsonl 중 하나라도 바뀌면
  모든 변형이 무효가 된다. 특히 문항을 추가하면 gold 보유 문서가 늘어
  커버리지 축과 분량 축이 통째로 달라진다. 그때마다 이 스크립트를 돌린다.

전부 CPU 작업이다(임베딩·생성 없음). 노트북에서 돌려도 된다.
GPU 가 필요한 것은 24(임베딩)와 25(RAG 생성)뿐이다.

무엇을 하나
  1. 기존 변형 폐기 후 22 로 재생성 (coverage 3전략 + volume 1)
  2. 28 중복감사 → dup_map.json
  3. 29 내용기준 q_status 재계산
  4. 검증 4종: 인용매칭 / 전략분기 / 단조성 / 분량축 커버리지 고정
  5. 중복조건 탐지 → run_plan.json
     temperature 0.0 이면 동일 코퍼스는 동일 응답이다. MD5 가 같은 조건을
     한 번만 돌리도록 실행계획을 만든다. 문항 수가 적을 때 특히 중복이
     많이 생긴다(12문항이면 한 문항이 8.3% 라 8단계를 다 구분 못 함).

사용법
  py 30_regen.py                       # 기본 경로로 전체 재생성
  py 30_regen.py --skip-audit          # 28/29 건너뛰기(코퍼스 안 바뀐 경우)
  py 30_regen.py --levels 100,85,70,55,40,25,10,0 --vol-levels 100,85,70,55,40,30
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

STRATEGIES = ["core", "periph", "random"]


def sh(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd)


def md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def units(p: Path) -> set:
    return {json.loads(l)["unit_id"]
            for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}


def main() -> int:
    a = sys.argv

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    corpus = opt("--corpus", "corpus_final.jsonl")
    quest = opt("--questions", "question_final.jsonl")
    refs = opt("--refs", "refs.jsonl")
    index = opt("--index", "index")
    unit = opt("--unit", "doc")
    levels = opt("--levels", "100,85,70,55,40,25,10,0")
    vlevels = opt("--vol-levels", "100,85,70,55,40,30")
    py = opt("--python", sys.executable)
    skip_audit = "--skip-audit" in a

    for f in (corpus, quest, refs):
        if not Path(f).exists():
            print(f"*** 입력 없음: {f}")
            return 1

    # ---------------------------------------------- 1. 변형 재생성
    for d in [f"cov_{s}" for s in STRATEGIES] + ["cov_vol"]:
        shutil.rmtree(d, ignore_errors=True)

    for s in STRATEGIES:
        if sh([py, "22_coverage_engine.py", corpus, quest, "--unit", unit,
               "--strategy", s, "--refs", refs, "--levels", levels,
               "--out", f"cov_{s}"]):
            return 1
    if sh([py, "22_coverage_engine.py", corpus, quest, "--mode", "volume",
           "--unit", unit, "--strategy", "periph", "--refs", refs,
           "--levels", vlevels, "--out", "cov_vol"]):
        return 1

    # ---------------------------------------------- 2~3. 감사
    if not skip_audit:
        if sh([py, "28_dup_audit.py", index, quest,
               "--min-sim", opt("--min-sim", "0.6"), "--out", "audit"]):
            return 1
        if sh([py, "29_status_content.py", index, quest, "audit/dup_map.json",
               "--variants", ",".join([f"cov_{s}" for s in STRATEGIES] + ["cov_vol"]),
               "--out", "."]):
            return 1

    # ---------------------------------------------- 4. 검증
    print("\n" + "=" * 62)
    print("검증")
    print("=" * 62)
    ok = True

    mf = json.loads(Path(f"cov_{STRATEGIES[0]}/coverage_manifest.json")
                    .read_text(encoding="utf-8"))
    d = mf.get("citation_diag", {})
    pct = d.get("matched", 0) / d["edges"] * 100 if d.get("edges") else 0
    print(f"[인용]   간선 {d.get('edges',0):,} 매칭 {d.get('matched',0):,} "
          f"({pct:.1f}%) → 문서 {d.get('docs_with_citation',0)}종")
    if not d.get("matched"):
        print("   *** 매칭 0 — 전략 축이 무효입니다"); ok = False

    fixed = f"corpus_cov{int(levels.split(',')[len(levels.split(','))//2]):03d}"
    hs = {}
    for s in STRATEGIES:
        g = list(Path(f"cov_{s}").glob(f"{fixed}_*.jsonl"))
        if g:
            hs[s] = md5(g[0])
    if len(set(hs.values())) == len(hs) and len(hs) == len(STRATEGIES):
        print(f"[전략]   {fixed} 기준 3전략 모두 구분됨")
    else:
        print(f"[전략]   *** 동일 파일 존재: {hs}"); ok = False

    lv = [int(x) for x in levels.split(",")]
    for s in STRATEGIES:
        prev, bad = None, 0
        for v in lv:
            f = Path(f"cov_{s}/corpus_cov{v:03d}_{s}_{unit}.jsonl")
            if not f.exists():
                continue
            cur = units(f)
            if prev is not None and not cur <= prev:
                bad += 1
            prev = cur
        print(f"[단조]   {s}: {'OK' if bad == 0 else f'*** 깨짐 {bad}구간'}")
        ok &= bad == 0

    vm = json.loads(Path("cov_vol/coverage_manifest.json")
                    .read_text(encoding="utf-8"))
    bad = [c for c in vm["conditions"] if c["actual_cov"] != 100.0]
    print(f"[분량]   조건 {len(vm['conditions'])}개 | "
          f"커버리지 100% 고정 {'OK' if not bad else '*** 이탈 ' + str(len(bad))}")
    ok &= not bad

    # ---------------------------------------------- 5. 중복조건 → 실행계획
    by_hash: dict[str, list[str]] = defaultdict(list)
    for dirn in [f"cov_{s}" for s in STRATEGIES] + ["cov_vol"]:
        for f in sorted(Path(dirn).glob("corpus_cov*.jsonl")):
            by_hash[md5(f)].append(str(f))
    uniq = {h: v[0] for h, v in by_hash.items()}
    dups = {h: v for h, v in by_hash.items() if len(v) > 1}
    total = sum(len(v) for v in by_hash.values())
    print(f"\n[중복]   전체 변형 {total}개 → 고유 {len(uniq)}개 "
          f"(중복 {total - len(uniq)}개 절약)")
    for h, v in dups.items():
        print(f"   {Path(v[0]).name}  ≡  " +
              ", ".join(Path(x).name for x in v[1:]))

    plan = dict(unique_variants=sorted(uniq.values()),
                duplicate_groups=[sorted(v) for v in dups.values()],
                n_total=total, n_unique=len(uniq))
    Path("run_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> run_plan.json (고유 변형 {len(uniq)}개만 실행하면 됩니다)")
    print("=" * 62)
    print("전체 통과" if ok else "*** 실패 항목 있음 — 위 로그 확인")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
