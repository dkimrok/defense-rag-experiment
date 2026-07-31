#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
39_sample_oos.py — 범위 밖(OOS) 문항 후보 추출

왜 필요한가
  범위 밖 문항이 17개뿐이라 '주변부를 걷어내면 정직해진다'는 발견의
  신뢰구간이 넓다(9/17 → 95% CI 약 [31, 74]). 문항을 늘리면 확정 서술로
  올릴 수 있다.

  확장 여지는 일반법 인용에만 있다. oos_sources.jsonl 기준:
    out_scope_targets 보유 552 레코드 (대상 문서 188종)   ← 여기서 뽑는다
    abolished_cited 8 / unobtainable_cited 6              ← 이미 거의 소진

문항 설계 원칙
  질문은 **인용된 문서(코퍼스 밖)의 내용**을 물어야 한다.
  인용하는 조문만 읽고 답이 되면 그 문항은 실패다(실측: OOS-001 이 그랬다).
  각 레코드의 refs 에 인용 대상의 조·항이 들어 있으므로
  ("「군인사법」 제57조 제1항"), 그 조가 정하는 바를 물으면 안전하다.

선정 기준
  - 이미 쓴 문항의 인용 조문(unit_id)과 대상 문서는 제외
  - 대상 문서당 상한을 둬 특정 법(국가계약법 등)에 몰리지 않게 한다
  - 인용 대상의 조 번호가 명시된 레코드를 우선한다(질문 초점이 분명해짐)
  - 인용하는 조문이 너무 길면 그 안에 답이 들어 있을 위험이 커지므로 후순위

출력
  question_oos_extra.jsonl   31 이 읽는 슬롯 스키마(작성란 비어 있음)

사용법
  py 39_sample_oos.py oos_sources.jsonl corpus_final.jsonl \\
      --exclude question_final.jsonl --n 25 --max-per-target 2 \\
      --out question_oos_extra.jsonl
  py 31_make_worksheet.py question_oos_extra.jsonl --out worksheet_oos
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20260721
RE_WS = re.compile(r'\s+')


def load(p) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def dedup_parts(parts: list[str]) -> str:
    kept, acc = [], ""
    for x in parts:
        f = RE_WS.sub('', x or '')
        if not f or f in acc:
            continue
        kept.append(x)
        acc += f
    return "\n".join(kept)


def jo_fulltext(units: dict, base: str) -> str:
    """조 전문 조립. 17/24 와 같은 중복 제거 규칙을 쓴다."""
    parts = []
    for uid in sorted(units):
        if uid == base or uid.startswith(base + ":"):
            t = (units[uid].get("text") or "").strip()
            if t:
                parts.append(t)
    return dedup_parts(parts)


def main() -> int:
    a = sys.argv
    if len(a) < 3:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    src = load(a[1])
    corpus = {u["unit_id"]: u for u in load(a[2])}
    n_want = int(opt("--n", "25"))
    cap = int(opt("--max-per-target", "2"))
    rng = random.Random(int(opt("--seed", str(SEED))))
    outp = opt("--out", "question_oos_extra.jsonl")
    as_of = opt("--as-of", "2026-07-21")

    # 이미 쓴 문항 제외
    used_units, used_targets = set(), set()
    ex = opt("--exclude", None)
    start_no = 18
    if ex and Path(ex).exists():
        prev = load(ex)
        for s in prev:
            if s.get("answerable", True):
                continue
            for g in s.get("gold_evidence") or []:
                used_units.add(g.get("unit_id", "").rsplit(":", 3)[0])
                used_units.add(g.get("unit_id", ""))
            m = re.findall(r'「([^」]+)」', s.get("level_justification", ""))
            if m:
                used_targets.add(m[-1])
        nums = [int(re.search(r'OOS-(\d+)', s["qid"]).group(1))
                for s in prev if "OOS-" in s.get("qid", "")]
        start_no = max(nums) + 1 if nums else 18
        print(f"기존 범위밖 문항 {len(nums)}개 확인 | 제외 대상 문서 "
              f"{len(used_targets)}종 | 새 qid 는 OOS-{start_no:03d} 부터")

    # 후보 구성: (레코드, 인용대상, 인용표면)
    cands = []
    for r in src:
        outs = set(r.get("out_scope_targets") or [])
        if not outs:
            continue
        uid = r.get("unit_id", "")
        if uid in used_units or uid not in corpus:
            continue
        for ref in r.get("refs") or []:
            tgt = ref.get("target_name", "")
            if tgt not in outs or tgt in used_targets:
                continue
            has_jo = bool(str(ref.get("jo") or "").strip())
            cands.append(dict(rec=r, target=tgt, ref=ref, has_jo=has_jo,
                              surface=ref.get("surface") or f"「{tgt}」"))

    if not cands:
        print("후보가 없습니다. --exclude 조건을 확인하십시오.")
        return 1

    # 조 번호가 명시된 것 우선, 인용 조문이 짧은 것 우선
    def jolen(c):
        return len(jo_fulltext(corpus, c["rec"]["unit_id"]))
    rng.shuffle(cands)
    cands.sort(key=lambda c: (not c["has_jo"], jolen(c)))

    # 대상 문서당 상한을 지키며 선정
    picked, per = [], Counter()
    for c in cands:
        if len(picked) >= n_want:
            break
        if per[c["target"]] >= cap:
            continue
        if any(p["rec"]["unit_id"] == c["rec"]["unit_id"] for p in picked):
            continue
        per[c["target"]] += 1
        picked.append(c)

    if len(picked) < n_want:
        print(f"! 상한 {cap} 로는 {len(picked)}개만 뽑혔습니다. "
              f"--max-per-target 을 올리거나 --n 을 낮추십시오.")

    # 슬롯 생성
    slots = []
    for i, c in enumerate(picked):
        r, ref = c["rec"], c["ref"]
        uid = r["unit_id"]
        u = corpus[uid]
        span = jo_fulltext(corpus, uid)
        qid = f"DAPA-OOS-{start_no + i:03d}"
        loc = {"조": str(r.get("jo", ""))}
        if r.get("jo_branch"):
            loc["조의"] = str(r["jo_branch"])
        slots.append(dict(
            qid=qid, as_of=as_of, level=0,
            level_justification=(f"out_of_scope: {r.get('doc_name','')} "
                                 f"제{r.get('jo','')}조가 「{c['target']}」를 인용 "
                                 f"(인용 표면: {c['surface']})"),
            question_ko="", question_en="", answerable=False,
            out_of_scope_reason="out_of_scope",
            answer_short="", answer_long="", answer_alternatives=[],
            gold_evidence=[dict(
                unit_id=uid, tier=u.get("tier", ""),
                doc_type=u.get("doc_type", ""), doc_name=r.get("doc_name", ""),
                doc_id=r.get("doc_id", ""), issue_no=r.get("issue_no", ""),
                effective_date=u.get("effective_date", ""),
                locator=loc, text_span=span, necessity="required")],
            evidence_profile=dict(unit_count=1, required_count=1, tier_span=1,
                                  has_supplementary=False),
            distractors=dict(stale_versions=[], sibling_provisions=[],
                             cross_tier_lookalikes=[]),
            source=dict(origin="oos_확장추출",
                        note=f"인용 대상 {c['surface']}"),
            quality_checks=dict(lexical_leak_max_ngram=None,
                                lexical_leak_pass=None,
                                single_answer_verified=False,
                                proper_noun_count=None),
            annotation={}, condition_labels={}))

    with open(outp, "w", encoding="utf-8") as f:
        for s in slots:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n후보 {len(cands):,} 중 {len(slots)}개 선정 → {outp}")
    print(f"대상 문서 {len(per)}종 (문서당 최대 {cap})")
    for t, n in per.most_common():
        print(f"   {n}  {t}")
    lens = [len(s["gold_evidence"][0]["text_span"]) for s in slots]
    print(f"\n인용 조문 길이 중앙값 {sorted(lens)[len(lens)//2]:,}자 "
          f"(최대 {max(lens):,})")
    print("\n다음: py 31_make_worksheet.py "
          f"{outp} --out worksheet_oos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
