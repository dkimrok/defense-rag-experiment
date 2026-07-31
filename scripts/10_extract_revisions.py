#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개정 쌍 추출기 — L4(적용판단) 문항 후보 생성

목적
    같은 행정규칙의 인접 버전을 조 단위로 대조하여, 개정으로 인해
    '답이 실제로 달라지는' 조문을 골라낸다. 이것이 L4 문항의 원천이고,
    동시에 어노테이션 스키마의 distractors.stale_versions 를 채운다.

왜 단순 텍스트 diff로는 부족한가
    개정의 다수는 부처명 변경, 띄어쓰기, 문장부호 정리 같은 자구 수정이다.
    이런 쌍으로 문항을 만들면 정답이 바뀌지 않아 L4가 성립하지 않는다.
    그래서 '정답 변경 신호'를 따로 탐지한다.

        수치   기한/금액/비율/인원/횟수가 바뀌면 답이 바뀐다
        주체   ~장/~관/~부서/~위원회가 바뀌면 '누가 하는가'의 답이 바뀐다
        의무성 하여야 한다 <-> 할 수 있다 는 재량 여부의 답을 바꾼다
        참조   제N조 인용이 바뀌면 절차 연결이 바뀐다
        신설/삭제

    이 중 하나 이상이 걸린 쌍만 L4 후보로 승격한다.

부칙 적용례 연결
    설계서에서 L4는 '부칙·적용례·경과규정 또는 개정시점 판단을 포함'해야
    한다고 정의했다. 각 버전의 부칙에서 적용례/경과조치 조항을 추출하여
    그 버전에서 변경된 조에 연결한다. 이렇게 하면
    "개정된 X조가 이미 선행연구를 시작한 사업에도 적용되는가"
    같은 문항이 gold evidence(본칙 + 부칙 적용례)와 함께 생성된다.

사용법
    py 10_extract_revisions.py raw/admrul_body_history
        -> revision_pairs.jsonl   조 단위 개정 쌍 전체
        -> l4_candidates.jsonl    정답변경 신호가 걸린 쌍
        -> revision_report.md
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

# 07 파서 재사용
_spec = importlib.util.spec_from_file_location(
    "parser07", str(Path(__file__).with_name("07_parse_admrul_v2.py")))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


# ---------------------------------------------------------------- 신호 탐지

RE_NUM = re.compile(r'(\d[\d,]*)\s*(일|개월|년|원|만원|억원|퍼센트|%|명|회|건|배|년간|일간)')
RE_ACTOR = re.compile(r'([가-힣]{2,12}(?:국장|본부장|실장|과장|팀장|청장|장관|위원장|담당관|사업부장|기관장))')
RE_ORG = re.compile(r'([가-힣]{2,15}(?:위원회|본부|부서|팀|국|과))(?=[는이가을를에의])')
RE_REF = re.compile(r'제\s*\d{1,3}\s*조(?:\s*의\s*\d{1,2})?')
RE_MUST = re.compile(r'하여야\s*한다|해야\s*한다')
RE_MAY = re.compile(r'할\s*수\s*있다')
RE_DELETED = re.compile(r'<\s*삭\s*제\s*>')

# 부칙에서 적용례/경과조치 추출
RE_BUCHIK_ART = re.compile(r'제(\d{1,2})조\(([^)]{2,40})\)')
APPLY_KEYS = ("적용례", "경과조치", "경과규정", "특례", "유효기간", "재검토")


def issue_key(v) -> tuple:
    """발령번호를 정렬 가능한 튜플로 만든다.

    훈령은 '969' 처럼 단순 일련번호를 쓰지만, 고시·예규는 '2010-39',
    '제2023-8호' 처럼 연도-일련번호 형식을 쓴다. int() 로 바로 바꾸면
    ValueError 가 난다. 숫자 그룹을 순서대로 뽑아 튜플로 비교한다.
    """
    nums = re.findall(r'\d+', str(v or ""))
    return tuple(int(n) for n in nums) if nums else (0,)


def normalize(s: str) -> str:
    s = re.sub(r'<개정[^>]*>|<신설[^>]*>|<삭제[^>]*>', ' ', s)
    s = re.sub(r'\s+', '', s)
    return s


def signals(old: str, new: str) -> dict:
    """정답 변경 신호를 탐지한다."""
    def setof(pat, t):
        return {m.group(0).strip() for m in pat.finditer(t)}

    sig: dict[str, list] = {}
    for name, pat in (("numbers", RE_NUM), ("actors", RE_ACTOR),
                      ("orgs", RE_ORG), ("refs", RE_REF)):
        a, b = setof(pat, old), setof(pat, new)
        if a != b:
            sig[name] = {"removed": sorted(a - b)[:8],
                         "added": sorted(b - a)[:8]}

    mo, mn = bool(RE_MUST.search(old)), bool(RE_MUST.search(new))
    yo, yn = bool(RE_MAY.search(old)), bool(RE_MAY.search(new))
    if (mo, yo) != (mn, yn):
        sig["modality"] = {"old": {"의무": mo, "재량": yo},
                           "new": {"의무": mn, "재량": yn}}
    return sig


# ---------------------------------------------------------------- 버전 로딩

def load_versions(dirpath: str) -> list[dict]:
    """디렉터리의 모든 응답을 읽는다. 규정 구분은 하지 않는다."""
    out = []
    for f in sorted(Path(dirpath).glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        units, stats, meta = P.parse(rec)
        jos: dict[str, dict] = {}
        for u in units:
            if u["level"] != "jo":
                continue
            code = u["unit_id"].rsplit(":", 1)[-1]     # 000300 형태
            jos[code] = u
        s = rec.get("AdmRulService", rec)
        bc = s.get("부칙", {}) or {}
        out.append(dict(meta=meta, jos=jos, n_units=len(units),
                        buchik_texts=bc.get("부칙내용", []) or [],
                        buchik_nos=bc.get("부칙공포번호", []) or []))
    out.sort(key=lambda v: (str(v["meta"]["effective_date"]),
                            issue_key(v["meta"]["issue_no"])))
    return out


def group_versions(vers: list[dict]) -> dict[str, list[dict]]:
    """행정규칙ID 로 묶는다.

    (a) 한 디렉터리에 여러 규정이 섞이면 서로 다른 규정끼리 diff 를 뜬다.
    (b) 같은 규정이 시기별로 이름을 바꾸므로 이름으로 묶으면 한 규정의
        버전들이 여러 그룹으로 쪼개진다.
        예) 일반무기체계 연구개발 계약특수조건 표준
            <-> 일반무기체계 연구개발 표준계약특수조건
    행정규칙ID 는 개명과 무관하게 유지되므로 이것을 그룹 키로 쓴다.
    표시 이름은 가장 최근 버전의 이름을 쓴다.
    """
    byid: dict[str, list[dict]] = defaultdict(list)
    for v in vers:
        key = str(v["meta"].get("rule_id") or "").strip() \
            or str(v["meta"]["doc_name"]).strip()
        byid[key].append(v)

    g: dict[str, list[dict]] = {}
    for key, lst in byid.items():
        lst.sort(key=lambda v: (str(v["meta"]["effective_date"]),
                                issue_key(v["meta"]["issue_no"])))
        label = str(lst[-1]["meta"]["doc_name"]).strip()
        alias = {str(v["meta"]["doc_name"]).strip() for v in lst} - {label}
        if alias:
            print(f"  [개명 통합] {label} <- {', '.join(sorted(alias))}")
        g[label] = lst
    return g


def _unused_group_by_name(vers: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for v in vers:
        g[str(v["meta"]["doc_name"]).strip()].append(v)
    for k in g:
        g[k].sort(key=lambda v: (str(v["meta"]["effective_date"]),
                                 issue_key(v["meta"]["issue_no"])))
    return dict(g)


def buchik_of(ver: dict) -> list[dict]:
    """이 버전 발령번호에 해당하는 부칙에서 적용례/경과조치를 뽑는다."""
    issue = str(ver["meta"]["issue_no"])
    picked = []
    for i, t in enumerate(ver["buchik_texts"]):
        if not isinstance(t, str):
            continue
        no = str(ver["buchik_nos"][i]) if i < len(ver["buchik_nos"]) else ""
        if no and no != issue:
            continue
        for m in RE_BUCHIK_ART.finditer(t):
            title = m.group(2)
            if any(k in title for k in APPLY_KEYS):
                st = m.start()
                nx = RE_BUCHIK_ART.search(t, m.end())
                body = t[st: nx.start() if nx else min(len(t), st + 600)]
                picked.append(dict(buchik_issue=no, art_no=m.group(1),
                                   title=title, text=body.strip()[:600]))
    return picked


def _tokens(s: str) -> set:
    """매칭용 명사성 토큰. 2자 이상 한글 덩어리."""
    stop = {"관한", "대한", "관련", "적용례", "경과조치", "경과규정", "따른",
            "위한", "등에", "에서", "으로", "하는", "이하", "부터", "까지"}
    return {t for t in re.findall(r'[가-힣]{2,}', s) if t not in stop}


def link_applies(applies: list[dict], jo_title: str, jo_text: str) -> list[dict]:
    """부칙 적용례 제목과 조의 제목·본문을 토큰 겹침으로 매칭한다.

    한 버전의 적용례를 그 버전에서 바뀐 모든 조에 붙이면 gold evidence가
    부정확해진다. 적용례 제목에는 대상이 명시되어 있으므로
    ('국내 구매 추진대상에 관한 적용례', '소요검토팀 구성ㆍ운영에 대한 적용례')
    이를 조제목·본문과 대조하여 점수를 매기고, 겹침이 있는 것만 연결한다.
    """
    tt = _tokens(jo_title) | _tokens(jo_text[:400])
    out = []
    for a in applies:
        at = _tokens(a["title"])
        if not at:
            continue
        hit = at & tt
        # 제목 토큰의 상당 부분이 조에 나타나면 연결
        score = len(hit) / len(at)
        if hit and (score >= 0.34 or len(hit) >= 2):
            out.append({**a, "match_score": round(score, 2),
                        "matched_tokens": sorted(hit)[:6]})
    out.sort(key=lambda x: -x["match_score"])
    return out


# ---------------------------------------------------------------- 메인

def main(dirpath: str) -> None:
    allv = load_versions(dirpath)
    groups = group_versions(allv)
    usable = {k: v for k, v in groups.items() if len(v) >= 2}
    print(f"파일 {len(allv)}개 / 규정 {len(groups)}종 (버전 2개 이상 {len(usable)}종)")
    for k, v in sorted(usable.items(), key=lambda x: -len(x[1])):
        print(f"  {len(v):3}버전  {k}  "
              f"({v[0]['meta']['effective_date']}~{v[-1]['meta']['effective_date']})")
    if not usable:
        sys.exit("버전이 2개 이상인 규정이 없습니다.")

    pairs: list[dict] = []
    kinds = Counter()

    for name, vers in usable.items():
      for i in range(len(vers) - 1):
        a, b = vers[i], vers[i + 1]
        applies = buchik_of(b)
        codes = set(a["jos"]) | set(b["jos"])
        for code in sorted(codes):  # noqa: E111
            ua, ub = a["jos"].get(code), b["jos"].get(code)
            ta = ua["text"] if ua else ""
            tb = ub["text"] if ub else ""
            da = bool(ua and ua.get("deleted"))
            db = bool(ub and ub.get("deleted"))

            if ua is None and ub is not None and not db:
                kind = "신설"
            elif ub is None and ua is not None:
                kind = "제거"
            elif (not da) and db:
                kind = "삭제표시"
            elif da and (not db):
                kind = "부활"
            elif normalize(ta) == normalize(tb):
                continue
            else:
                kind = "개정"

            sig = signals(ta, tb) if kind == "개정" else {}
            ratio = SequenceMatcher(None, normalize(ta), normalize(tb)).ratio() \
                if (ta and tb) else 0.0
            kinds[kind] += 1

            pairs.append(dict(
                doc_name=name, jo_code=code,
                jo=(ub or ua).get("jo"), jo_branch=(ub or ua).get("jo_branch"),
                jo_title=(ub or ua).get("jo_title", ""),
                kind=kind,
                old_issue=a["meta"]["issue_no"], old_eff=a["meta"]["effective_date"],
                new_issue=b["meta"]["issue_no"], new_eff=b["meta"]["effective_date"],
                similarity=round(ratio, 3),
                signals=sig,
                signal_types=sorted(sig.keys()),
                buchik_applies=link_applies(
                    applies, (ub or ua).get("jo_title", ""), tb or ta),
                buchik_all_in_version=len(applies),
                old_text=ta[:1200], new_text=tb[:1200],
            ))

    # L4 후보: 정답변경 신호가 있거나 구조변경(신설/삭제/제거/부활)
    l4 = [p for p in pairs
          if p["signals"] or p["kind"] in ("신설", "제거", "삭제표시", "부활")]
    # 부칙 적용례가 붙은 것을 우선 (설계서 L4 정의 충족)
    l4.sort(key=lambda p: (-len(p["buchik_applies"]), -len(p["signal_types"])))

    def dump(fn, rows):
        with open(fn, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {fn} ({len(rows):,}건)")

    dump("revision_pairs.jsonl", pairs)
    dump("l4_candidates.jsonl", l4)

    sigcnt = Counter(t for p in pairs for t in p["signal_types"])
    withb = sum(1 for p in l4 if p["buchik_applies"])
    byjo = Counter(p["jo_code"] for p in l4)

    per_doc = Counter(p["doc_name"] for p in l4)
    L = ["# 개정 쌍 분석", "",
         f"- 규정 {len(usable)}종 / 버전 {sum(len(v) for v in usable.values())}개",
         f"- 변경된 조 쌍 총 {len(pairs):,}건",
         f"- **L4 후보 {len(l4):,}건** (그중 부칙 적용례 연결 {withb:,}건)", "",
         "## 규정별 L4 후보", "", "| 규정 | L4 후보 | 부칙연결 |", "|---|---|---|"]
    for nm, n in per_doc.most_common():
        wb = sum(1 for p in l4 if p["doc_name"] == nm and p["buchik_applies"])
        L.append(f"| {nm} | {n:,} | {wb:,} |")
    L += ["", "## 변경 유형", "", "| 유형 | 건수 |", "|---|---|"]
    for k, v in kinds.most_common():
        L.append(f"| {k} | {v:,} |")

    L += ["", "## 정답변경 신호 분포", "", "| 신호 | 건수 | 의미 |", "|---|---|---|"]
    mean = {"numbers": "기한·금액·비율 변경", "actors": "권한 주체 변경",
            "orgs": "담당 조직 변경", "refs": "조문 참조 변경",
            "modality": "의무/재량 전환"}
    for k, v in sigcnt.most_common():
        L.append(f"| {k} | {v:,} | {mean.get(k,'')} |")

    L += ["", "## 개정이 잦은 조 상위 25 (L4 문항 우선 대상)", "",
          "| 조 | 조제목 | L4 후보 쌍 수 |", "|---|---|---|"]
    title = {p["jo_code"]: p["jo_title"] for p in l4}
    for code, c in byjo.most_common(25):
        jo = int(code[:4]); br = int(code[4:])
        label = f"제{jo}조" + (f"의{br}" if br else "")
        L.append(f"| {label} | {title.get(code,'')} | {c} |")

    L += ["", "## 부칙 적용례가 붙은 L4 후보 상위 15", "",
          "설계서의 L4 정의(부칙·적용례·경과규정 포함)를 가장 잘 충족하는 항목이다.", "",
          "| 조 | 개정 | 신호 | 부칙 적용례 |", "|---|---|---|---|"]
    for p in [x for x in l4 if x["buchik_applies"]][:15]:
        br = p["jo_branch"]
        label = f"제{p['jo']}조" + (f"의{br}" if str(br) not in ("0", "") else "")
        ap = "; ".join(f"{a['title']}({a['match_score']})"
                       for a in p["buchik_applies"][:2])
        L.append(f"| {label} | {p['old_issue']}→{p['new_issue']} | "
                 f"{', '.join(p['signal_types']) or p['kind']} | {ap[:60]} |")

    L += ["", "## 문항 작성 절차", "",
          "1. `l4_candidates.jsonl` 에서 부칙 적용례가 붙은 항목을 우선 검토한다.",
          "2. 신·구 조문을 읽고 **정답이 실제로 달라지는지** 사람이 확인한다.",
          "   자동 신호는 후보 축소용이지 판정이 아니다.",
          "3. 문항은 현행 기준으로 묻되, 구버전 조문을 그대로",
          "   `distractors.stale_versions` 에 넣고 answer_under_this_version 을 기록한다.",
          "4. 부칙 적용례 조문을 gold_evidence 에 necessity=required 로 추가한다.",
          "   이것이 있어야 L4(적용판단)의 정의를 충족한다."]

    Path("revision_report.md").write_text("\n".join(L), encoding="utf-8")
    print("-> revision_report.md")
    print(f"\nL4 후보 {len(l4):,}건 (부칙 적용례 연결 {withb:,}건) / 목표 20문항")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1])
