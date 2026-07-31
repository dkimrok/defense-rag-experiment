#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
미판정(undecided) 항목 자동 축소

11_finalize_scope.py 실행 결과 undecided 215종이 나왔다. 손으로 다 볼 필요는
없다. 대부분은 아래 세 가지로 자동 해소된다.

  A. 노이즈       '같은 법', '이 규정', '동법' 등 지시어가 법령명으로 잡힌 것
  B. 표기 변이    이미 수집된 문서인데 이름이 조금 다른 것
                  (퍼지 매칭 + 토큰 포함 관계로 탐지)
  C. 접미사 상속  이미 판정된 법의 시행령/시행규칙/세칙
                  ('X 시행령'은 'X'의 판정을 물려받는다)

남는 것만 인용 횟수로 나눠 수동 검토 대상을 좁힌다.

  P1  인용 10회 이상   반드시 사람이 결정
  P2  인용 3~9회       결정 권장
  P3  인용 1~2회       기본값 적용 (외부 일반법으로 보고 out_of_scope)
                       단 P3도 목록으로 남겨 검토 가능하게 한다

출력
  triage_worksheet.md   사람이 채울 결정 시트 (P1/P2 목록 + 제안값)
  triage_auto.json      자동 해소된 항목과 근거
  scope_map_v2.json     자동 해소분을 반영한 갱신 판정

사용법
  py 12_triage_undecided.py scope_map.json raw/admrul_list_current.jsonl

되먹임
  이 스크립트는 scope_overrides.json 을 남긴다. 11_finalize_scope.py 는
  다음 실행에서 이 파일을 읽어, 규칙이 undecided 로 남긴 항목에만 적용한다.
  규칙이 항상 우선이므로 규칙을 고치면 오버라이드보다 앞선다.
  따라서 11 -> 12 -> 11 순으로 돌리면 undecided 가 수렴한다.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

# ---------------------------------------------------------------- 유틸

def nkey(s: str) -> str:
    s = re.sub(r'[ㆍ·・]', '', s)
    s = re.sub(r'\s+', '', s)
    return s.replace('(', '').replace(')', '')


# A. 노이즈 패턴 — 법령명이 아닌 지시어/조각
NOISE_EXACT = {"같은법", "이법", "동법", "본법", "해당법률", "이규정", "같은규정",
               "이훈령", "같은훈령", "이지침", "같은영", "같은시행령",
               "이기준", "같은규칙", "이세칙", "해당법령", "관계법령", "법령"}
# 지시어 + 일반명사의 닫힌 조합만 노이즈로 본다.
# 열린 패턴({0,4}자)을 쓰면 '이자제한법' 같은 실명이 오분류된다.
NOISE_PAT = re.compile(
    r'^(같은|이|동|본|해당|위|당해|전기|후기)\s*'
    r'(법률|법|령|영|규정|규칙|훈령|예규|고시|지침|기준|세칙|조항|법령|조|항|호|목)'
    r'(\s*(시행령|시행규칙|시행세칙))?$')

# 법령형 접미사를 갖추면 짧아도 실명으로 본다 (민법·상법·형법 등)
LEGAL_SUFFIX = re.compile(r'(법|법률|령|규칙|규정|훈령|예규|고시|지침|기준|'
                          r'세칙|조건|표준|조약|협정|헌법)$')

# C. 접미사 — 앞부분을 떼면 모법이 된다
SUFFIXES = [" 시행규칙", " 시행령", " 시행세칙", " 시행규정",
            " 施行令", "시행규칙", "시행령", "시행세칙"]


def is_noise(name: str) -> bool:
    k = nkey(name)
    # 1) 명시적 지시어는 접미사가 있어도 노이즈다 ('같은 법', '이 규정')
    if k in NOISE_EXACT:
        return True
    # 2) 조문 조각
    if re.fullmatch(r'[제\d조항호목의\s]+', name.strip()):
        return True
    # 3) 지시어+일반명사 조합 (LEGAL_SUFFIX 예외보다 먼저 판정)
    if NOISE_PAT.match(name.strip()):
        return True
    # 4) 법령형 접미사를 갖추면 실명으로 인정한다
    if LEGAL_SUFFIX.search(k):
        return False
    if len(k) <= 2:
        return True
    return False


def strip_suffix(name: str) -> str | None:
    for s in SUFFIXES:
        if name.endswith(s.strip()) and len(name) > len(s.strip()) + 2:
            return name[: -len(s.strip())].strip()
    return None


def best_match(name: str, pool: list[str]) -> tuple[str, float] | None:
    k = nkey(name)
    best, score = None, 0.0
    for p in pool:
        pk = nkey(p)
        if not pk:
            continue
        if pk == k:
            return p, 1.0
        # 포함 관계는 강한 신호
        if len(k) >= 6 and (k in pk or pk in k):
            r = min(len(k), len(pk)) / max(len(k), len(pk))
            if r > score:
                best, score = p, max(r, 0.9)
            continue
        r = SequenceMatcher(None, k, pk).ratio()
        if r > score:
            best, score = p, r
    return (best, score) if best else None


# ---------------------------------------------------------------- 본체

def main(scope_path: str, list_path: str) -> None:
    scope = json.loads(Path(scope_path).read_text(encoding="utf-8"))
    collected = []
    for l in Path(list_path).read_text(encoding="utf-8").splitlines():
        if l.strip():
            n = str(json.loads(l).get("행정규칙명", "")).strip()
            if n:
                collected.append(n)
    collected += ["방위사업법", "방위사업법 시행령", "방위사업법 시행규칙"]
    print(f"수집 문서 {len(set(collected))}종 / 판정 대상 {len(scope)}종")

    decided = {n: d for n, d in scope.items() if d["scope"] != "undecided"}
    und = [d for d in scope.values() if d["scope"] == "undecided"]
    und.sort(key=lambda x: -x["citations"])
    print(f"미판정 {len(und)}종부터 시작합니다.\n")

    auto: list[dict] = []
    remain: list[dict] = []

    for d in und:
        name = d["name"]

        # A. 노이즈
        if is_noise(name):
            auto.append({**d, "resolved": "noise",
                         "new_scope": "excluded_noise",
                         "evidence": "법령명이 아닌 지시어/조각"})
            continue

        # B. 수집 문서와의 표기 변이
        m = best_match(name, collected)
        if m and m[1] >= 0.90:
            auto.append({**d, "resolved": "name_variant",
                         "new_scope": "in_scope",
                         "evidence": f"수집문서 '{m[0]}' 와 유사도 {m[1]:.2f}"})
            continue

        # C. 접미사 상속
        base = strip_suffix(name)
        if base:
            bd = decided.get(base)
            if not bd:
                for n2, d2 in decided.items():
                    if nkey(n2) == nkey(base):
                        bd = d2
                        break
            if bd:
                auto.append({**d, "resolved": "suffix_inherit",
                             "new_scope": bd["scope"],
                             "evidence": f"모법 '{base}' 판정({bd['scope']}) 상속"})
                continue
            mb = best_match(base, collected)
            if mb and mb[1] >= 0.90:
                auto.append({**d, "resolved": "suffix_variant",
                             "new_scope": "in_scope",
                             "evidence": f"모법이 수집문서 '{mb[0]}' 와 유사 {mb[1]:.2f}"})
                continue

        remain.append({**d,
                       "near_collected": (f"{m[0]} ({m[1]:.2f})" if m and m[1] >= 0.6 else "")})

    p1 = [d for d in remain if d["citations"] >= 10]
    p2 = [d for d in remain if 3 <= d["citations"] < 10]
    p3 = [d for d in remain if d["citations"] < 3]

    # ------------------------------------------------ 출력
    new_scope = dict(scope)
    for a in auto:
        if a["new_scope"] not in ("excluded_noise",):
            new_scope[a["name"]] = {**scope[a["name"]],
                                    "scope": a["new_scope"],
                                    "reason": f"AUTO {a['resolved']}: {a['evidence']}"}
        else:
            new_scope.pop(a["name"], None)
    for d in p3:
        new_scope[d["name"]] = {**scope[d["name"]],
                                "scope": "out_of_scope",
                                "reason": "P3 기본값(인용 2회 이하 외부 일반법)"}

    # 11 이 다음 실행에서 읽어갈 오버라이드. 이것이 되먹임 경로다.
    ov_path = Path("scope_overrides.json")
    ov = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    for a in auto:
        if a["new_scope"] == "excluded_noise":
            ov[a["name"]] = {"scope": "out_of_scope",
                             "reason": f"noise: {a['evidence']}"}
        else:
            ov[a["name"]] = {"scope": a["new_scope"],
                             "reason": f"{a['resolved']}: {a['evidence']}"}
    for d in p3:
        ov.setdefault(d["name"], {"scope": "out_of_scope",
                                  "reason": "P3 기본값(인용 2회 이하 외부 일반법)"})
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> scope_overrides.json ({len(ov)}건) — 11 재실행 시 자동 반영")

    Path("triage_auto.json").write_text(
        json.dumps(auto, ensure_ascii=False, indent=1), encoding="utf-8")
    Path("scope_map_v2.json").write_text(
        json.dumps(new_scope, ensure_ascii=False, indent=1), encoding="utf-8")

    rc = Counter(a["resolved"] for a in auto)
    L = ["# 미판정 항목 분류 시트", "",
         f"- 미판정 {len(und)}종 → 자동해소 {len(auto)}종 / 잔여 {len(remain)}종", "",
         "## 자동 해소 내역", "", "| 유형 | 종수 | 설명 |", "|---|---|---|",
         f"| noise | {rc.get('noise',0)} | 지시어·조각이 법령명으로 추출된 것 (제거) |",
         f"| name_variant | {rc.get('name_variant',0)} | 이미 수집된 문서의 표기 변이 (in_scope) |",
         f"| suffix_inherit | {rc.get('suffix_inherit',0)} | 모법 판정을 상속한 시행령·시행규칙 |",
         f"| suffix_variant | {rc.get('suffix_variant',0)} | 모법이 수집문서인 하위법령 |",
         "",
         "## P1 — 반드시 결정 (인용 10회 이상)", "",
         "| 법령·규정 | 인용 | 위계 | 유사 수집문서 | 결정(IN/OUT) | 근거 |",
         "|---|---|---|---|---|---|"]
    for d in p1:
        L.append(f"| {d['name']} | {d['citations']} | {d['tier']} | "
                 f"{d['near_collected']} |  |  |")

    L += ["", "## P2 — 결정 권장 (인용 3~9회)", "",
          "| 법령·규정 | 인용 | 위계 | 유사 수집문서 | 결정(IN/OUT) |",
          "|---|---|---|---|---|"]
    for d in p2:
        L.append(f"| {d['name']} | {d['citations']} | {d['tier']} | "
                 f"{d['near_collected']} |  |")

    L += ["", f"## P3 — 기본값 out_of_scope 적용 ({len(p3)}종, 인용 2회 이하)", "",
          "인용이 희소한 외부 법령이다. 범위밖 문항 원천으로만 쓰고 코퍼스에 넣지 않는다.",
          "아래 목록에서 포함해야 할 것이 보이면 P1/P2 로 올려 결정한다.", ""]
    for d in p3[:80]:
        L.append(f"- {d['name']} ({d['citations']}회, {d['tier']})")
    if len(p3) > 80:
        L.append(f"- … 외 {len(p3)-80}종 (scope_map_v2.json 참조)")

    L += ["", "## 반영 절차", "",
          "1. P1·P2 표의 '결정' 칸을 IN 또는 OUT 으로 채운다.",
          "2. IN 은 11_finalize_scope.py 의 IN_LAW_FAMILIES 에,",
          "   OUT 은 OUT_FAMILIES 에 추가한다.",
          "3. 규칙 추가 후 IN/OUT 부분문자열 충돌 검사를 다시 수행한다.",
          "4. 11_finalize_scope.py 를 재실행하여 undecided 가 0인지 확인한다."]

    Path("triage_worksheet.md").write_text("\n".join(L), encoding="utf-8")
    print(f"자동해소 {len(auto)}종 (noise {rc.get('noise',0)}, "
          f"표기변이 {rc.get('name_variant',0)}, "
          f"접미사 {rc.get('suffix_inherit',0)+rc.get('suffix_variant',0)})")
    print(f"수동 결정 대상: P1 {len(p1)}종 / P2 {len(p2)}종 / P3 {len(p3)}종(기본값)")
    print("-> triage_worksheet.md, triage_auto.json, scope_map_v2.json")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        main(sys.argv[1], sys.argv[2])
