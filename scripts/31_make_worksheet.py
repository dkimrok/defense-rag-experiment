#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
31_make_worksheet.py — 근거 조문이 실린 작성용 워크시트 생성

기존 워크시트는 슬롯 목록(qid·수준·근거요약)만 있어 조문을 따로 찾아봐야 했다.
question_slots.jsonl 에는 gold_evidence[].text_span 으로 조문 전문이,
L4 슬롯에는 distractors.stale_versions[].diff_note 로 구버전 전문이 들어 있다.
이 스크립트는 그것을 수준별 마크다운으로 펼쳐, 파일 하나만 보고 문항을
쓸 수 있게 한다.

수준별 지침을 슬롯마다 붙인다. 특히 OOS 는 흔한 실수가 있다:
  OOS 슬롯의 gold 는 '인용하는' 조문이지 '인용된' 문서가 아니다.
  질문은 코퍼스 밖에 있는 '인용된' 문서의 내용을 물어야 한다.
  인용하는 조문만 읽고 답할 수 있으면 그 문항은 OOS 가 아니다.
  (실측: OOS-001 이 인용 조문만으로 답이 되어 모델이 확신 있게 답해버렸다)

출력
  worksheet/00_index.md         전체 현황
  worksheet/L1.md ~ OOS.md      수준별 작성 파일
  32_fill_worksheet.py 로 되돌린다.

사용법
  py 31_make_worksheet.py question_slots.jsonl --out worksheet
  py 31_make_worksheet.py question_slots.jsonl --done question_final.jsonl \\
      --dup audit/gold_dup.tsv --out worksheet
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

GUIDE = {
    "L1": [
        "단일 조에서 사실 하나를 묻는다. 답은 15자 이내 단답.",
        "조문에 그 답이 유일하게 있어야 한다(다른 조에도 있으면 L1 이 아니다).",
    ],
    "L2": [
        "아래 조문들을 **모두** 봐야 답이 나오게 쓴다. 하나만 보면 못 풀어야 한다.",
        "첫 조가 다른 조를 가리키는 구조(준용·위임)를 이용하면 자연스럽다.",
    ],
    "L3": [
        "법 → 시행령 → 부령을 횡단해야 답이 완성되게 쓴다.",
        "상위법만 보면 원칙만 나오고, 하위 규정을 봐야 구체값이 나오는 형태가 좋다.",
    ],
    "L4": [
        "현행과 구버전이 함께 제시된다. **시점 판단**을 요구하는 문항을 쓴다.",
        "답에 세 요소를 넣는다: 적용 여부 / 근거 조문 / 기준 시점.",
        "구버전 내용은 distractors 로만 쓰고, 질문에 구버전 표현을 넣지 않는다.",
    ],
    "OOS": [
        "**답이 없어야 하는 문항이다.** 인용된 문서(코퍼스 밖)의 내용을 물어야 한다.",
        "아래 조문은 '인용하는' 쪽이다. 이 조문만 읽고 답이 되면 실패한 문항이다.",
        "answer_short 에는 정답 대신 '코퍼스 내 근거 없음'과 그 이유를 적는다.",
    ],
}

OOS_KIND = {
    "out_of_scope": "일반법 등 코퍼스 경계 밖 문서",
    "abolished_cited": "폐지된 규정",
    "unobtainable_cited": "비공개 문서",
    "deleted_provision": "삭제된 조문",
}


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def level_key(qid: str) -> str:
    return qid.split("-")[1]


def fmt_date(s: str) -> str:
    s = str(s or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else (s or "-")


def locator_str(loc: dict) -> str:
    if not loc:
        return ""
    order = ["조", "조의", "항", "호", "목"]
    parts = [f"제{loc[k]}{k}" if k == "조" else f"{k} {loc[k]}"
             for k in order if loc.get(k)]
    return " ".join(parts)


def cited_target(*texts: str) -> str:
    """인용 대상 문서명. out_of_scope_reason 은 유형만 담고 있어
    실제 문서명은 level_justification 의 「」 안에 있다."""
    for t in texts:
        m = re.findall(r'「([^」]+)」', t or "")
        if m:
            return m[-1]
    return ""


def dedup_span(t: str) -> str:
    """text_span 중복 제거.

    jo_fulltext 조립이 '조 전문' 뒤에 각 항·호를 다시 이어붙여
    같은 내용이 2~3회 반복된다. 1500자 상한을 중복이 먹어 실제 내용이
    잘리는 원인이기도 하다. 앞줄에 이미 포함된 줄은 버린다.
    """
    lines = [x for x in (t or "").splitlines() if x.strip()]
    kept: list[str] = []
    acc = ""
    for ln in lines:
        flat = re.sub(r'\s+', '', ln)
        if flat and flat in acc:
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

    slots = load(a[1])
    out = Path(opt("--out", "worksheet"))
    out.mkdir(parents=True, exist_ok=True)

    done = set()
    dpath = opt("--done", None)
    if dpath and Path(dpath).exists():
        for r in load(dpath):
            if (r.get("question_ko") or "").strip():
                done.add(r["qid"])

    weak: dict[str, list] = defaultdict(list)
    dpp = opt("--dup", None)
    if dpp and Path(dpp).exists():
        for line in Path(dpp).read_text(encoding="utf-8").splitlines()[1:]:
            f = line.split("\t")
            if len(f) >= 7 and f[4].isdigit() and int(f[4]) > 0:
                weak[f[0]].append((f[2], f[4], f[5]))

    by_lv: dict[str, list] = defaultdict(list)
    for s in slots:
        by_lv[level_key(s["qid"])].append(s)

    idx = ["# 문항 작성 워크시트", "",
           f"- 슬롯 {len(slots)}개 / 작성완료 {len(done)}개 / 남은 {len(slots)-len(done)}개",
           "- 근거 조문은 각 수준 파일에 전문이 실려 있다. 별도 자료 불필요.",
           "", "## 공통 규칙", "",
           "- R1 질문에 gold 조문의 연속 5어절 이상을 쓰지 않는다(어휘 누출)",
           "- R2 단답 15자 이내 / 서술 2~3문장 / L4는 적용여부·근거·시점 3요소",
           "- R3 고유명사·연도 최소화",
           "- R5 기준일(2026-07-21)은 질문문에 쓰지 않는다",
           "", "## 파일", ""]

    for lv in ["L1", "L2", "L3", "L4", "OOS"]:
        rows = by_lv.get(lv, [])
        if not rows:
            continue
        todo = [r for r in rows if r["qid"] not in done]
        idx.append(f"- `{lv}.md` — {len(rows)}슬롯 중 남은 {len(todo)}개")

        L = [f"# {lv} 작성 워크시트", "",
             f"남은 슬롯 {len(todo)} / 전체 {len(rows)}", "", "## 이 수준의 지침", ""]
        L += [f"- {g}" for g in GUIDE[lv]]
        L += ["", "작성란의 `- question_ko:` 등 뒤에 이어서 쓴다. "
              "여러 줄로 써도 되고, 다음 `- ` 항목 전까지가 값이다.", "", "---", ""]

        for s in rows:
            qid = s["qid"]
            if qid in done:
                continue
            L.append(f"## {qid}")
            L.append("")
            L.append(f"- 수준 근거: {s.get('level_justification','')}")
            if weak.get(qid):
                d = weak[qid][0]
                L.append(f"- **[약한 도구] 다른 문서에 형제 조문 {d[1]}건 "
                         f"(유사도 {d[2]}). 이 조를 지워도 지식이 안 지워진다. "
                         f"가능하면 형제에 없는 값을 답으로 잡을 것.**")
            if not s.get("answerable", True):
                reason = s.get("out_of_scope_reason") or ""
                just = s.get("level_justification") or ""
                kind = (reason.split(":")[0].strip()
                        or just.split(":")[0].strip())
                tgt = cited_target(just, reason)
                L.append(f"- 유형: **{kind}** ({OOS_KIND.get(kind,'')})")
                L.append(f"- **물어야 할 대상: 「{tgt}」의 내용** "
                         f"(코퍼스 밖 → 답할 수 없어야 정상)")
            L.append("")

            ge = s.get("gold_evidence") or []
            L.append(f"### 근거 조문 ({len(ge)}개)")
            L.append("")
            for i, g in enumerate(ge, 1):
                head = (f"**[{i}] {g.get('doc_name','')} {locator_str(g.get('locator'))}** "
                        f"· {g.get('tier','')} · 시행 {fmt_date(g.get('effective_date'))}"
                        f" · {g.get('necessity','required')}")
                L += [head, "", f"`{g.get('unit_id','')}`", "", "```",
                      dedup_span(g.get("text_span") or "").strip(), "```", ""]

            sv = (s.get("distractors") or {}).get("stale_versions") or []
            if sv:
                L.append("### 구버전 (distractors 용 · 질문에 쓰지 말 것)")
                L.append("")
                for v in sv:
                    L += [f"**구버전 {v.get('issue_no','')}호 · 시행 "
                          f"{fmt_date(v.get('effective_date'))}**", "", "```",
                          dedup_span(v.get("diff_note") or "").strip(), "```", ""]

            L += ["### 작성란", "",
                  "- question_ko: ",
                  "- answer_short: ",
                  "- answer_long: ",
                  "", "---", ""]

        (out / f"{lv}.md").write_text("\n".join(L), encoding="utf-8")

    (out / "00_index.md").write_text("\n".join(idx), encoding="utf-8")
    print(f"-> {out}/  " + ", ".join(
        f"{lv}.md" for lv in ["L1", "L2", "L3", "L4", "OOS"] if by_lv.get(lv)))
    for lv in ["L1", "L2", "L3", "L4", "OOS"]:
        if by_lv.get(lv):
            n = len([r for r in by_lv[lv] if r["qid"] not in done])
            p = out / f"{lv}.md"
            print(f"   {lv:4s} 남은 {n:3d}개 | {p.stat().st_size/1024:6.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
