#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
작성된 슬롯 병합 — 실험용 최종 문항 세트 만들기

문항 작성이 두 파일로 나뉘어 있다.
    pilot_slots_filled_v2.jsonl   시범 15개 (검증 완료)
    main_slots.jsonl              나머지 85개

이 둘을 합쳐 완성된 100개 슬롯(question_final.jsonl)을 만든다.
RAG 실행기(25)와 채점기(23)는 이 파일을 입력으로 쓴다.

검사
    - qid 중복 없는지
    - question_ko 가 빈 슬롯이 있는지 (있으면 경고 — 아직 안 쓴 문항)
    - 수준 배분이 맞는지 (L1~L4 각 20, OOS 20 기대)

빈 슬롯 처리
    question_ko 가 비어 있으면 '미작성'이다. 기본은 제외하고 경고한다.
    --keep-empty 를 주면 빈 것도 포함한다(권장하지 않음).

사용법
    py 26_merge_slots.py pilot_slots_filled_v2.jsonl main_slots.jsonl
        -> question_final.jsonl
    py 26_merge_slots.py <파일들...> --out question_final.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def main(paths: list[str], out: str, keep_empty: bool) -> None:
    merged: dict[str, dict] = {}
    dup = []
    for p in paths:
        if not Path(p).exists():
            print(f"  ! 파일 없음: {p}")
            continue
        rows = load(p)
        n_filled = sum(1 for r in rows if (r.get("question_ko") or "").strip())
        print(f"  {p}: {len(rows)}개 (작성 {n_filled})")
        for r in rows:
            qid = r["qid"]
            if qid in merged:
                # 이미 있으면, 작성된 쪽을 우선한다
                old = merged[qid]
                old_filled = bool((old.get("question_ko") or "").strip())
                new_filled = bool((r.get("question_ko") or "").strip())
                if new_filled and not old_filled:
                    merged[qid] = r
                elif new_filled and old_filled:
                    dup.append(qid)
                # 둘 다 비었거나 기존이 작성됨 → 유지
            else:
                merged[qid] = r

    slots = list(merged.values())
    empty = [s["qid"] for s in slots if not (s.get("question_ko") or "").strip()]
    filled = [s for s in slots if (s.get("question_ko") or "").strip()]

    final = slots if keep_empty else filled

    with open(out, "w", encoding="utf-8") as f:
        for s in final:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    by_level = Counter(s["level"] for s in final)
    print()
    print(f"병합: 총 {len(slots)}개 슬롯 / 작성 {len(filled)} / 미작성 {len(empty)}")
    print(f"출력: {out} ({len(final)}개)")
    print(f"수준 배분: " + " · ".join(f"L{k} {v}" for k, v in sorted(by_level.items())))
    if dup:
        print(f"\n! 두 파일에 모두 작성된 qid {len(dup)}개 (뒤 파일 무시): "
              f"{', '.join(dup[:10])}")
    if empty and not keep_empty:
        print(f"\n! 미작성 {len(empty)}개 제외됨: {', '.join(empty[:15])}"
              + (" ..." if len(empty) > 15 else ""))
        print("  실험 전에 이 문항들을 작성하거나, 100개 미만으로 진행할지 정하세요.")
    if len(final) < 100 and not empty:
        print(f"\n  (참고) 최종 {len(final)}개. 100개를 의도했다면 누락을 확인하세요.")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    out = "question_final.jsonl"
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
        a = [x for x in a if x != out]
    if not a:
        print(__doc__)
    else:
        main(a, out, "--keep-empty" in sys.argv)
