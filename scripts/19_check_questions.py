#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
문항 자동 점검기

작성한 슬롯을 읽어 설계서 4절 작성 규칙을 기계적으로 검사한다.
사람이 판단할 수 없는 것(정답의 타당성, 수준 분류)은 검사하지 않는다.
여기서 걸러지는 것은 형식 결함뿐이며, 통과했다고 좋은 문항인 것은 아니다.

검사 항목
  R1  어휘 누출   질문과 gold 조문 사이 최장 연속 일치 어절 수. 5 이상이면 반려.
                  BM25 가 부당하게 유리해져 검색 난이도가 왜곡된다.
                  단, 「」 안의 문서명은 계산에서 뺀다. 그것은 표현 베끼기가
                  아니라 질문이 가리키는 대상이며, 범위밖 문항은 인용 대상을
                  반드시 밝혀야 하기 때문이다.
  R2  단답 길이   15자 초과 경고, 40자 초과 반려(스키마 상한).
                  범위밖 문항은 '근거 없음' 정형구라 제외한다.
      서술 문장수 2~3문장 권장.
  R3  고유명사    「」 인용 법령명과 4자리 연도의 개수를 센다.
  R5  기준일 누출 질문문에 날짜·연도가 있으면 반려.
  R6  위치 참조   질문문에 조·항·호 번호가 있으면 반려(답가능 문항 한정).
                  24/25 의 tokenize_ko 가 조 번호를 통째 토큰으로 뽑아
                  BM25 검색이 어휘일치로 풀린다. 또 커버리지를 낮춰 gold 조를
                  지웠을 때 '그 조가 없다'는 것만으로 기권할 수 있게 되어,
                  '모른다는 것을 모른다'는 측정 대상이 오염된다.
                  OOS 는 인용 대상(코퍼스 밖)을 지목해야 하므로 예외.
  OOS 대상 명시   범위밖 문항의 질문에 인용 대상 문서명이 있는지 본다.
                  없으면 코퍼스 안 조문만으로 답이 되어버릴 수 있다.
  L4  3요소       서술에 적용여부·근거조문·시점 표현이 있는지 본다.
  OOS 정답 형식   범위밖 문항의 서술에 '확인할 수 없다' 취지가 있는지 본다.
  공통 빈칸       질문·단답·서술이 비어 있지 않은지.

사용법
    py 19_check_questions.py corpus_final.jsonl pilot_slots.jsonl
        -> check_report.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LEAK_LIMIT = 5          # 연속 일치 어절 5 이상이면 반려
SHORT_WARN, SHORT_FAIL = 15, 40

RE_DATE = re.compile(r'(19|20)\d{2}\s*년|(19|20)\d{2}[.\-/]\d{1,2}|'
                     r'\d{1,2}\s*월\s*\d{1,2}\s*일')
RE_YEAR = re.compile(r'(19|20)\d{2}')
RE_QUOTED = re.compile(r'[「『][^」』]{2,60}[」』]')
RE_JO = re.compile(r'제\s*\d{1,3}\s*조')
# R6 위치 참조 탐지용. '별지 제3호 서식'은 내용 식별자라 위치 포인터가 아니므로 제외.
RE_JO_REF = re.compile(r'제\s*\d{1,3}\s*조(?:\s*의\s*\d+)?')
RE_HANG_REF = re.compile(r'제\s*\d{1,2}\s*항|[\u2460-\u2473]')
RE_HO_REF = re.compile(r'제\s*\d{1,3}\s*호')
RE_BYEOLJI = re.compile(r'별지\s*제?\s*\d+\s*호(?:\s*서식)?')
RE_CITED = re.compile(r'[「『]([^」』]{2,60})[」』]')
RE_SENT = re.compile(r'[.!?。]\s*')


def toks(s: str) -> list[str]:
    """어절 단위. 조사·문장부호 차이는 무시하지 않는다(보수적으로 본다)."""
    return [t for t in re.split(r'\s+', re.sub(r'[^\w가-힣]', ' ', s)) if t]


def longest_common_run(a: list[str], b: list[str]) -> tuple[int, str]:
    """두 어절열의 최장 연속 공통 부분열 길이와 그 내용."""
    if not a or not b:
        return 0, ""
    best, best_txt = 0, ""
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
                    best_txt = " ".join(a[i - best:i])
        prev = cur
    return best, best_txt


def check(s: dict, corpus: dict) -> dict:
    q = (s.get("question_ko") or "").strip()
    a_s = (s.get("answer_short") or "").strip()
    a_l = (s.get("answer_long") or "").strip()
    lvl = s.get("level")
    fails, warns = [], []

    if not q:
        fails.append("질문 미작성")
    if not a_s:
        fails.append("단답 미작성")
    if not a_l:
        fails.append("서술 미작성")
    if fails:
        return dict(qid=s["qid"], level=lvl, status="미작성",
                    fails=fails, warns=warns, leak=0, leak_txt="")

    # R1 어휘 누출
    # 「」 안의 문서명은 '표현 베끼기'가 아니라 질문이 가리키는 대상이다.
    # 특히 범위밖 문항은 인용 대상 문서명을 반드시 밝혀야 하므로
    # (안 밝히면 코퍼스 안에서 답이 되어버린다) 이름 길이 때문에 반려되면
    # 규칙 목적과 어긋난다. 겹침 계산 전에 「」 구간을 뺀다.
    q_for_leak = RE_QUOTED.sub(' ', q)
    quoted_names = [x.strip('「」『』') for x in RE_QUOTED.findall(q)]
    qt = toks(q_for_leak)
    leak, leak_txt = 0, ""
    for g in s.get("gold_evidence", []):
        u = corpus.get(g["unit_id"], {})
        text = u.get("text") or g.get("text_span") or ""
        n, t = longest_common_run(qt, toks(text))
        if n > leak:
            leak, leak_txt = n, t
    if leak >= LEAK_LIMIT:
        fails.append(f"R1 어휘누출 {leak}어절: '{leak_txt}'")
    elif leak == LEAK_LIMIT - 1:
        warns.append(f"R1 경계 {leak}어절")

    # R2 길이 — 범위밖 문항의 단답은 '근거 없음' 정형구라 15자를 넘는다.
    # 사실형 단답에만 적용한다.
    if s.get("answerable", True):
        if len(a_s) > SHORT_FAIL:
            fails.append(f"R2 단답 {len(a_s)}자 (상한 {SHORT_FAIL})")
        elif len(a_s) > SHORT_WARN:
            warns.append(f"R2 단답 {len(a_s)}자 (권장 {SHORT_WARN} 이내)")
    ns = len([x for x in RE_SENT.split(a_l) if x.strip()])
    if ns > 4:
        warns.append(f"R2 서술 {ns}문장 (권장 2~3)")

    # R3 고유명사·연도
    pn = len(RE_QUOTED.findall(q))
    yr = len(RE_YEAR.findall(q))
    if pn + yr >= 3:
        warns.append(f"R3 고유명사 {pn} 연도 {yr}")

    # R5 기준일 누출
    if RE_DATE.search(q):
        fails.append("R5 질문문에 날짜 표기")

    # R6 위치 참조 — 답 가능 문항에서만 반려한다.
    answerable = s.get("answerable", True)
    q_nb = RE_BYEOLJI.sub(" ", q)
    refs = []
    if RE_JO_REF.search(q_nb):
        refs.append("조:" + ",".join(RE_JO_REF.findall(q_nb)))
    if RE_HANG_REF.search(q_nb):
        refs.append("항:" + ",".join(RE_HANG_REF.findall(q_nb)))
    if RE_HO_REF.search(q_nb):
        refs.append("호:" + ",".join(RE_HO_REF.findall(q_nb)))
    if refs and answerable:
        fails.append("R6 질문문에 위치 참조 " + " ".join(refs))

    # OOS 인용 대상이 질문에 지목돼 있는지
    if not answerable:
        tgt = ""
        for src in (s.get("level_justification"), s.get("out_of_scope_reason"),
                    s.get("source", {}).get("note") if isinstance(
                        s.get("source"), dict) else ""):
            m = RE_CITED.findall(src or "")
            if m:
                tgt = m[-1]
                break
        if tgt:
            key = re.sub(r'\s+', '', tgt)
            if key not in re.sub(r'\s+', '', q):
                warns.append(f"OOS 인용대상 「{tgt}」 이 질문에 없음 "
                             f"— 코퍼스 안에서 답이 되어버릴 수 있음")

    # 수준별
    if lvl == 4:
        has_apply = any(k in a_l for k in (
            "적용", "해당", "포함", "대상", "제외"))
        has_basis = bool(RE_JO.search(a_l)) or "부칙" in a_l or "별표" in a_l
        # 시점: 명시 어휘 + 시간 관계 표현 + 개정/버전 관련 어휘를 폭넓게 본다
        has_time = any(k in a_l for k in (
            "현행", "개정", "시행", "종전", "이전", "이후", "당시", "기존",
            "소급", "착수", "체결", "발령", "종래", "구법", "신법", "경과",
            "부터", "까지", "전에", "후에", "당초", "최초", "이미")) \
            or bool(re.search(r'20\d{2}|\d+년|\d+월', a_l))
        miss = [n for n, ok in (("적용여부", has_apply), ("근거조문", has_basis),
                                ("시점", has_time)) if not ok]
        if miss:
            # 3요소는 강제 반려가 아니라 주의로 낮춘다. 서술 방식이 다양해
            # 자동 판정이 오탐하기 쉽다. 사람이 최종 확인하도록 남긴다.
            warns.append("L4 3요소 점검(자동): " + ", ".join(miss)
                         + " — 서술에 실제로 있는지 확인")
    if lvl == 0:
        oos_ok = any(k in a_l for k in (
            "확인할 수 없", "확인이 어렵", "확인 불가", "알 수 없", "판단할 수 없",
            "근거가 없", "근거를 찾을 수 없", "규정되어 있지 않", "포함되어 있지 않",
            "포함되지 않", "다루지 않", "범위 밖", "범위를 벗어", "대상이 아니",
            "소관", "적용되지 않", "해당하지 않", "폐지", "미공개", "다른 법령",
            "타 법령", "일반법", "국가계약법", "이 규정집", "이 코퍼스",
            "명시되어 있지 않"))
        if not oos_ok:
            warns.append("OOS 정답 점검(자동): '확인 불가' 취지가 안 잡힘 "
                         "— 서술을 사람이 확인")

    if quoted_names:
        warns.append("인용 문서명: " + ", ".join(quoted_names[:3])
                     + " (R1 계산에서 제외됨)")
    return dict(qid=s["qid"], level=lvl,
                status="반려" if fails else ("주의" if warns else "통과"),
                fails=fails, warns=warns, leak=leak, leak_txt=leak_txt,
                q_len=len(q), a_short=len(a_s), a_sent=ns)


def main(corpus_path: str, slots_path: str,
         out_path: str = "check_report.md") -> None:
    corpus = {}
    for l in Path(corpus_path).read_text(encoding="utf-8").splitlines():
        if l.strip():
            u = json.loads(l)
            corpus[u["unit_id"]] = u
    slots = [json.loads(l) for l in
             Path(slots_path).read_text(encoding="utf-8").splitlines() if l.strip()]

    res = [check(s, corpus) for s in slots]
    n = {k: sum(1 for r in res if r["status"] == k)
         for k in ("통과", "주의", "반려", "미작성")}

    L = ["# 문항 점검 결과", "",
         f"- 대상 {len(res)}개 / " + " · ".join(f"{k} {v}" for k, v in n.items()), "",
         "자동 점검은 형식 결함만 잡는다. 정답의 타당성과 수준 분류는",
         "사람이 따로 확인해야 한다.", "",
         "| qid | 수준 | 판정 | 최장일치 | 단답 | 문제 |",
         "|---|---|---|---|---|---|"]
    for r in res:
        issues = "; ".join(r["fails"] + [f"({w})" for w in r["warns"]]) or "-"
        L.append(f"| {r['qid']} | L{r['level']} | {r['status']} | "
                 f"{r.get('leak', 0)}어절 | {r.get('a_short', 0)}자 | {issues} |")

    bad = [r for r in res if r["status"] == "반려"]
    if bad:
        L += ["", "## 반려 상세", ""]
        for r in bad:
            L.append(f"### {r['qid']}")
            for f in r["fails"]:
                L.append(f"- {f}")
            if r.get("leak_txt"):
                L.append(f"- 겹친 부분: `{r['leak_txt']}`")
            L.append("")

    L += ["", "## 다음", "",
          "1. 반려 문항을 고쳐 워크시트에 반영하고 32 로 되돌린 뒤 다시 점검한다.",
          "2. 35_scan_refs.py 로 문서명 참조·모호 위험을 함께 본다.",
          "   (19 는 통과/반려만 가른다. 35 는 고칠 방향을 알려준다)",
          "3. 전부 통과하면 B 인덱스 재빌드 → C 변형 재생성으로 넘어간다."]

    Path(out_path).write_text("\n".join(L), encoding="utf-8")
    print(" · ".join(f"{k} {v}" for k, v in n.items()))
    print(f"-> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        a = sys.argv
        out = a[a.index("--out") + 1] if "--out" in a else "check_report.md"
        main(a[1], a[2], out)
