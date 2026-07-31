#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
문항 100개 층화 추출 — 어노테이션 슬롯 생성

후보 풀에서 문항 자리를 뽑고, gold evidence 를 미리 채운 '빈 문항'을 만든다.
사람은 질문문과 정답만 쓰면 된다. 근거는 이미 unit_id 로 확정되어 있다.

배분 (설계서 3절)
    L1 단일조문 조회      20
    L2 조문결합 해석      20   동일 위계 내 내부참조가 있는 조
    L3 위계횡단 재구성    20   l3_final.jsonl
    L4 적용판단           20   l4_candidates.jsonl (부칙 적용례 연결 우선)
    범위밖 통제           20   결손 유형 4종에 배분
    ------------------------
    합계                 100

L2 후보 탐지
    조 본문에 문서명 없이 '제N조' 만 나오면 같은 문서 안의 조를 가리킨다.
    그 조가 실제로 존재하면 동일 위계 2개 이상의 gold evidence 가 성립한다.
    09_extract_refs.py 는 외부 참조만 다뤘으므로 여기서 별도로 찾는다.

층화 원칙
    - 규정당 상한을 둔다 (기본 2). 한 규정에 문항이 몰리면 외적 타당도가 준다.
    - L1 은 위계별로 배분한다. T1~T3 은 분량이 4.8%뿐이지만 절반을 할당한다.
      분량 비례로 뽑으면 상위법 문항이 거의 안 나온다.
    - 난수 시드를 고정하고 기록한다.

사용법
    py 17_sample_questions.py corpus_final.jsonl
        [--l3 l3_final.jsonl] [--l4 l4_candidates.jsonl]
        [--oos oos_sources.jsonl] [--seed 20260721]
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

AS_OF = "2026-07-21"          # 코퍼스 수집 시점 현행 기준
PER_DOC_CAP = 2
L4_DOC_CAP = 5      # L4 가 한 규정에 몰리면 커버리지 조작에서 문서 효과와 교란된다
SEED = 20260721

RE_BARE_JO = re.compile(r'(?<![가-힣」』])제\s*(\d{1,3})\s*조(?:\s*의\s*(\d{1,2}))?')

# 외부 문서를 가리키는 인용을 먼저 지운다. 남는 '제N조'만 내부참조다.
#   「국가계약법 시행령」 제26조   <- 정식명칭 인용
#   법 제25조 / 영 제22조 / 규칙 제3조 / 혁신법 시행령 제45조  <- 약어 인용
# 이걸 지우지 않으면 모법 참조가 동일 위계 내부참조로 오인되어
# L2 와 L3 의 수준 정의가 무너진다.
RE_EXT_QUOTED = re.compile(r'[「『][^」』]{2,60}[」』]\s*제\s*\d{1,3}\s*조'
                           r'(?:\s*의\s*\d{1,2})?')
RE_EXT_ALIAS = re.compile(
    r'[가-힣]{0,12}(?:법률|법|시행령|령|영|시행규칙|규칙|규정|훈령|예규|고시|'
    r'지침|기준|세칙)\s*제\s*\d{1,3}\s*조(?:\s*의\s*\d{1,2})?')



# ---------------------------------------------------------------- 조 전문 조립

SPAN_CAP = 8000        # gold 조문 저장 상한(문자). 중복 제거 후 기준.


def dedup_parts(parts: list[str]) -> str:
    """조 전문을 조립하되 중복을 제거한다.

    파서에 따라 조 unit 의 text 가 이미 전문(항·호 포함)을 담고 있다.
    행정규칙(07 파서)이 그렇고, 법률(14 파서)은 조 제목만 담는다.
    그래서 '조 text + 하위 unit' 을 그대로 이어붙이면 행정규칙만
    같은 내용이 2~3회 반복된다. 실측: gold 텍스트의 27% 가 중복이었고,
    그 중복이 1500자 상한을 먹어 100슬롯 중 34개의 조문 뒷부분이 소실됐다.

    앞서 담은 내용에 이미 포함된 조각은 버린다. 법률처럼 중복이
    없는 경우에는 아무것도 버리지 않으므로 양쪽 파서에 모두 안전하다.
    """
    kept: list[str] = []
    acc = ""
    for p in parts:
        flat = re.sub(r'\s+', '', p or '')
        if flat and flat in acc:
            continue
        if not flat:
            continue
        kept.append(p)
        acc += flat
    return "\n".join(kept)


def code6(n: int, br: int = 0) -> str:
    return f"{n:04d}{br:02d}"


def load(p: str) -> list[dict]:
    f = Path(p)
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------- 코퍼스

class Corpus:
    def __init__(self, path: str):
        self.units: dict[str, dict] = {}
        self.jo_by_doc: dict[str, dict[str, dict]] = defaultdict(dict)
        self.doc_meta: dict[str, dict] = {}
        self.buchik: dict[str, dict[str, dict]] = defaultdict(dict)
        self.by_name: dict[str, str] = {}
        for l in Path(path).read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            u = json.loads(l)
            self.units[u["unit_id"]] = u
            did = str(u.get("doc_id", ""))
            if u.get("level") == "jo":
                self.jo_by_doc[did][u["unit_id"].rsplit(":", 1)[-1]] = u
            elif u.get("level") == "buchik":
                self.buchik[did][str(u.get("promulgation_no", ""))] = u
            self.by_name.setdefault(str(u.get("doc_name", "")), did)
            self.doc_meta.setdefault(did, dict(
                doc_name=u.get("doc_name", ""), tier=u.get("tier", ""),
                doc_type=u.get("doc_type", ""), prefix=u["unit_id"].split(":", 1)[0],
                issue_no=u.get("issue_no", ""),
                effective_date=u.get("effective_date", "")))

    def jo(self, did: str, jo: int, br: int = 0) -> dict | None:
        return self.jo_by_doc.get(did, {}).get(code6(jo, br))

    def jo_fulltext(self, u: dict) -> str:
        """조의 전문을 조립한다.

        한국 법률은 '제N조(제목)' 다음에 바로 항이 오는 구조라, jo unit 의
        text 에는 제목만 있고 실제 내용은 하위 항/호/목 unit 에 흩어져 있다.
        gold evidence 에 조 제목만 담으면 정작 정답 근거가 빠진다.
        그래서 같은 조에 속한 모든 하위 unit 을 unit_id 순으로 이어 붙인다.
        """
        did = str(u.get("doc_id", ""))
        jc = u["unit_id"].rsplit(":", 1)[-1]
        prefix = u["unit_id"].split(":", 1)[0]
        base = f"{prefix}:{did}:{jc}"
        parts = []
        for uid in sorted(self.units):
            if uid == u["unit_id"] or uid.startswith(base + ":"):
                t = self.units[uid].get("text", "").strip()
                if t:
                    parts.append(t)
        return dedup_parts(parts) or u.get("text", "")

    def doc_id_of(self, name: str) -> str:
        return self.by_name.get(name, "")

    def buchik_of(self, did: str, promulgation_no: str) -> dict | None:
        return self.buchik.get(did, {}).get(str(promulgation_no))


def ev(c: Corpus, u: dict, necessity: str = "required") -> dict:
    did = str(u.get("doc_id", ""))
    m = c.doc_meta.get(did, {})
    loc = {}
    if u.get("jo"):
        loc["조"] = str(u["jo"]) + (f"의{u['jo_branch']}" if u.get("jo_branch") else "")
    for k, f in (("항", "hang"), ("호", "ho"), ("목", "mok")):
        if u.get(f):
            loc[k] = str(u[f])
    # 조 단위면 하위 항/호/목을 포함한 전문을 담는다. 항/호/목 단위면 그대로.
    span = c.jo_fulltext(u) if u.get("level") == "jo" else u.get("text", "")
    return dict(unit_id=u["unit_id"], tier=u.get("tier", ""),
                doc_type=m.get("doc_type", ""), doc_name=u.get("doc_name", ""),
                doc_id=did, issue_no=m.get("issue_no", ""),
                effective_date=m.get("effective_date", ""),
                locator=loc, text_span=span[:SPAN_CAP],
                necessity=necessity)


def slot(qid: str, level: int, answerable: bool, gold: list[dict],
         origin: str, note: str, extra: dict | None = None) -> dict:
    tiers = {g["tier"] for g in gold if g.get("tier")}
    d = dict(
        qid=qid, as_of=AS_OF, level=level,
        level_justification=note,
        question_ko="", question_en="",
        answerable=answerable,
        out_of_scope_reason=None if answerable else "see source.note",
        answer_short="", answer_long="", answer_alternatives=[],
        gold_evidence=gold,
        evidence_profile=dict(
            unit_count=len(gold),
            required_count=sum(1 for g in gold if g["necessity"] == "required"),
            tier_span=len(tiers),
            has_supplementary=any("부칙" in str(g.get("unit_id", "")) for g in gold)),
        distractors=dict(stale_versions=[], sibling_provisions=[],
                         cross_tier_lookalikes=[]),
        source=dict(origin=origin, note=note),
        quality_checks=dict(lexical_leak_max_ngram=None, lexical_leak_pass=None,
                            single_answer_verified=False, proper_noun_count=None),
        annotation=dict(annotator_a="", annotator_b="", level_agreed=None,
                        evidence_jaccard=None, adjudicator=None,
                        adjudication_note=None, status="draft",
                        rejection_reason=None),
        condition_labels={})
    if extra:
        d.update(extra)
    return d


# ---------------------------------------------------------------- 후보 생성

def pool_l1(c: Corpus) -> list[dict]:
    """단답이 나올 만한 조: 제목 있고, 적당한 길이, 수치·주체·기한 포함."""
    sig = re.compile(r'\d+\s*(일|개월|년|퍼센트|%|명|회|억원|만원|원)|'
                     r'[가-힣]{2,10}(장|관|위원회|부서)')
    out = []
    for did, jos in c.jo_by_doc.items():
        for u in jos.values():
            if u.get("deleted") or not u.get("jo_title"):
                continue
            t = u.get("text", "")
            if not (60 <= len(t) <= 500) or not sig.search(t):
                continue
            out.append(u)
    return out


def pool_l2(c: Corpus) -> list[dict]:
    """같은 문서 안의 다른 조를 인용하는 조. 인용 대상이 실존해야 한다."""
    out = []
    for did, jos in c.jo_by_doc.items():
        for u in jos.values():
            if u.get("deleted"):
                continue
            t = u.get("text", "")
            body = RE_EXT_QUOTED.sub(" ", t)
            body = RE_EXT_ALIAS.sub(" ", body)     # 약어 인용까지 제거
            refs = []
            for m in RE_BARE_JO.finditer(body):
                jn, br = int(m.group(1)), int(m.group(2) or 0)
                if jn == u.get("jo") and br == (u.get("jo_branch") or 0):
                    continue
                tgt = c.jo(did, jn, br)
                if tgt and not tgt.get("deleted"):
                    refs.append(tgt)
            uniq = {r["unit_id"]: r for r in refs}
            if uniq:
                out.append((u, list(uniq.values())))
    return out


def jolabel(u: dict) -> str:
    br = u.get("jo_branch") or 0
    return f"제{u.get('jo')}조" + (f"의{br}" if br else "")


def take(items, key, cap: int, n: int, rng) -> list:
    """규정당 상한을 지키며 n개를 뽑는다."""
    rng.shuffle(items)
    used: Counter = Counter()
    got = []
    for it in items:
        k = key(it)
        if used[k] >= cap:
            continue
        used[k] += 1
        got.append(it)
        if len(got) >= n:
            break
    return got


# ---------------------------------------------------------------- 메인

def main(corpus_path: str, l3p: str, l4p: str, oosp: str, seed: int,
         allow_missing: bool = False) -> None:
    # 입력 파일이 없으면 load() 가 조용히 []를 돌려줘 L3/L4/OOS 가 0건이 된다.
    # 그 상태로 슬롯을 덮어쓰면 작성분이 날아간다. 먼저 막는다.
    missing = [x for x in (corpus_path, l3p, l4p, oosp) if not Path(x).exists()]
    if missing and not allow_missing:
        print("*** 입력 파일 없음:")
        for x in missing:
            print(f"      {x}")
        print("    경로를 확인하거나, 의도한 것이면 --allow-missing 을 주십시오.")
        raise SystemExit(2)

    rng = random.Random(seed)
    c = Corpus(corpus_path)
    print(f"코퍼스 {len(c.units):,} unit / 문서 {len(c.doc_meta)}종  (seed={seed})")

    slots: list[dict] = []
    stat: dict[str, int] = {}

    # ---- L1
    p1 = pool_l1(c)
    picked = take(p1, lambda u: u["doc_id"], PER_DOC_CAP, 20, rng)
    # 위계 균형: T1~T3 를 절반 이상 확보
    upper = [u for u in p1 if not str(u.get("tier", "")).startswith("T4")]
    if upper:
        need = max(0, 10 - sum(1 for u in picked
                               if not str(u.get("tier", "")).startswith("T4")))
        add = take(upper, lambda u: u["doc_id"], PER_DOC_CAP, need, rng)
        seen = {u["unit_id"] for u in picked}
        picked = [u for u in picked if str(u.get("tier", "")).startswith("T4")][:20 - len(add)]
        picked += [a for a in add if a["unit_id"] not in seen]
    for i, u in enumerate(picked[:20], 1):
        slots.append(slot(f"DAPA-L1-{i:03d}", 1, True, [ev(c, u)],
                          "조문직접생성",
                          f"gold unit 1개, 단일 문서({u['doc_name']} {jolabel(u)})"))
    stat["L1"] = min(len(picked), 20)

    # ---- L2
    p2 = pool_l2(c)
    picked2 = take(p2, lambda x: x[0]["doc_id"], PER_DOC_CAP, 20, rng)
    for i, (u, refs) in enumerate(picked2[:20], 1):
        gold = [ev(c, u)] + [ev(c, r, "required") for r in refs[:2]]
        slots.append(slot(f"DAPA-L2-{i:03d}", 2, True, gold, "조문직접생성",
                          f"동일 위계 내 {len(gold)}개 조 결합 "
                          f"({u['doc_name']} {jolabel(u)} → "
                          f"{', '.join(jolabel(r) for r in refs[:2])})"))
    stat["L2"] = min(len(picked2), 20)

    # ---- L3
    l3_all = load(l3p)
    # 부분통과(pass_partial)는 깨진 참조를 안고 있다. 그 조의 본문이 삭제된
    # 조를 근거로 삼고 있으면 정답이 흔들리므로 완전통과만 쓴다.
    l3 = [r for r in l3_all if r.get("status") == "pass"] or l3_all
    if len(l3) != len(l3_all):
        print(f"  L3: 완전통과 {len(l3)}건만 사용 (부분통과 {len(l3_all)-len(l3)}건 제외)")
    picked3 = take(l3, lambda r: r.get("doc_name", ""), PER_DOC_CAP, 20, rng)
    for i, r in enumerate(picked3[:20], 1):
        head = c.jo(str(r.get("doc_id", "")), int(r.get("jo") or 0),
                    int(r.get("jo_branch") or 0))
        gold = ([ev(c, head)] if head else [])
        for g in r.get("gold_refs", []):
            u = c.units.get(g.get("unit_id", ""))
            if u:
                gold.append(ev(c, u))
        slots.append(slot(f"DAPA-L3-{i:03d}", 3, True, gold, "참조자동추출",
                          f"위계 {r.get('resolved_ext_tier_span')}개 횡단 "
                          f"({'/'.join(r.get('resolved_tiers', []))})"))
    stat["L3"] = min(len(picked3), 20)

    # ---- L4 (부칙 적용례 연결 우선)
    l4 = load(l4p)
    l4.sort(key=lambda p: (-len(p.get("buchik_applies", [])),
                           -len(p.get("signal_types", []))))
    picked4, used = [], Counter()
    seen_jo = set()

    def _head_of(p):
        did = c.doc_id_of(str(p.get("doc_name", "")))
        return c.jo_by_doc.get(did, {}).get(p.get("jo_code", ""))

    # 상한을 1씩 올리며 반복한다. 한 번에 상한을 풀면 목록 앞쪽 규정이
    # 남은 자리를 독식해 분포가 치우친다.
    for cap in range(L4_DOC_CAP, 21):
        for p in l4:
            if len(picked4) >= 20:
                break
            nm = str(p.get("doc_name", ""))
            key = (nm, p.get("jo_code", ""))
            if key in seen_jo or used[nm] >= cap:
                continue
            head = _head_of(p)
            if not head or head.get("deleted"):
                continue
            seen_jo.add(key)
            used[nm] += 1
            picked4.append((p, head))
        if len(picked4) >= 20:
            break
    print(f"  L4: 규정별 분포 {dict(used)}")
    n_with_buchik = 0
    for i, (p, head) in enumerate(picked4, 1):
        gold = [ev(c, head)]
        # 설계서 L4 정의: 본칙 조 + 부칙 적용례가 함께 gold evidence 여야 한다.
        did_h = str(head.get("doc_id", ""))
        seen_b = set()
        for ap in p.get("buchik_applies", []):
            bu = c.buchik_of(did_h, ap.get("buchik_issue", ""))
            if bu and bu["unit_id"] not in seen_b:
                seen_b.add(bu["unit_id"])
                g = ev(c, bu, "required")
                g["applies_title"] = ap.get("title", "")
                g["applies_art"] = ap.get("art_no", "")
                gold.append(g)
        if len(gold) > 1:
            n_with_buchik += 1
        note = (f"개정 {p.get('old_issue')}→{p.get('new_issue')}, "
                f"신호 {','.join(p.get('signal_types', [])) or p.get('kind')}")
        extra = dict(distractors=dict(
            stale_versions=[dict(unit_id=head["unit_id"],
                                 issue_no=str(p.get("old_issue")),
                                 effective_date=str(p.get("old_eff")),
                                 answer_under_this_version="",
                                 diff_note=p.get("old_text", "")[:300])],
            sibling_provisions=[], cross_tier_lookalikes=[]))
        # 부칙 적용례 유무에 따라 문항 작성 방식이 달라진다.
        #   있음: "개정된 X조가 이미 착수한 사업에도 적용되는가" (적용례 판단형)
        #   없음: "현행 기준으로 이 절차는 어떻게 되는가"        (시점 판단형)
        if p.get("buchik_applies"):
            note += (f" / 부칙 적용례 {len(p['buchik_applies'])}건"
                     f" [적용례판단형]")
        else:
            note += " / 부칙 적용례 없음 [시점판단형]"
        slots.append(slot(f"DAPA-L4-{i:03d}", 4, True, gold, "개정이력",
                          note, extra))
    stat["L4"] = len(picked4)
    print(f"  L4: 부칙 적용례가 gold 에 붙은 문항 {n_with_buchik}/{len(picked4)}")

    # ---- 범위밖 (결손 유형 배분)
    oos = load(oosp)
    gaps = load("gap_missing_provision.jsonl")
    buckets = {"out_of_scope": [], "abolished_cited": [],
               "unobtainable_cited": [], "deleted_provision": []}
    for g in load("gap_deleted_provision.jsonl"):
        nm = str(g.get("citing_doc", "")).strip()
        buckets["deleted_provision"].append(
            (dict(doc_name=nm, jo=g.get("citing_jo"), jo_branch=0,
                  doc_id=c.doc_id_of(nm)),
             f"{g.get('matched_doc','')} 제{g.get('jo')}조(삭제)"))
    for r in oos:
        for t, kind in (r.get("gap_targets") or {}).items():
            if kind in buckets:
                buckets[kind].append((r, t))
        if r.get("out_scope_targets"):
            buckets["out_of_scope"].append((r, r["out_scope_targets"][0]))
    plan = [("out_of_scope", 8), ("abolished_cited", 4),
            ("unobtainable_cited", 5), ("deleted_provision", 3)]
    idx = 1
    for kind, n in plan:
        pool = buckets.get(kind, [])
        sel = take(pool, lambda x: x[0].get("doc_name", ""), PER_DOC_CAP, n, rng)
        for r, tgt in sel:
            head = c.jo(str(r.get("doc_id", "")), int(r.get("jo") or 0),
                        int(r.get("jo_branch") or 0))
            slots.append(slot(
                f"DAPA-OOS-{idx:03d}", 0, False,
                [ev(c, head, "supporting")] if head else [],
                "경계밖참조",
                f"{kind}: {r.get('doc_name')} 제{r.get('jo')}조가 「{tgt}」를 인용",
                dict(out_of_scope_reason=kind)))
            idx += 1
    stat["OOS"] = idx - 1

    with open("question_slots.jsonl", "w", encoding="utf-8") as f:
        for s in slots:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    L = ["# 문항 슬롯 (작성 대기)", "",
         f"- 총 {len(slots)}개 / seed {seed} / as_of {AS_OF}",
         f"- 배분 " + " · ".join(f"{k} {v}" for k, v in stat.items()), "",
         "각 슬롯은 gold evidence 가 unit_id 로 확정되어 있다.",
         "작성자는 `question_ko`, `answer_short`, `answer_long` 만 채운다.", "",
         "## 작성 규칙 (설계서 4절)", "",
         "- R1 질문에 gold 조문의 연속 5어절 이상을 쓰지 않는다 (어휘 누출)",
         "- R2 단답 15자 이내 / 서술 2~3문장 / L4는 적용여부·근거·시점 3요소",
         "- R3 고유명사·연도 최소화",
         "- R5 기준일은 질문문에 쓰지 않는다 (시스템 프롬프트로 일괄 제공)", "",
         "## 슬롯 목록", "",
         "| qid | 수준 | 근거 unit | 위계 | 근거 요약 |", "|---|---|---|---|---|"]
    for s in slots:
        g = s["gold_evidence"]
        L.append(f"| {s['qid']} | {s['level']} | {len(g)} | "
                 f"{s['evidence_profile']['tier_span']} | {s['source']['note'][:70]} |")
    Path("question_worksheet.md").write_text("\n".join(L), encoding="utf-8")

    print("\n배분:", stat, f"총 {len(slots)}")
    print("-> question_slots.jsonl, question_worksheet.md")
    short = {k: v for k, v in stat.items() if v < (20 if k != "OOS" else 20)}
    if short:
        print(f"   ! 목표 미달: {short} — 후보 풀 또는 상한(PER_DOC_CAP)을 조정하세요")


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        SPAN_CAP = int(opt("--span-cap", str(SPAN_CAP)))
        main(a[1], opt("--l3", "l3_final.jsonl"), opt("--l4", "l4_candidates.jsonl"),
             opt("--oos", "oos_sources.jsonl"), int(opt("--seed", str(SEED))),
             "--allow-missing" in a)
