#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
최종 코퍼스 병합

입력
    corpus_units.jsonl              T4 방위사업청 행정규칙 220건 (07 파서)
    corpus_units_law.jsonl          T1~T3 법령 24건 (14 파서)
    corpus_units_admrul_scope.jsonl T4 국방부·산업부 행정규칙 (07 파서, 선택)
    scope_map.json                  경계 판정 정본

하는 일
  1. unit_id 좌표계가 동일하므로 그대로 합친다.
  2. scope_map 으로 경계를 재확인한다. in_scope 계열이 아닌 문서의 unit 은
     제외하고 사유를 기록한다. (수집 이후 판정이 바뀌었을 수 있다)
  3. unit_id 충돌을 검출한다. 충돌이 있으면 파서 버그이므로 중단 수준의 경고다.
  4. 위계·문서·unit·문자수 통계를 낸다. 커버리지 조작 설계의 기준값이다.

출력
    corpus_final.jsonl
    corpus_report.md

사용법
    py 15_merge_corpus.py
    py 15_merge_corpus.py --no-scope-filter    # 경계 필터 없이 전부 병합
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

INPUTS = [
    ("corpus_units.jsonl", "방위사업청 행정규칙"),
    ("corpus_units_law.jsonl", "법령 T1~T3"),
    ("corpus_units_admrul_scope.jsonl", "국방부·산업부 행정규칙"),
]
SCOPE = "scope_map.json"


def nkey(s: str) -> str:
    s = re.sub(r'[ㆍ·・]', '', s)
    s = re.sub(r'\s+', '', s)
    return s.replace('(', '').replace(')', '')


def load(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(scope_filter: bool = True) -> None:
    scope = {}
    if scope_filter and Path(SCOPE).exists():
        raw = json.loads(Path(SCOPE).read_text(encoding="utf-8"))
        scope = {nkey(k): v.get("scope", "") for k, v in raw.items()}
        print(f"경계 판정 {len(scope)}종 로드")
    elif scope_filter:
        print("scope_map.json 없음 — 경계 필터 없이 진행합니다")

    units: list[dict] = []
    srcstat: list[tuple[str, int, int]] = []
    for path, label in INPUTS:
        rows = load(path)
        if not rows:
            print(f"  (없음) {path}")
            continue
        for u in rows:
            u["_source"] = label
        units += rows
        docs = len({u.get("doc_id") for u in rows})
        print(f"  {label:22} {len(rows):>7,} unit / {docs} 문서")
        srcstat.append((label, docs, len(rows)))

    # ---------------------------------------------------- 경계 필터
    dropped: dict[str, int] = defaultdict(int)
    kept: list[dict] = []
    unknown_docs: set[str] = set()
    for u in units:
        name = str(u.get("doc_name", ""))
        if not scope:
            kept.append(u)
            continue
        sc = scope.get(nkey(name))
        if sc is None:
            # 인용된 적이 없는 문서다. 수집했으므로 코퍼스에 남긴다.
            unknown_docs.add(name)
            kept.append(u)
        elif sc.startswith("in_scope"):
            kept.append(u)
        else:
            dropped[f"{name} [{sc}]"] += 1

    # ---------------------------------------------------- 충돌
    cnt = Counter(u["unit_id"] for u in kept)
    dup = [k for k, v in cnt.items() if v > 1]

    with open("corpus_final.jsonl", "w", encoding="utf-8") as f:
        for u in kept:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    # ---------------------------------------------------- 통계
    by_tier = Counter(u.get("tier", "?") for u in kept)
    chars_tier: Counter = Counter()
    docs_tier: dict[str, set] = defaultdict(set)
    for u in kept:
        chars_tier[u.get("tier", "?")] += u.get("char_len", 0)
        docs_tier[u.get("tier", "?")].add(u.get("doc_id"))
    by_level = Counter(u.get("level", "?") for u in kept)
    total_chars = sum(u.get("char_len", 0) for u in kept)
    n_docs = len({u.get("doc_id") for u in kept})
    deleted = sum(1 for u in kept if u.get("deleted"))

    L = ["# 최종 코퍼스", "",
         f"- 문서 {n_docs}건 / unit {len(kept):,}개 / 문자 {total_chars:,}",
         f"- unit_id 충돌 {len(dup)}건" + (" **파서 점검 필요**" if dup else ""),
         f"- 삭제 표시 unit {deleted:,}개 (검색 대상에서 제외 권장)", "",
         "## 입력 구성", "", "| 출처 | 문서 | unit |", "|---|---|---|"]
    for label, d, n in srcstat:
        L.append(f"| {label} | {d} | {n:,} |")

    L += ["", "## 위계별", "", "| 위계 | 문서 | unit | 문자수 | 비중 |", "|---|---|---|---|---|"]
    for t in sorted(by_tier, key=lambda x: str(x)):
        share = chars_tier[t] / total_chars * 100 if total_chars else 0
        L.append(f"| {t} | {len(docs_tier[t])} | {by_tier[t]:,} | "
                 f"{chars_tier[t]:,} | {share:.1f}% |")

    L += ["", "## 층위별 unit", "", "| 층위 | 개수 |", "|---|---|"]
    for lv, n in by_level.most_common():
        L.append(f"| {lv} | {n:,} |")

    if dropped:
        L += ["", "## 경계 필터로 제외된 문서", "",
              "수집했으나 경계 판정이 in_scope 가 아니다.", "",
              "| 문서 [판정] | unit |", "|---|---|"]
        for k, v in sorted(dropped.items(), key=lambda x: -x[1])[:30]:
            L.append(f"| {k} | {v:,} |")

    if unknown_docs:
        L += ["", f"## 인용된 적 없는 문서 ({len(unknown_docs)}건)", "",
              "다른 규정이 한 번도 인용하지 않은 문서다. 코퍼스에는 남겨둔다.",
              "커버리지 조작 시 '주변부 문서'로 분류해 우선 제거 대상으로 쓸 수 있다.", ""]
        for n in sorted(unknown_docs)[:25]:
            L.append(f"- {n}")
        if len(unknown_docs) > 25:
            L.append(f"- … 외 {len(unknown_docs)-25}건")

    if dup:
        L += ["", "## unit_id 충돌 (파서 버그)", ""]
        for k in dup[:20]:
            L.append(f"- {k} ({cnt[k]}회)")

    L += ["", "## 다음", "",
          "1. L3 후보의 gold evidence 가 실제로 이 코퍼스에 존재하는지 검증한다.",
          "   참조된 조가 삭제되었거나 조번호가 이동했으면 후보에서 제외한다.",
          "2. 검증을 통과한 후보에서 문항 100개를 층화 추출한다.",
          "3. 위 문자수가 커버리지 조작의 기준값이다. gold unit 제거 시",
          "   동일 문자수만큼 무관 조문으로 padding 하여 분량을 고정한다."]

    Path("corpus_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"\n-> corpus_final.jsonl ({len(kept):,} unit / {n_docs} 문서 / {total_chars:,}자)")
    print("-> corpus_report.md")
    if dropped:
        print(f"   경계 필터로 {sum(dropped.values()):,} unit 제외")
    if dup:
        print(f"   !! unit_id 충돌 {len(dup)}건 — 파서 점검 필요")


if __name__ == "__main__":
    main(scope_filter="--no-scope-filter" not in sys.argv)
