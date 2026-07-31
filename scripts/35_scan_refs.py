#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
35_scan_refs.py — 질문문의 위치 참조(조·항·호)와 문서명 참조 점검

왜 필요한가
  질문에 '제109조에 따르면' 같은 위치 참조가 들어가면 세 가지가 깨진다.
  (1) 24/25 의 tokenize_ko 가 조 번호를 통째 토큰으로 뽑는다.
      질문의 '제109조' 가 gold 청크와 직접 어휘 매칭되어 BM25 검색이
      지름길로 풀린다. recall@k 가 커버리지가 아니라 어휘일치로 결정된다.
  (2) 조 번호는 232개 문서에서 유일하지 않다. 다른 문서의 같은 번호 조를
      끌어와 엉뚱한 근거로 확신 있게 답할 수 있다.
  (3) 커버리지를 낮춰 gold 조를 지웠을 때, 모델이 '그 조가 검색결과에
      없다'는 것만으로 기권할 수 있게 된다. 메타인지를 공짜로 주는 셈이라
      '모른다는 것을 모른다'는 측정 대상 자체가 오염된다.

  문서명 참조는 성격이 다르다. 위치 포인터가 아니라 주제 한정자이고,
  없으면 문항이 성립하지 않는 경우가 많다('이 지침의 적용범위는?').
  그래서 제거 대상이 아니라 '필요한지' 판단 대상으로 보고한다.

판정
  [제거] 조·항·호 번호
  [검토] gold 문서명이 질문에 있음 → 없어도 답이 유일한지 확인
  [필요] OOS 에서 인용 대상 문서명 → 오히려 있어야 문항이 성립
  [주의] 문서명 없이 일반어(적용범위·목적·정의 등)만 있는 질문 → 모호

사용법
  py 35_scan_refs.py question_final.jsonl
  py 35_scan_refs.py question_final.jsonl --tsv refs_scan.tsv
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RE_JO = re.compile(r'제\s*\d+\s*조(?:\s*의\s*\d+)?')
RE_HANG = re.compile(r'제\s*\d+\s*항|[①-⑳]')
RE_HO = re.compile(r'제\s*\d+\s*호')
RE_BYEOLJI = re.compile(r'별지\s*제?\s*\d+\s*호')
GENERIC = ("적용범위", "적용 범위", "목적", "정의", "적용대상", "적용 대상",
           "구성", "운영원칙", "관리ㆍ운용 원칙", "기본원칙", "업무분장")


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def cited_target(*texts: str) -> str:
    for t in texts:
        m = re.findall(r'「([^」]+)」', t or "")
        if m:
            return m[-1]
    return ""


def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    rows = load(a[1])
    tsv = opt("--tsv", None)
    out = [("qid", "판정", "항목", "질문")]

    n_jo = n_doc = n_amb = n_ok = 0
    written = 0

    for r in rows:
        q = (r.get("question_ko") or "").strip()
        if not q:
            continue
        written += 1
        qid = r["qid"]
        flags: list[tuple[str, str]] = []

        # 위치 참조 — 별지 서식 번호는 제외(내용 식별자라 위치 포인터가 아님)
        q_nobyeol = RE_BYEOLJI.sub(" ", q)
        jo = RE_JO.findall(q_nobyeol)
        hang = RE_HANG.findall(q_nobyeol)
        ho = RE_HO.findall(q_nobyeol)
        if jo or hang or ho:
            n_jo += 1
            flags.append(("제거", " ".join(
                [f"조:{','.join(jo)}" if jo else "",
                 f"항:{','.join(hang)}" if hang else "",
                 f"호:{','.join(ho)}" if ho else ""]).strip()))

        # gold 문서명 참조
        golds = r.get("gold_evidence") or []
        names = [g.get("doc_name", "") for g in golds if g.get("doc_name")]
        hit = [n for n in set(names) if n and n in q]
        answerable = r.get("answerable", True)

        if not answerable:
            tgt = cited_target(r.get("level_justification"),
                               r.get("out_of_scope_reason"))
            if tgt and tgt in q:
                flags.append(("필요", f"인용대상 「{tgt}」 명시됨"))
            elif tgt:
                flags.append(("주의", f"인용대상 「{tgt}」 미명시 — "
                                      f"코퍼스 안에서 답이 되어버릴 수 있음"))
        elif hit:
            n_doc += 1
            flags.append(("검토", f"문서명 '{hit[0]}' — 없어도 답이 유일한지"))
        else:
            if any(g in q for g in GENERIC):
                n_amb += 1
                flags.append(("주의", "문서명 없이 일반어만 — 답이 모호할 수 있음"))

        if not flags:
            n_ok += 1
        for kind, item in flags:
            out.append((qid, kind, item, q))

    # ---------------------------------------------- 보고
    order = {"제거": 0, "주의": 1, "검토": 2, "필요": 3}
    body = sorted(out[1:], key=lambda x: (order.get(x[1], 9), x[0]))
    cur = None
    for qid, kind, item, q in body:
        if kind != cur:
            head = {"제거": "위치 참조 — 반드시 제거",
                    "주의": "모호 위험 — 확인 필요",
                    "검토": "문서명 참조 — 필요 여부 판단",
                    "필요": "OOS 인용대상 명시 — 정상"}[kind]
            print(f"\n{'='*66}\n{head}\n{'='*66}")
            cur = kind
        print(f"[{qid}] {item}")
        print(f"   {q}")

    print(f"\n{'='*66}")
    print(f"작성된 문항 {written}개")
    print(f"  위치 참조 있음 {n_jo}  |  문서명 참조 {n_doc}  |  "
          f"모호 위험 {n_amb}  |  문제 없음 {n_ok}")

    if tsv:
        with open(tsv, "w", encoding="utf-8") as f:
            for row in [out[0]] + body:
                f.write("\t".join(row) + "\n")
        print(f"-> {tsv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
