#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
40_recover_slots.py — 응답 파일에서 최소 문항 슬롯 복원

언제 쓰나
  실험에 쓴 문항 파일(question_final.jsonl)을 잃었을 때의 보험이다.
  응답 레코드에는 qid, q_status, gold_chunks 가 실려 있으므로
  채점에 필요한 것의 일부를 되살릴 수 있다.

복원되는 것 / 안 되는 것
  [O] answerable   q_status=='oos' 로 판정
  [O] gold_evidence 의 조 번호   gold_chunks 의 unit_id 에서 환원
      → **인용 정확도** 채점이 가능하다(이 연구의 주 지표)
  [O] 기권·확신도·범위밖 기권   응답 텍스트만으로 판정
  [X] question_ko / answer_short / answer_long
      → **정답률과 과신오답률은 채점할 수 없다.**
        답 가능 문항은 전부 review 로 남는다.

  즉 4.1(인용), 4.2(짝지음-인용), 4.3, 4.4, 4.6 은 살릴 수 있고
  정답률 기반 지표만 잃는다. 원본을 찾는 편이 압도적으로 낫다.

chunk_id 좌표
  law:{법령ID}:{조6}  /  admrul:{일련번호}:{조6}
  조6 = 조번호 4자리 + 가지 2자리. 예) 000300 -> 제3조, 002702 -> 제27조의2

사용법
  py 40_recover_slots.py runs --out question_recovered.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def jo_from_chunk(chunk_id: str) -> dict:
    """chunk_id 끝의 6자리에서 조 번호와 가지를 되살린다."""
    tail = chunk_id.rsplit(":", 1)[-1]
    if not (tail.isdigit() and len(tail) == 6):
        return {}
    jo, branch = int(tail[:4]), int(tail[4:])
    # 23 의 citation_ok 는 locator["조"] 를 '27의2' 형태로 읽는다.
    # 가지를 별도 키로 두면 매칭에서 빠진다.
    return {"조": f"{jo}의{branch}" if branch else str(jo)}


def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    src = Path(a[1])
    files = sorted(src.glob("responses_*.jsonl")) if src.is_dir() else [src]
    if not files:
        print(f"응답 파일이 없습니다: {src}")
        return 1

    slots: dict[str, dict] = {}
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            qid = r["qid"]
            s = slots.setdefault(qid, dict(qid=qid, level=None,
                                           answerable=True, gold=set(),
                                           statuses=set()))
            s["statuses"].add(r.get("q_status"))
            for g in r.get("gold_chunks") or []:
                s["gold"].add(g)

    out = []
    for qid, s in sorted(slots.items()):
        # 어느 조건에서든 oos 로 표시됐으면 범위밖 문항이다
        answerable = "oos" not in s["statuses"]
        lvl = 0 if not answerable else (
            int(qid.split("-")[1][1]) if qid.split("-")[1][1:].isdigit() else None)
        out.append(dict(
            qid=qid, as_of=opt("--as-of", "2026-07-21"), level=lvl,
            level_justification="[복원] 응답 파일에서 재구성",
            question_ko="", question_en="", answerable=answerable,
            out_of_scope_reason=None if answerable else "out_of_scope",
            answer_short="", answer_long="", answer_alternatives=[],
            gold_evidence=[dict(unit_id=g, tier="", doc_type="", doc_name="",
                                doc_id="", issue_no="", effective_date="",
                                locator=jo_from_chunk(g), text_span="",
                                necessity="required")
                           for g in sorted(s["gold"])],
            evidence_profile=dict(unit_count=len(s["gold"]),
                                  required_count=len(s["gold"]),
                                  tier_span=1, has_supplementary=False),
            distractors=dict(stale_versions=[], sibling_provisions=[],
                             cross_tier_lookalikes=[]),
            source=dict(origin="응답파일_복원", note="문항·정답 텍스트 없음"),
            quality_checks={}, annotation={}, condition_labels={}))

    outp = opt("--out", "question_recovered.jsonl")
    with open(outp, "w", encoding="utf-8") as f:
        for s in out:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    n_oos = sum(1 for s in out if not s["answerable"])
    n_gold = sum(1 for s in out if s["gold_evidence"])
    print(f"응답 파일 {len(files)}개에서 문항 {len(out)}개 복원 → {outp}")
    print(f"  범위밖 {n_oos} | gold 조 보유 {n_gold}")
    print("\n채점 가능:  인용 정확도 · 기권 · 확신도 · 범위밖 기권")
    print("채점 불가:  정답률 · 과신오답률  (문항·정답 텍스트가 없음)")
    print("→ 원본 question_final.jsonl 을 찾으면 그것을 쓰십시오.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
