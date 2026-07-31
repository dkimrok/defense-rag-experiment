#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gold evidence 실물 검증 — L3 후보 풀 확정

지금까지 확인한 것은 "참조 대상 문서가 코퍼스 안에 있다"까지다.
정작 "참조된 조가 실제로 존재하는가"는 확인하지 않았다.
훈령이 「방위사업법 제57조」를 인용하는데 그 조가 삭제되었거나 조번호가
이동했으면 gold evidence 가 비어 문항이 성립하지 않는다.

이 스크립트는 각 참조를 코퍼스의 unit_id 로 실제 해석한다.

    참조 (방위사업법, 제12조제1항)
      -> 문서명으로 doc_id 조회        방위사업법 -> law:010107
      -> 조 좌표 생성                  law:010107:001200
      -> 코퍼스에 존재? 삭제 아님?

판정
    resolved        조가 존재하고 삭제되지 않음        -> gold evidence 사용 가능
    deleted_jo      조가 <삭제> 상태                   -> 사용 불가
    missing_jo      문서는 있으나 그 조가 없음         -> 네 번째 결손 유형
    missing_doc     문서 자체를 찾지 못함              -> 경계 판정 재확인 필요

L3 확정 조건
    외부 위계(자기 위계 제외) 참조가 모두 resolved 이고,
    그 위계가 여전히 2개 이상이어야 한다.

사용법
    py 16_verify_gold.py corpus_final.jsonl l3_revalidated.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

MATCH_MIN = 0.86

# 11_finalize_scope.py 의 약어 사전을 그대로 쓴다.
# 이걸 안 쓰면 '혁신법' 같은 짧은 약어가 코퍼스의
# '국방과학기술혁신 촉진법' 과 매칭되지 않아 missing_doc 으로 오판된다.
def _load_canonical() -> dict:
    try:
        import importlib.util
        f = Path(__file__).with_name("11_finalize_scope.py")
        if not f.exists():
            return {}
        sp = importlib.util.spec_from_file_location("scope11", str(f))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return dict(getattr(m, "CANONICAL", {}))
    except Exception as e:                                   # noqa: BLE001
        print(f"  (약어 사전 로드 실패: {e})")
        return {}


CANONICAL = _load_canonical()


def nkey(s: str) -> str:
    s = re.sub(r'[ㆍ·・]', '', s)
    s = re.sub(r'\s+', '', s)
    return s.replace('(', '').replace(')', '')


def code6(n: int, br: int = 0) -> str:
    return f"{n:04d}{br:02d}"


# ---------------------------------------------------------------- 코퍼스 색인

def build_index(path: str):
    """문서명 -> (prefix, doc_id) 와 존재하는 조 unit_id 집합을 만든다."""
    doc_of: dict[str, tuple[str, str]] = {}
    names: list[str] = []
    jo_units: set[str] = set()
    deleted: set[str] = set()
    doc_tier: dict[str, str] = {}
    doc_units: Counter = Counter()

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        u = json.loads(line)
        uid = u["unit_id"]
        prefix = uid.split(":", 1)[0]
        did = str(u.get("doc_id", ""))
        nm = str(u.get("doc_name", ""))
        k = nkey(nm)
        if k and k not in doc_of:
            doc_of[k] = (prefix, did)
            names.append(nm)
            doc_tier[k] = u.get("tier", "")
        doc_units[k] += 1
        if u.get("level") == "jo":
            jo_units.add(uid)
            if u.get("deleted"):
                deleted.add(uid)
    return doc_of, names, jo_units, deleted, doc_tier, doc_units


def resolve_doc(name: str, doc_of: dict, names: list[str]):
    k = nkey(name)
    if k in CANONICAL:                       # 약어 -> 정식명칭
        name = CANONICAL[k]
        k = nkey(name)
    if k in doc_of:
        return doc_of[k], 1.0, name
    best, score = None, 0.0
    for nm in names:
        pk = nkey(nm)
        r = SequenceMatcher(None, k, pk).ratio()
        # 포함 관계 단축로직은 길이 비율이 비슷할 때만 신뢰한다.
        # 긴 고시 이름 안에 짧은 법령명이 들어 있는 경우를 걸러야 한다.
        if len(k) >= 6 and (k in pk or pk in k):
            lr = min(len(k), len(pk)) / max(len(k), len(pk))
            if lr >= 0.6:
                r = max(r, 0.93)
        if r > score:
            best, score = nm, r
    if best and score >= MATCH_MIN:
        return doc_of[nkey(best)], round(score, 2), best
    return None, round(score, 2), best or ""


# ---------------------------------------------------------------- 본체

def main(corpus_path: str, cand_path: str) -> None:
    doc_of, names, jo_units, deleted, doc_tier, doc_units = build_index(corpus_path)
    print(f"약어 사전 {len(CANONICAL)}건 적용")
    print(f"코퍼스 색인: 문서 {len(doc_of)}종 / 조 unit {len(jo_units):,}개 "
          f"(그중 삭제 {len(deleted)})")

    cands = [json.loads(l) for l in
             Path(cand_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"L3 후보 {len(cands)}건 검증\n")

    passed, rejected = [], []
    verdicts = Counter()
    missing_jo_list: list[dict] = []
    deleted_list: list[dict] = []

    for c in cands:
        own_tier = None
        resolved_refs, bad = [], []
        for r in c.get("refs", []):
            tgt = r.get("target_name", "")
            (loc, sc, matched) = resolve_doc(tgt, doc_of, names)
            if not loc:
                verdicts["missing_doc"] += 1
                bad.append({**r, "verdict": "missing_doc", "score": sc})
                continue
            prefix, did = loc
            jo = int(str(r.get("jo") or 0) or 0)
            br = int(str(r.get("jo_branch") or 0) or 0)
            uid = f"{prefix}:{did}:{code6(jo, br)}"
            if uid not in jo_units:
                verdicts["missing_jo"] += 1
                item = {**r, "verdict": "missing_jo", "unit_id": uid,
                        "matched_doc": matched, "citing_doc": c.get("doc_name"),
                        "citing_jo": c.get("jo")}
                bad.append(item)
                missing_jo_list.append(item)
                continue
            if uid in deleted:
                verdicts["deleted_jo"] += 1
                item = {**r, "verdict": "deleted_jo", "unit_id": uid,
                        "matched_doc": matched, "citing_doc": c.get("doc_name"),
                        "citing_jo": c.get("jo")}
                bad.append(item)
                deleted_list.append(item)
                continue
            verdicts["resolved"] += 1
            resolved_refs.append({**r, "verdict": "resolved", "unit_id": uid,
                                  "matched_doc": matched,
                                  "tier": doc_tier.get(nkey(matched), r.get("target_tier"))})

        ext = {x["tier"] for x in resolved_refs
               if x.get("tier") and not str(x["tier"]).startswith("T4")}
        row = dict(c)
        row["gold_refs"] = resolved_refs
        row["bad_refs"] = bad
        row["resolved_ext_tier_span"] = len(ext)
        row["resolved_tiers"] = sorted(ext)

        if len(ext) >= 2 and not bad:
            row["status"] = "pass"
            passed.append(row)
        elif len(ext) >= 2:
            row["status"] = "pass_partial"      # 일부 참조가 깨졌지만 2위계 유지
            passed.append(row)
        else:
            row["status"] = "reject"
            rejected.append(row)

    def dump(fn, rows):
        with open(fn, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {fn} ({len(rows)}건)")

    full = [r for r in passed if r["status"] == "pass"]
    part = [r for r in passed if r["status"] == "pass_partial"]
    dump("l3_final.jsonl", passed)
    dump("l3_rejected.jsonl", rejected)
    if missing_jo_list:
        dump("gap_missing_provision.jsonl", missing_jo_list)
    if deleted_list:
        dump("gap_deleted_provision.jsonl", deleted_list)

    # ------------------------------------------------ 층화용 통계
    cited_docs = {nkey(str(x.get("target_name", "")))
                  for c in cands for x in c.get("refs", [])}
    strat = defaultdict(list)
    for r in passed:
        key = (r["resolved_ext_tier_span"], r.get("doc_name", ""))
        strat[key].append(r)

    by_doc = Counter(r.get("doc_name", "") for r in passed)
    by_span = Counter(r["resolved_ext_tier_span"] for r in passed)

    L = ["# gold evidence 실물 검증", "",
         f"- 후보 {len(cands)}건 → **통과 {len(passed)}건** "
         f"(완전 {len(full)} / 부분 {len(part)}) / 탈락 {len(rejected)}건", "",
         "## 참조 단위 판정", "", "| 판정 | 건수 | 의미 |", "|---|---|---|",
         f"| resolved | {verdicts['resolved']:,} | 조가 존재하고 유효 |",
         f"| missing_jo | {verdicts['missing_jo']:,} | 문서는 있으나 그 조가 없음 |",
         f"| deleted_jo | {verdicts['deleted_jo']:,} | 조가 삭제 상태 |",
         f"| missing_doc | {verdicts['missing_doc']:,} | 문서를 찾지 못함 |",
         "", "## 통과 후보의 위계 span", "",
         "| 외부위계 수 | 후보 |", "|---|---|"]
    for k in sorted(by_span):
        L.append(f"| {k} | {by_span[k]} |")

    L += ["", "## 통과 후보가 많은 규정 상위 15", "",
          "층화 추출 시 한 규정에 문항이 몰리지 않도록 상한을 둔다.", "",
          "| 규정 | 통과 후보 |", "|---|---|"]
    for nm, n in by_doc.most_common(15):
        L.append(f"| {nm} | {n} |")

    if deleted_list:
        L += ["", f"## 결손 유형 — 삭제된 조 참조 ({len(deleted_list)}건)", "",
              "현행 규정이 인용하는 조가 대상 문서에서 삭제되었다.",
              "인위적 조작 없이 얻은 '근거를 확인할 수 없는 질문'의 원천이다.", "",
              "| 인용한 규정 | 인용 조 | 대상 문서 | 삭제된 조 |", "|---|---|---|---|"]
        for m in deleted_list[:20]:
            L.append(f"| {m.get('citing_doc','')} | 제{m.get('citing_jo','')}조 | "
                     f"{m.get('matched_doc','')} | 제{m.get('jo','')}조 |")

    if missing_jo_list:
        L += ["", f"## 결손 유형 — 존재하지 않는 조 참조 ({len(missing_jo_list)}건)", "",
              "현행 규정이 인용하는 조가 대상 문서에 없다. 조번호 이동이나",
              "개정 누락으로 생긴 실제 결함이며, 인위적 조작 없이 얻은",
              "'근거를 확인할 수 없는 질문'의 원천이다.", "",
              "| 인용한 규정 | 인용 조 | 대상 문서 | 없는 조 |", "|---|---|---|---|"]
        for m in missing_jo_list[:25]:
            L.append(f"| {m.get('citing_doc','')} | 제{m.get('citing_jo','')}조 | "
                     f"{m.get('matched_doc','')} | 제{m.get('jo','')}조 |")

    L += ["", "## 다음", "",
          "1. l3_final.jsonl 이 L3 문항의 최종 후보 풀이다.",
          "2. 규정별 상한(예: 규정당 최대 2문항)을 두고 20문항을 층화 추출한다.",
          "3. gap_missing_provision.jsonl 은 범위밖 20문항 중",
          "   '존재하지 않는 조 참조' 유형의 원천으로 쓴다."]

    Path("gold_verify_report.md").write_text("\n".join(L), encoding="utf-8")
    print("-> gold_verify_report.md")
    print(f"\n통과 {len(passed)} (완전 {len(full)} / 부분 {len(part)}) / 탈락 {len(rejected)}")
    print(f"참조 판정: " + ", ".join(f"{k}={v}" for k, v in verdicts.most_common()))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        main(sys.argv[1], sys.argv[2])
