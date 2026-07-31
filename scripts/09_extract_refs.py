#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
위계횡단 참조 링크 추출기 — L3 문항 후보 생성

목적
    행정규칙(T4) 본문에는 상위법을 가리키는 명시적 참조가 들어 있다.
        "영 제22조제1항에 따라 …"        -> T2 방위사업법 시행령
        "법 제12조에 의하여 …"            -> T1 방위사업법
        "「혁신법 시행령」 제45조제1항 …"  -> 외부법령
    이 참조를 정규식으로 추출하면 thdCmp에 의존하지 않고도
    T4 -> T1/T2/T3 gold evidence 체인을 자동으로 만들 수 있다.

    L3(위계횡단 절차 재구성) 문항의 정의는 "최소 2개 위계를 가로지르는
    gold evidence"이므로, 2개 이상 위계를 동시에 참조하는 조가 곧 후보다.

    동시에 이 스크립트는 코퍼스 경계를 진단한다. 인용되는데 코퍼스에 없는
    법령이 무엇인지 집계하여, 경계에 넣을지 out-of-scope 재료로 쓸지 정한다.

약어 정의 주의
    각 행정규칙은 제1조나 제2조에서 "「방위사업법」(이하 "법"이라 한다)"
    같은 방식으로 약어를 정의한다. 규정마다 약어가 가리키는 대상이 다를 수
    있으므로, 문서별로 약어 정의를 먼저 추출한 뒤 참조를 해석한다.

사용법
    py 09_extract_refs.py corpus_units.jsonl
        -> refs.jsonl          조 단위 참조 목록
        -> l3_candidates.jsonl L3 문항 후보 (2개 이상 위계 참조)
        -> refs_report.md      집계 및 코퍼스 경계 진단
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------- 패턴

# 약어 정의: 「방위사업법」(이하 "법"이라 한다)
RE_ALIAS = re.compile(r'[「『]([^」』]{2,60})[」』]\s*\(\s*이하\s*[""\'"]([^""\'"]{1,20})[""\'"]\s*(?:이)?라\s*한다\s*\)')

# 약어 기반 참조: 법 제12조, 영 제22조제1항, 규칙 제3조의2
RE_ALIAS_REF = re.compile(r'(?<![가-힣A-Za-z])([가-힣]{1,10})\s*제\s*(\d{1,3})\s*조(?:\s*의\s*(\d{1,2}))?'
                          r'(?:\s*제\s*(\d{1,3})\s*항)?(?:\s*제\s*(\d{1,3})\s*호)?')

# 정식명칭 참조: 「국가계약법 시행령」 제26조제1항
RE_FULL_REF = re.compile(r'[「『]([^」』]{2,60})[」』]\s*제\s*(\d{1,3})\s*조(?:\s*의\s*(\d{1,2}))?'
                         r'(?:\s*제\s*(\d{1,3})\s*항)?(?:\s*제\s*(\d{1,3})\s*호)?')

# 위계 판정: 약어/명칭 -> tier
# 순서 주의: '훈령'은 '령'으로 끝나므로 T4 판정을 T2보다 먼저 해야 한다.
TIER_RULES = [
    (re.compile(r'훈령$|예규$|고시$|지침$|규정$|기준$|세칙$|조건$|표준$'), "T4_행정규칙"),
    (re.compile(r'시행규칙$|규칙$'), "T3_부령"),
    (re.compile(r'시행령$|령$'),     "T2_대통령령"),
    (re.compile(r'법률$|법$'),       "T1_법률"),
]

# 코퍼스 경계 (설계 확정안)
IN_SCOPE_HINT = ["방위사업법", "국방과학기술혁신 촉진법", "혁신법",
                 "국방전력발전업무훈령"]
OUT_SCOPE_HINT = ["국가계약법", "국가를 당사자로 하는 계약에 관한 법률",
                  "지방계약법", "전자정부법", "군수품관리법"]


def tier_of(name: str) -> str:
    n = name.strip()
    for pat, t in TIER_RULES:
        if pat.search(n):
            return t
    return "UNK"


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


# ---------------------------------------------------------------- 본체

def build_alias_map(units: list[dict]) -> dict[str, str]:
    """한 문서 안의 약어 정의를 모은다. 약어 -> 정식명칭"""
    amap: dict[str, str] = {}
    for u in units:
        for m in RE_ALIAS.finditer(u.get("text", "")):
            full, alias = norm(m.group(1)), m.group(2).strip()
            if alias and alias not in amap:
                amap[alias] = full
    return amap


def extract_refs(u: dict, amap: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    txt = u.get("text", "")

    for m in RE_FULL_REF.finditer(txt):
        nm = norm(m.group(1))
        out.append(dict(kind="full", target_name=nm, target_tier=tier_of(nm),
                        jo=m.group(2), jo_branch=m.group(3) or "0",
                        hang=m.group(4) or "", ho=m.group(5) or "",
                        surface=m.group(0)[:60]))

    for m in RE_ALIAS_REF.finditer(txt):
        word = m.group(1).strip()
        if word not in amap:
            continue                      # 정의된 약어만 신뢰한다
        nm = amap[word]
        out.append(dict(kind="alias", target_name=nm, target_tier=tier_of(nm),
                        alias=word, jo=m.group(2), jo_branch=m.group(3) or "0",
                        hang=m.group(4) or "", ho=m.group(5) or "",
                        surface=m.group(0)[:60]))

    # 중복 제거
    seen, uniq = set(), []
    for r in out:
        k = (r["target_name"], r["jo"], r["jo_branch"], r["hang"], r["ho"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def scope_of(name: str) -> str:
    for h in IN_SCOPE_HINT:
        if h in name:
            return "in_scope"
    for h in OUT_SCOPE_HINT:
        if h in name:
            return "out_of_scope"
    return "unknown"


def main(path: str) -> None:
    units = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    bydoc: dict[str, list[dict]] = defaultdict(list)
    for u in units:
        bydoc[u.get("doc_id", "")].append(u)

    ref_rows: list[dict] = []
    l3: list[dict] = []
    cited = Counter()
    tier_hits = Counter()
    docs_scanned = 0

    for doc_id, us in bydoc.items():
        docs_scanned += 1
        amap = build_alias_map(us)
        # 조 단위로 묶어서 참조를 집계한다
        byjo: dict[tuple, list[dict]] = defaultdict(list)
        for u in us:
            if u.get("level") in ("jo", "hang", "ho", "mok") and not u.get("deleted"):
                byjo[(u.get("jo"), u.get("jo_branch"))].append(u)

        for (jo, br), group in byjo.items():
            refs: list[dict] = []
            for u in group:
                refs.extend(extract_refs(u, amap))
            if not refs:
                continue
            seen, uniq = set(), []
            for r in refs:
                k = (r["target_name"], r["jo"], r["jo_branch"], r["hang"], r["ho"])
                if k not in seen:
                    seen.add(k)
                    uniq.append(r)

            head = next((u for u in group if u["level"] == "jo"), group[0])
            tiers = {r["target_tier"] for r in uniq if r["target_tier"] != "UNK"}
            ext_tiers = {t for t in tiers if t != "T4_행정규칙"}
            for r in uniq:
                cited[r["target_name"]] += 1
                tier_hits[r["target_tier"]] += 1

            row = dict(doc_id=doc_id, doc_name=head.get("doc_name", ""),
                       issue_no=head.get("issue_no", ""),
                       jo=jo, jo_branch=br,
                       jo_title=head.get("jo_title", ""),
                       unit_id=head.get("unit_id", ""),
                       n_refs=len(uniq), tiers=sorted(tiers),
                       ext_tier_span=len(ext_tiers), refs=uniq)
            ref_rows.append(row)
            # L3 후보: 자기 위계(T4) 밖의 위계를 2개 이상 참조
            if len(ext_tiers) >= 2:
                l3.append(row)

    def dump(name: str, rows: list[dict]) -> None:
        with open(name, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {name} ({len(rows)}건)")

    dump("refs.jsonl", ref_rows)
    dump("l3_candidates.jsonl", l3)

    # ------------------------------------------------------ 리포트
    L = ["# 위계횡단 참조 분석", "",
         f"- 문서 {docs_scanned}건 / 참조를 가진 조 {len(ref_rows):,}개",
         f"- **L3 후보(외부 위계 2개 이상 참조) {len(l3):,}개 조**", ""]

    L += ["## 참조 위계 분포", "", "| 위계 | 참조수 |", "|---|---|"]
    for k, v in tier_hits.most_common():
        L.append(f"| {k} | {v:,} |")

    span = Counter(r["ext_tier_span"] for r in ref_rows)
    L += ["", "## 조별 외부위계 span 분포", "",
          "| 외부위계 수 | 조 개수 | 판정 |", "|---|---|---|"]
    for k in sorted(span):
        tag = "L3 후보" if k >= 2 else ("L2~L3 경계" if k == 1 else "-")
        L.append(f"| {k} | {span[k]:,} | {tag} |")

    L += ["", "## 코퍼스 경계 진단 — 인용 상위 40종", "",
          "| 인용 법령/규정 | 인용횟수 | 위계 | 경계 판정 |", "|---|---|---|---|"]
    for nm, c in cited.most_common(40):
        L.append(f"| {nm} | {c} | {tier_of(nm)} | {scope_of(nm)} |")

    unk = [(n, c) for n, c in cited.most_common() if scope_of(n) == "unknown"][:25]
    L += ["", "## 경계 미판정 항목 (수동 결정 필요)", ""]
    for n, c in unk:
        L.append(f"- {n} ({c}회)")

    L += ["", "## L3 후보 상위 30조", "",
          "| 규정 | 조 | 조제목 | 참조수 | 위계 |", "|---|---|---|---|---|"]
    for r in sorted(l3, key=lambda x: -x["n_refs"])[:30]:
        L.append(f"| {r['doc_name']} | 제{r['jo']}조"
                 f"{'의'+str(r['jo_branch']) if str(r['jo_branch']) not in ('0','') else ''} | "
                 f"{r['jo_title']} | {r['n_refs']} | {', '.join(r['tiers'])} |")

    L += ["", "## 다음 작업", "",
          "1. 경계 미판정 항목을 in_scope / out_of_scope 로 확정한다.",
          "2. in_scope 로 결정한 법령은 코퍼스에 추가 수집한다.",
          "3. out_of_scope 인용이 많은 조는 범위밖 20문항의 원천으로 표시한다.",
          "4. L3 후보에서 20개를 층화 추출하여 문항을 작성한다.",
          "   참조된 상위 조문을 실제로 가져와 gold evidence 체인을 완성한다."]

    Path("refs_report.md").write_text("\n".join(L), encoding="utf-8")
    print("-> refs_report.md")
    print(f"\nL3 후보 {len(l3)}개 조 확보 (목표 20문항)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1])
