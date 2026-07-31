#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
32_fill_worksheet.py — 작성한 워크시트를 슬롯 JSONL 로 되돌린다

31 이 만든 worksheet/*.md 의 '작성란'을 읽어 question_slots.jsonl 에
question_ko / answer_short / answer_long 을 채워 넣는다.

파싱 규칙
  '## <qid>' 로 슬롯을 구분한다.
  '- question_ko:' 뒤부터 다음 '- ' 항목 또는 '---' 전까지가 값이다.
  여러 줄로 써도 된다(줄바꿈은 공백으로 합쳐진다).
  빈 값은 건너뛴다(미작성 슬롯은 그대로 둔다).

점검
  R1 어휘 누출: 질문이 gold 조문의 연속 5어절을 그대로 포함하는지
  R5 기준일 노출: 질문에 날짜 표기가 있는지
  단답 길이: answer_short 15자 초과
  OOS: 인용하는 조문만으로 답이 되는지 의심되는 경우 경고
  (경고만 낸다. 판단은 사람이 한다)

사용법
  py 32_fill_worksheet.py question_slots.jsonl worksheet --out question_final.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RE_H2 = re.compile(r'^##\s+(DAPA-[A-Z0-9-]+)\s*$')
RE_FIELD = re.compile(r'^-\s+(question_ko|answer_short|answer_long)\s*:\s*(.*)$')
RE_DATE = re.compile(r'\d{4}\s*[.\-년/]\s*\d{1,2}|\d{4}년|\d{8}')
FIELDS = ("question_ko", "answer_short", "answer_long")


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def parse_md(text: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    qid = None
    key = None
    buf: list[str] = []
    in_code = False

    def flush():
        if qid and key:
            v = " ".join(x.strip() for x in buf if x.strip()).strip()
            if v:
                out.setdefault(qid, {})[key] = v

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = RE_H2.match(line.strip())
        if m:
            flush()
            qid, key, buf = m.group(1), None, []
            continue
        m = RE_FIELD.match(line)
        if m:
            flush()
            key, buf = m.group(1), [m.group(2)]
            continue
        if line.strip().startswith("- ") or line.strip() == "---" or line.startswith("#"):
            flush()
            key, buf = None, []
            continue
        if key:
            buf.append(line)
    flush()
    return out


def eojeol(s: str) -> list[str]:
    return [w for w in re.split(r'\s+', re.sub(r'[^\w가-힣\s]', ' ', s or "")) if w]


def leak_ngram(q: str, spans: list[str], n: int = 5) -> str | None:
    qe = eojeol(q)
    if len(qe) < n:
        return None
    grams = {" ".join(qe[i:i + n]) for i in range(len(qe) - n + 1)}
    for sp in spans:
        se = eojeol(sp)
        for i in range(len(se) - n + 1):
            g = " ".join(se[i:i + n])
            if g in grams:
                return g
    return None


def main() -> int:
    a = sys.argv
    if len(a) < 3:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    slots = load(a[1])
    wsdir = Path(a[2])
    outp = opt("--out", "question_final.jsonl")

    filled: dict[str, dict] = {}
    for f in sorted(wsdir.glob("*.md")):
        if f.name.startswith("00_"):
            continue
        filled.update(parse_md(f.read_text(encoding="utf-8")))

    n_new = n_warn = 0
    for s in slots:
        v = filled.get(s["qid"])
        if not v:
            continue
        for k in FIELDS:
            if v.get(k):
                s[k] = v[k]
        if not (s.get("question_ko") or "").strip():
            continue
        n_new += 1

        q = s["question_ko"]
        spans = [g.get("text_span") or "" for g in s.get("gold_evidence") or []]
        w = []
        g5 = leak_ngram(q, spans)
        if g5:
            w.append(f"R1 어휘누출 5어절: '{g5}'")
        if RE_DATE.search(q):
            w.append("R5 질문에 날짜 표기")
        if len(s.get("answer_short") or "") > 15 and s.get("answerable", True):
            w.append(f"단답 {len(s['answer_short'])}자 (15자 초과)")
        if not s.get("answerable", True):
            ashort = s.get("answer_short") or ""
            if "근거" not in ashort and "없" not in ashort:
                w.append("OOS 인데 answer_short 가 '근거 없음' 형태가 아님")
        if not (s.get("answer_long") or "").strip():
            w.append("answer_long 비어 있음")
        if w:
            n_warn += 1
            print(f"[{s['qid']}]")
            for x in w:
                print(f"   - {x}")

    with open(outp, "w", encoding="utf-8") as f:
        for s in slots:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    total = sum(1 for s in slots if (s.get("question_ko") or "").strip())
    print(f"\n워크시트에서 {n_new}개 반영 | 경고 {n_warn}개")
    print(f"작성 완료 {total}/{len(slots)} → {outp}")
    if total < len(slots):
        miss = [s["qid"] for s in slots if not (s.get("question_ko") or "").strip()]
        print(f"미작성 {len(miss)}개: {', '.join(miss[:10])}"
              f"{' ...' if len(miss) > 10 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
