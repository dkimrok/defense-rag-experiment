#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
34_fix_spans.py — 슬롯 파일의 근거 조문 중복을 직접 정리

17 을 다시 돌리지 않고 이미 만들어진 question_slots.jsonl 을 손본다.
gold_evidence[].text_span 과 distractors.stale_versions[].diff_note 에서
'조 전문 + 항 반복 + 호 반복' 구조의 중복을 걷어낸다.

판정
  앞서 담은 내용에 이미 포함된 조각만 버린다. 조 text 가 전문을 담은
  행정규칙에서는 반복이 사라지고, 조 제목만 담은 법률에서는 아무것도
  버리지 않는다. 양쪽 파서에 모두 안전하다.

한계
  저장 시점에 상한(1500/8000자)에 걸려 이미 잘려나간 뒷부분은 복구할 수
  없다. 그런 슬롯은 따로 보고하므로, 그 목록이 나오면 17 을 고쳐
  재생성해야 한다.

--reset 을 주면 question_ko / answer_short / answer_long 을 모두 비운다.
문항을 처음부터 다시 쓸 때 쓴다. (원본은 .bak 으로 남는다)

사용법
  py 34_fix_spans.py question_slots.jsonl
  py 34_fix_spans.py question_slots.jsonl --reset --worksheet worksheet
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RE_WS = re.compile(r'\s+')


def dedup_parts(text: str) -> str:
    """줄 단위로 앞에 이미 나온 내용을 버린다."""
    kept: list[str] = []
    acc = ""
    for ln in (text or "").splitlines():
        flat = RE_WS.sub('', ln)
        if not flat or flat in acc:
            continue
        kept.append(ln)
        acc += flat
    return "\n".join(kept)


def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    path = a[1]
    reset = "--reset" in a
    ws = opt("--worksheet", None)

    rows = [json.loads(l) for l in
            Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    shutil.copy(path, path + ".bak")
    print(f"백업 → {path}.bak")

    before = after = 0
    changed = 0
    still_cut: list[str] = []
    caps = (1500, 8000)

    for r in rows:
        hit_cap = False
        for g in r.get("gold_evidence") or []:
            t = g.get("text_span") or ""
            d = dedup_parts(t)
            before += len(t)
            after += len(d)
            if d != t:
                changed += 1
            if len(t) in caps:          # 정확히 상한 = 잘린 흔적
                hit_cap = True
            g["text_span"] = d
        for v in (r.get("distractors") or {}).get("stale_versions") or []:
            t = v.get("diff_note") or ""
            v["diff_note"] = dedup_parts(t)
            if len(t) in caps:
                hit_cap = True
        if hit_cap:
            still_cut.append(r["qid"])
        if reset:
            for k in ("question_ko", "question_en", "answer_short",
                      "answer_long"):
                r[k] = ""
            r["answer_alternatives"] = []

    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    pct = (1 - after / before) * 100 if before else 0
    print(f"슬롯 {len(rows)}개 | 근거 텍스트 {before:,} → {after:,}자 "
          f"({pct:.0f}% 중복 제거) | 변경된 span {changed}개")
    if reset:
        print("작성분 초기화 완료 (question_ko/answer_short/answer_long)")

    if still_cut:
        print(f"\n*** 상한에 걸려 이미 잘린 슬롯 {len(still_cut)}개")
        print("    " + ", ".join(still_cut[:12]) +
              (" ..." if len(still_cut) > 12 else ""))
        print("    이 조문들은 뒷부분이 소실됐습니다. 17 을 고쳐 재생성해야 합니다.")
    else:
        print("\n상한에 걸린 슬롯 없음 — 모든 근거 조문이 온전합니다.")

    if ws:
        cmd = [sys.executable, "31_make_worksheet.py", path, "--out", ws]
        dup = opt("--dup", None)
        if dup and Path(dup).exists():
            cmd += ["--dup", dup]
        if not reset:
            cmd += ["--done", path]
        print(f"\n$ {' '.join(cmd)}")
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
