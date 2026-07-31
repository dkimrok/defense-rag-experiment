#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코퍼스 경계 확정 — scope decision

09_extract_refs.py 의 scope_of() 는 이름 패턴만 보았기 때문에
이미 수집된 문서(군수품조달관리규정 58회, 방위사업관리규정 47회)가
'미판정'으로 올라오는 결함이 있었다. 이 스크립트가 그것을 바로잡는다.

하는 일
  1. 명칭 정규화     혁신법 == 국방과학기술혁신 촉진법
                     국가계약법 == 국가를 당사자로 하는 계약에 관한 법률
                     띄어쓰기·중점(ㆍ·) 변이 통일
  2. 수집목록 대조   raw/admrul_list_current.jsonl 및 법령 수집분과 조인
  3. 규칙 기반 판정
        IN-1  방위사업청 소관 행정규칙 (이미 수집됨)
        IN-2  위 규칙들이 위임근거 또는 직접 적용근거로 인용하는
              방위사업·국방R&D·군수 고유 법령 계통 및 하위 부령
        IN-3  국방부 소관이면서 획득 절차를 직접 규율하는 훈령
        OUT   방위사업 여부와 무관하게 모든 정부기관에 동일하게 적용되는
              일반 규범 (계약·공직윤리·인사·재난·중소기업·하도급 등)
  4. L3 후보 재검증  참조 대상이 모두 in_scope 인 조만 L3 로 인정한다.
                     out_of_scope 를 참조하는 조는 범위밖 문항 원천으로 돌린다.

출력
  scope_decision.md      검토용 표 (사람이 최종 승인)
  scope_map.json         기계 판독용 판정 결과 (이후 스크립트가 참조)
  to_collect.json        추가 수집이 필요한 법령 목록
  l3_revalidated.jsonl   gold evidence가 코퍼스 안에 있는 L3 후보만
  oos_sources.jsonl      범위밖 20문항 원천 후보

사용법
  py 11_finalize_scope.py refs.jsonl raw/admrul_list_current.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------- 정규화

def nkey(s: str) -> str:
    """비교용 키. 공백·중점·괄호 변이를 제거한다."""
    s = re.sub(r'[ㆍ·・]', '', s)
    s = re.sub(r'\s+', '', s)
    s = s.replace('(', '').replace(')', '')
    return s


# 약어 -> 정식명칭. 실제 인용 데이터에서 확인된 것만 넣는다.
CANONICAL_RAW = {
    "혁신법": "국방과학기술혁신 촉진법",
    "혁신법 시행령": "국방과학기술혁신 촉진법 시행령",
    "혁신법 시행규칙": "국방과학기술혁신 촉진법 시행규칙",
    "국가계약법": "국가를 당사자로 하는 계약에 관한 법률",
    "국가계약법 시행령": "국가를 당사자로 하는 계약에 관한 법률 시행령",
    "국가계약법 시행규칙": "국가를 당사자로 하는 계약에 관한 법률 시행규칙",
    "방위산업발전 및 지원에 관한 법률": "방위산업 발전 및 지원에 관한 법률",
    "방위산업에 관한 계약사무처리 규칙": "방위산업에 관한 계약사무 처리규칙",
    "방위산업에 관한 착수금 및 중도금 지급규칙":
        "방위산업에 관한 착수금 및 중도금 지급규칙",
    # 원문에서 줄여 인용한 것을 정식명칭으로 복원 (2026-07-21 확인)
    "수출지원사업 운영 규정": "방산 중소기업 수출지원사업 운영 규정",
    "수출지원사업 운영규정": "방산 중소기업 수출지원사업 운영 규정",
    # 아래는 사용자 지시에 따른 갈음. 인용문맥 검증 후 확정할 것.
    "위원회 운영 규정": "방위사업기획ㆍ관리 실무위원회 운영규정",
    "위원회 운영규정": "방위사업기획ㆍ관리 실무위원회 운영규정",
    # 약칭·오기 병합 (P3 검토에서 발견, 2026-07-21)
    "부패방지권익위법": "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률",
    "부패방지권익위법 시행령":
        "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률 시행령",
    "부패방지 및 국민권익위원회 설치와 운영에 관한 법률":
        "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률",
    "국방과학기술 혁신법": "국방과학기술혁신 촉진법",       # 오기
    "방산물자의 원가계산에 관한 시행세칙":
        "방산원가대상물자의 원가계산에 관한 시행세칙",        # 축약
    "공감법": "공공감사에 관한 법률",
    "총수명주기관리업무훈령(국방부 훈령)": "총수명주기관리업무 훈령",  # 괄호 표기 중복
    "국방보안업무훈령": "국방 보안업무훈령",                            # 정식명은 띄어쓰기 있음
}
CANONICAL = {nkey(k): v for k, v in CANONICAL_RAW.items()}


def canon_alias(name: str) -> str:
    """약어 사전만 적용한 1차 정규화."""
    return CANONICAL.get(nkey(name), re.sub(r'\s+', ' ', name).strip())


# 2차 정규화: 표기 변이 병합용 대표형 색인.
# '전략물자 수출입고시' / '전략물자수출입고시' / '전략물자 수출입 고시' 는
# nkey 가 같으므로 같은 문서다. build_rep_index() 로 대표형을 정한다.
_REP: dict[str, str] = {}


def build_rep_index(name_counts: "Counter") -> None:
    groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for n, c in name_counts.items():
        a = canon_alias(n)
        groups[nkey(a)].append((a, c))
    for k, lst in groups.items():
        # 인용이 가장 많은 표기를 대표형으로, 동률이면 띄어쓰기가 있는 쪽
        _REP[k] = sorted(lst, key=lambda x: (-x[1], -x[0].count(' ')))[0][0]


def canon(name: str) -> str:
    a = canon_alias(name)
    return _REP.get(nkey(a), a)


# ---------------------------------------------------------------- 판정 규칙

# IN-2: 위임근거 법령 계통. 어간으로 매칭한다(법/시행령/시행규칙 모두 포함).
IN_LAW_FAMILIES = [
    "방위사업법",
    "국방과학기술혁신 촉진법",
    "방위산업 발전 및 지원에 관한 법률",
    "방위산업기술보호법",
    "방위산업기술 보호법",
    "군용항공기 비행안전성 인증에 관한 법률",
    "민ㆍ군기술협력사업 촉진법",
    "민군기술협력사업 촉진법",
    # 도메인 판단으로 포함 결정 (2026-07-21)
    #  국가연구개발혁신법: 방위사업관리규정 제6조의2가 보안과제 분류 근거로
    #    직접 인용한다. 방위력개선사업 연구개발의 실체적 요건을 규율한다.
    #  군수품관리법: 군수품조달관리규정 계통의 근거법.
    "국가연구개발혁신법",
    "군수품관리법",
    # P2 검토 결과 포함 결정 (2026-07-21)
    "방위사업감독관 직무 등에 관한 규칙",   # 방위사업 전용 부령
    "국방과학연구소법",                      # 방위력개선 R&D 수행주체
    "전략물자 수출입고시",                   # 방산물자 수출허가 직접근거
    "대외무역법",                            # 전략물자 수출통제 근거법
    # 방위사업 전용 부령
    "방산원가대상물자의 원가계산에 관한 규칙",
    "방위산업에 관한 착수금 및 중도금 지급규칙",
    "방위산업에 관한 계약사무 처리규칙",
]

# IN-3: 국방부 소관 획득 절차 훈령
IN_MND_RULES = [
    "국방전력발전업무훈령",
    "총수명주기관리업무훈령",        # 획득 절차를 직접 규율
    "군수품 관리훈령",                # 군수품관리법 포함과 일관 (P3에서 승격)
    # 국방 보안업무훈령 / 방위산업보안업무훈령 / 국방사업 총사업비 관리지침 은
    # 경계 안으로 판단했으나 확보 불가로 UNOBTAINABLE 로 이관했다 (2026-07-21).
]

# OUT: 범부처 일반법
OUT_FAMILIES = [
    "국가를 당사자로 하는 계약에 관한 법률",
    "지방자치단체를 당사자로 하는 계약에 관한 법률",
    "국가공무원법", "공무원임용령", "공무원 징계령",
    "공직자의 이해충돌 방지법", "공직자윤리법",
    "부정청탁 및 금품등 수수의 금지에 관한 법률",
    "공익신고자 보호법",
    "공공재정 부정청구 금지 및 부정이익 환수 등에 관한 법률",
    "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률",
    "재난 및 안전관리 기본법",
    "중소기업기본법", "중소기업제품 구매촉진 및 판로지원에 관한 법률",
    "하도급거래 공정화에 관한 법률", "하도급법",
    "전자정부법", "개인정보 보호법", "정보공개법",
    "행정절차법", "행정기본법",
    "경제안보를 위한 공급망 안정화 지원 기본법",
    "물품관리법", "국유재산법",
    # P2 검토 결과 제외 결정 (2026-07-21) — 전 행정 공통 규범
    "보조금 관리에 관한 법률", "본인서명사실 확인 등에 관한 법률",
    "공공기관의 정보공개에 관한 법률", "공공감사에 관한 법률", "공감법",
    "중견기업 성장촉진 및 경쟁력 강화에 관한 특별법",
    "전자문서 및 전자거래 기본법", "전자거래기본법", "전자서명법",
    "근로기준법", "청원법", "고등교육법", "양성평등기본법",
    "자본시장과 금융투자업에 관한 법률", "신용정보의 이용 및 보호에 관한 법률",
    "국고금관리법", "국고금 관리법", "국가재정법", "국가채권관리법",
    "국가회계법", "법인세법", "관세법", "통계법", "민법",
    "소프트웨어 진흥법", "과학기술기본법",
    "국가를 당사자로 하는 소송에 관한 법률",
    "공공기록물 관리에 관한 법률", "민원 처리에 관한 법률",
    "국가공무원 복무규정", "공무원수당 등에 관한 규정", "공무원보수규정",
    "공무원 제안 규정", "공무원 인사 운영에 관한 특례규정",
    "적극행정 운영규정", "군인사법", "군인 등의 특수근무수당에 관한 규칙",
    "항공안전법", "성폭력범죄의 처벌 등에 관한 특례법",
    "정부 입찰ㆍ계약 집행기준", "정부입찰ㆍ계약 집행기준",
    "물품구매(제조) 계약일반조건",
    "국가종합전자조달시스템 보증서 수납에 관한 협약",
    "조달사업에 관한 법률", "정부조직법", "행정소송법", "형사소송법",
    "정부업무평가기본법", "정부업무평가 기본법",
    # P2 검토 결과 제외 (2026-07-21)
    "중소기업 기술혁신 촉진법", "산업기술혁신촉진법", "산업기술혁신 촉진법",
    "대ㆍ중소기업 상생협력 촉진에 관한 법률",
    "성폭력방지 및 피해자보호 등에 관한 법률",
    "공무원인재개발법",
    # P3 중 계약예규·타부처 항목
    "예정가격작성기준", "조달청 군 급식품목 가격협의위원회 운영규정",
]


# 현행 규정이 인용하지만 이미 폐지되어 후속 규정이 없는 것.
# 코퍼스에는 넣지 않되, 범위밖 문항 중 'dangling reference' 유형의
# 원천으로 별도 표시한다. 인위적 조작이 아닌 실제 지식베이스 결함이다.
ABOLISHED = [
    "방위산업육성 지원사업 공통 운영규정",   # 폐지, 후속 규정 없음 (2026-07-21 확인)
]

# 경계 안으로 판정했으나 실제로 확보할 수 없는 문서.
# 보안 사유 미공개로 추정되며, 국가법령정보센터 검색에서 임계 이상 후보가 없었다.
# 폐쇄망 배치의 구조적 제약(상위 보안등급 문서는 코퍼스에 넣을 수 없음)을
# 그대로 재현하므로, 범위밖 문항 중 별도 유형의 원천이 된다.
UNOBTAINABLE = [
    "국방 보안업무훈령",
    "방위산업보안업무훈령",
    "국방사업 총사업비 관리지침",
]


def famhit(name: str, fams: list[str]) -> str | None:
    k = nkey(name)
    for f in fams:
        if nkey(f) and nkey(f) in k:
            return f
    return None


# 12_triage_undecided.py 가 남긴 확정분. 규칙이 undecided 로 남긴 항목에만 적용한다.
# 규칙이 우선이므로, 규칙을 고치면 오버라이드보다 앞선다.
OVERRIDE_PATH = "scope_overrides.json"
_OVERRIDE: dict[str, dict] = {}


def load_overrides() -> int:
    global _OVERRIDE
    p = Path(OVERRIDE_PATH)
    if not p.exists():
        return 0
    raw = json.loads(p.read_text(encoding="utf-8"))
    _OVERRIDE = {nkey(k): v for k, v in raw.items()}
    return len(_OVERRIDE)


def classify(name: str, collected: set[str]) -> tuple[str, str]:
    """returns (scope, reason)"""
    c = canon(name)
    f = famhit(c, ABOLISHED)
    if f:
        return "abolished_cited", f"폐지·후속없음({f}) — dangling reference 문항 원천"
    f = famhit(c, UNOBTAINABLE)
    if f:
        return "unobtainable_cited", f"수집불가({f}) — 미공개 추정, 접근불가 문항 원천"
    if nkey(c) in collected:
        return "in_scope", "IN-1 방위사업청 소관 행정규칙(수집완료)"
    f = famhit(c, IN_MND_RULES)
    if f:
        return "in_scope_to_collect", f"IN-3 국방부 획득절차 훈령({f})"
    f = famhit(c, OUT_FAMILIES)
    if f:
        return "out_of_scope", f"OUT 범부처 일반법({f})"
    f = famhit(c, IN_LAW_FAMILIES)
    if f:
        return "in_scope_to_collect", f"IN-2 방위사업·국방R&D·군수 법령계통({f})"
    ov = _OVERRIDE.get(nkey(c)) or _OVERRIDE.get(nkey(name))
    if ov:
        return ov.get("scope", "undecided"), "OVERRIDE " + ov.get("reason", "")
    return "undecided", "규칙 미해당 — 수동 결정 필요"


# ---------------------------------------------------------------- 본체

def main(refs_path: str, list_path: str) -> None:
    refs = [json.loads(l) for l in
            Path(refs_path).read_text(encoding="utf-8").splitlines() if l.strip()]

    collected_names = []
    for l in Path(list_path).read_text(encoding="utf-8").splitlines():
        if l.strip():
            collected_names.append(str(json.loads(l).get("행정규칙명", "")).strip())
    # 수집된 법령(T1~T3)도 코퍼스 안이다
    collected_names += ["방위사업법", "방위사업법 시행령", "방위사업법 시행규칙"]
    collected = {nkey(n) for n in collected_names if n}
    n_ov = load_overrides()
    print(f"수집 문서 {len(collected)}종과 대조합니다."
          + (f" 오버라이드 {n_ov}건 적용." if n_ov else " (오버라이드 없음)"))

    # 1차 집계 -> 표기 변이 병합용 대표형 색인 구축
    raw_counts = Counter()
    for row in refs:
        for r in row["refs"]:
            raw_counts[r["target_name"]] += 1
    build_rep_index(raw_counts)
    merged = len(raw_counts) - len(_REP)
    print(f"표기 변이 병합: {len(raw_counts)}종 -> {len(_REP)}종 ({merged}종 병합)")

    # 2차 집계 (병합 후)
    cite = Counter()
    tier_of_name: dict[str, str] = {}
    for row in refs:
        for r in row["refs"]:
            c = canon(r["target_name"])
            cite[c] += 1
            if r["target_tier"] != "UNK":
                tier_of_name.setdefault(c, r["target_tier"])
            else:
                tier_of_name.setdefault(c, "UNK")

    decisions = {}
    for name, n in cite.items():
        scope, reason = classify(name, collected)
        decisions[name] = dict(name=name, citations=n,
                               tier=tier_of_name.get(name, "UNK"),
                               scope=scope, reason=reason)

    by = Counter(d["scope"] for d in decisions.values())
    cit_by = Counter()
    for d in decisions.values():
        cit_by[d["scope"]] += d["citations"]

    # ------------------------------------------------ L3 재검증
    in_ok = {n for n, d in decisions.items()
             if d["scope"].startswith("in_scope")}
    gap_kinds = {n: d["scope"] for n, d in decisions.items()
                 if d["scope"] in ("abolished_cited", "unobtainable_cited")}
    l3_ok, oos_src, l3_mixed = [], [], []
    for row in refs:
        tgt = {canon(r["target_name"]) for r in row["refs"]}
        ext = {r["target_tier"] for r in row["refs"]
               if r["target_tier"] not in ("T4_행정규칙", "UNK")
               and canon(r["target_name"]) in in_ok}
        out_hit = [t for t in tgt if decisions.get(t, {}).get("scope") == "out_of_scope"]
        row2 = dict(row)
        row2["in_scope_targets"] = sorted(tgt & in_ok)
        row2["out_scope_targets"] = sorted(out_hit)
        row2["gap_targets"] = {t: gap_kinds[t] for t in tgt if t in gap_kinds}
        row2["valid_ext_tier_span"] = len(ext)
        if len(ext) >= 2:
            (l3_mixed if out_hit else l3_ok).append(row2)
        # out_of_scope 참조가 없어도 폐지·비공개 문서를 참조하면 범위밖 원천이다.
        # 이 조건을 빼면 abolished_cited / unobtainable_cited 유형 문항의
        # 원천이 파일에 남지 않는다.
        if (out_hit or row2["gap_targets"]) and len(ext) < 2:
            oos_src.append(row2)

    def dump(fn, rows):
        with open(fn, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {fn} ({len(rows)}건)")

    dump("l3_revalidated.jsonl", l3_ok)
    dump("oos_sources.jsonl", oos_src)

    to_collect = sorted(
        [d for d in decisions.values() if d["scope"] == "in_scope_to_collect"],
        key=lambda x: -x["citations"])
    Path("to_collect.json").write_text(
        json.dumps(to_collect, ensure_ascii=False, indent=1), encoding="utf-8")
    Path("scope_map.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> to_collect.json ({len(to_collect)}건)")
    print("-> scope_map.json")

    # ------------------------------------------------ 리포트
    L = ["# 코퍼스 경계 확정", "",
         f"- 인용된 법령·규정 {len(decisions)}종 (명칭 정규화 후)", "",
         "| 판정 | 종수 | 인용횟수 |", "|---|---|---|"]
    for k in ("in_scope", "in_scope_to_collect", "out_of_scope",
              "abolished_cited", "unobtainable_cited", "undecided"):
        L.append(f"| {k} | {by.get(k,0)} | {cit_by.get(k,0):,} |")

    L += ["", "## 추가 수집 대상 (in_scope_to_collect)", "",
          "| 법령·규정 | 인용 | 위계 | 근거 |", "|---|---|---|---|"]
    for d in to_collect:
        L.append(f"| {d['name']} | {d['citations']} | {d['tier']} | {d['reason']} |")

    L += ["", "## 의도적 제외 (out_of_scope) — 범위밖 문항 원천", "",
          "| 법령 | 인용 | 근거 |", "|---|---|---|"]
    for d in sorted([x for x in decisions.values() if x["scope"] == "out_of_scope"],
                    key=lambda x: -x["citations"])[:25]:
        L.append(f"| {d['name']} | {d['citations']} | {d['reason']} |")

    ab = [x for x in decisions.values() if x["scope"] == "abolished_cited"]
    if ab:
        L += ["", "## 폐지·후속없음 (dangling reference 원천)", "",
              "현행 규정이 인용하지만 이미 폐지되어 근거를 확인할 수 없는 규정이다.",
              "코퍼스에 넣지 않는다. 대신 범위밖 문항 중 별도 유형으로 사용한다.",
              "정답은 '인용된 규정이 폐지되어 현행 근거를 확인할 수 없다' 이며,",
              "이를 답하지 못하고 내용을 지어내면 곧 환각이다.", "",
              "| 규정 | 인용 | 인용하는 조 |", "|---|---|---|"]
        for d in sorted(ab, key=lambda x: -x["citations"]):
            L.append(f"| {d['name']} | {d['citations']} | oos_sources.jsonl 참조 |")

    und = sorted([x for x in decisions.values() if x["scope"] == "undecided"],
                 key=lambda x: -x["citations"])
    L += ["", f"## 수동 결정 필요 ({len(und)}종)", "",
          "아래 항목은 규칙으로 갈리지 않는다. 각각 in/out 을 정해 규칙에 반영한다.", "",
          "| 법령·규정 | 인용 | 위계 |", "|---|---|---|"]
    for d in und[:30]:
        L.append(f"| {d['name']} | {d['citations']} | {d['tier']} |")

    L += ["", "## L3 후보 재검증 결과", "",
          f"- 참조 대상이 모두 코퍼스 안 → **L3 확정 후보 {len(l3_ok)}개 조**",
          f"- 범위밖 참조가 섞임 → 보류 {len(l3_mixed)}개 조",
          f"- 범위밖 참조만 있음 → 범위밖 문항 원천 {len(oos_src)}개 조", "",
          "L3 확정 후보에서 20문항을 층화 추출한다.",
          "보류 항목은 범위밖 참조 조문을 gold evidence에서 빼도 답이 성립하면 사용 가능하다.", "",
          "## 승인 절차", "",
          "1. '수동 결정 필요' 항목을 검토하고 IN_LAW_FAMILIES / OUT_FAMILIES 에 반영한다.",
          "2. 스크립트를 다시 돌려 undecided 가 0이 되게 한다.",
          "3. to_collect.json 의 법령을 추가 수집한다.",
          "4. 확정된 scope_map.json 을 이후 모든 문항 작성의 기준으로 삼는다."]

    Path("scope_decision.md").write_text("\n".join(L), encoding="utf-8")
    print("-> scope_decision.md")
    print(f"\n판정: in={by.get('in_scope',0)} "
          f"to_collect={by.get('in_scope_to_collect',0)} "
          f"out={by.get('out_of_scope',0)} undecided={by.get('undecided',0)}")
    print(f"L3 확정 후보 {len(l3_ok)}개 (보류 {len(l3_mixed)})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        main(sys.argv[1], sys.argv[2])
