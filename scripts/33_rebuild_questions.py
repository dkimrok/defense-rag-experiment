#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
33_rebuild_questions.py — 슬롯 재생성 + 작성분 이월 + 워크시트 생성

왜 필요한가
  17 의 jo_fulltext 가 '조 unit 의 text' 와 '하위 항/호/목' 을 그대로
  이어붙여, 행정규칙에서 같은 내용이 2~3회 반복됐다. 그 중복이 1500자
  상한을 먹어 100슬롯 중 34개의 조문 뒷부분이 소실된 상태였다.
  17 을 고쳤으므로 슬롯을 다시 만들어야 한다.

  단순 재생성하면 이미 작성한 문항이 날아간다. 이 스크립트는
  재생성 후 기존 작성분(question_ko/answer_short/answer_long/annotation)을
  qid 기준으로 이월한다. 이월 전에 gold unit_id 가 같은지 확인하고,
  다르면 이월하지 않고 경고한다(근거가 바뀐 슬롯에 옛 문항을 붙이면
  틀린 문항이 된다).

절차
  1. 17 실행 → question_slots.jsonl (+ 17 자체 목록 md)
  2. 기존 작성분 이월
  3. 31 실행 → worksheet/ (근거 조문이 실린 작성용 워크시트)
  4. 잘림 잔존 여부 보고

사용법
  py 33_rebuild_questions.py corpus_final.jsonl \\
      --l3 l3_final.jsonl --l4 l4_candidates.jsonl --oos oos_sources.jsonl \\
      --filled question_final.jsonl --span-cap 8000 --dup audit/gold_dup.tsv
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

CARRY = ("question_ko", "question_en", "answer_short", "answer_long",
         "answer_alternatives")


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def gold_ids(s: dict) -> tuple:
    return tuple(sorted((g.get("unit_id") or "")
                        for g in (s.get("gold_evidence") or [])))


def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    corpus = a[1]
    filled_path = opt("--filled", "question_final.jsonl")
    span_cap = opt("--span-cap", "8000")
    py = opt("--python", sys.executable)

    # 기존 작성분 미리 읽어둔다(17 이 question_slots.jsonl 을 덮어쓰므로)
    prev: dict[str, dict] = {}
    if Path(filled_path).exists():
        for r in load(filled_path):
            if (r.get("question_ko") or "").strip():
                prev[r["qid"]] = r
        print(f"기존 작성분 {len(prev)}개 확보 ({filled_path})")
    else:
        print(f"기존 작성분 없음 ({filled_path} 미존재)")

    n_prev_slots = 0
    if Path("question_slots.jsonl").exists():
        shutil.copy("question_slots.jsonl", "question_slots.jsonl.bak")
        n_prev_slots = len(load("question_slots.jsonl"))
        print(f"기존 슬롯 백업 → question_slots.jsonl.bak ({n_prev_slots}개)")
    if Path(filled_path).exists():
        shutil.copy(filled_path, filled_path + ".bak")
        print(f"기존 작성본 백업 → {filled_path}.bak")

    # ---------------------------------------------- 1. 슬롯 재생성
    cmd = [py, "17_sample_questions.py", corpus,
           "--l3", opt("--l3", "l3_final.jsonl"),
           "--l4", opt("--l4", "l4_candidates.jsonl"),
           "--oos", opt("--oos", "oos_sources.jsonl"),
           "--seed", opt("--seed", "20260721"),
           "--span-cap", span_cap]
    print(f"\n$ {' '.join(cmd)}")
    if subprocess.call(cmd):
        return 1

    slots = load("question_slots.jsonl")

    # 슬롯이 크게 줄었다면 입력 누락이다. 덮어쓰기 전에 멈추고 되돌린다.
    if n_prev_slots and len(slots) < n_prev_slots * 0.9:
        print(f"\n*** 슬롯이 {n_prev_slots} → {len(slots)} 로 급감했습니다.")
        print("    L3/L4/OOS 후보 파일(--l3/--l4/--oos)이 누락됐을 가능성이 큽니다.")
        print("    백업을 복원하고 중단합니다. 파일 경로를 확인하십시오.")
        shutil.copy("question_slots.jsonl.bak", "question_slots.jsonl")
        if Path(filled_path + ".bak").exists():
            shutil.copy(filled_path + ".bak", filled_path)
        return 2

    # ---------------------------------------------- 2. 작성분 이월
    carried = skipped = 0
    for s in slots:
        old = prev.get(s["qid"])
        if not old:
            continue
        if gold_ids(old) != gold_ids(s):
            print(f"  ! {s['qid']} gold 가 바뀌어 이월하지 않음 "
                  f"(옛 {len(gold_ids(old))}개 → 새 {len(gold_ids(s))}개). "
                  f"워크시트에서 다시 작성하십시오.")
            skipped += 1
            continue
        for k in CARRY:
            if old.get(k):
                s[k] = old[k]
        if old.get("annotation"):
            s["annotation"] = old["annotation"]
        carried += 1

    with open("question_slots.jsonl", "w", encoding="utf-8") as f:
        for s in slots:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"\n이월 {carried}개 | 미이월 {skipped}개")

    # 이월분을 반영한 작업본도 남긴다
    shutil.copy("question_slots.jsonl", filled_path)
    print(f"이월 반영본 → {filled_path}")

    # ---------------------------------------------- 3. 워크시트
    cmd = [py, "31_make_worksheet.py", "question_slots.jsonl",
           "--done", filled_path, "--out", opt("--out", "worksheet")]
    dup = opt("--dup", None)
    if dup and Path(dup).exists():
        cmd += ["--dup", dup]
    print(f"\n$ {' '.join(cmd)}")
    if subprocess.call(cmd):
        return 1

    # ---------------------------------------------- 4. 잘림 점검
    cap = int(span_cap)
    cut = [s["qid"] for s in slots
           if any(len(g.get("text_span") or "") >= cap
                  for g in (s.get("gold_evidence") or []))]
    tot = sum(len(g.get("text_span") or "")
              for s in slots for g in (s.get("gold_evidence") or []))
    print(f"\ngold 텍스트 합계 {tot:,}자 | 상한 {cap:,}자")
    if cut:
        print(f"*** 여전히 잘린 슬롯 {len(cut)}개: {', '.join(cut[:10])}"
              f"{' ...' if len(cut) > 10 else ''}")
        print("    --span-cap 을 더 올려 다시 실행하십시오.")
    else:
        print("잘린 슬롯 없음 — 모든 근거 조문이 온전합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
