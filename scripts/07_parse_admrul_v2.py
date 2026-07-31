#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
행정규칙(훈령·예규·지침) 조문 파서 v2 — 실데이터 구조 기반

v1 대비 수정 사항 (방위사업관리규정 제969호 실물로 확인)
  1. 응답 언랩: AdmRulService > 행정규칙기본정보 / 조문내용 / 부칙 / 별표
  2. 조문내용은 이미 '조 단위'로 분할된 리스트다. 다만 항·호·목이 개행 없이
     한 문자열에 이어 붙어 있으므로 문자열 내부에서 분할해야 한다.
     예) '제2조(적용범위 등) ① … 적용한다.1. 방위사업청과 그 소속기관2. 국방과학연구소…'
  3. 조문내용에 부칙은 들어 있지 않다. 부칙은 별도 필드(병렬 배열 3종).
  4. 조문내용에 편/장/절/관 헤더가 섞여 있다(방위사업관리규정 기준 40개).
     헤더는 unit으로 만들지 않고 이후 조의 chapter/section 맥락으로 기록한다.
  5. '<삭  제>' 조문이 다수다(22개). unit은 만들되 deleted=True 로 표시한다.
  6. 별표와 별지는 '별표키'가 겹치므로 unit_id에 별표구분을 포함해야 한다.

오탐 방지 전략
  항(원문자)·호(숫자.)·목(한글.)은 모두 '1부터 순증하는 후보만 채택'한다.
  이렇게 하면 본문 중의 '<개정 2009.4.1>', '별표 1.' 같은 문자열이 호로
  오인되는 것을 대부분 막을 수 있다.

사용법
    python3 07_parse_admrul_v2.py raw/admrul_body.jsonl
        -> corpus_units.jsonl, parse_report.md
    python3 07_parse_admrul_v2.py --selftest <단일 응답 json>
"""
from __future__ import annotations
import json, re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"
CIRC_MAP = {c: i + 1 for i, c in enumerate(CIRCLED)}
MOK_ORDER = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"

RE_HEADER = re.compile(r"^\s*제\s*\d+\s*[편장절관]\s")
RE_JO_HEAD = re.compile(r"^\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:\(([^)]{0,80})\))?")
RE_DELETED = re.compile(r"<\s*삭\s*제\s*>")
# 호 후보: 숫자(가지 허용) + '.' + 공백
RE_HO_CAND = re.compile(r"(\d{1,3})(?:\s*의\s*(\d{1,2}))?\.\s")
# 목 후보: 한글 한 자 + '.' + 공백
RE_MOK_CAND = re.compile(r"([가-힣])\.\s")


def jo_code(jo: int, br: int = 0) -> str:
    return f"{jo:04d}{br:02d}"


def num_code(n: int, br: int = 0) -> str:
    return f"{n:04d}{br:02d}"


def _seq_filter(cands, key):
    """번호가 1부터 순증하는 후보만 남긴다. 오탐 제거의 핵심."""
    kept, expect = [], 1
    for c in cands:
        if key(c) == expect:
            kept.append(c)
            expect += 1
    return kept


def split_hang(body: str):
    """조 본문을 항 단위로 나눈다. 항 표지는 원문자."""
    pos = [(m.start(), CIRC_MAP[m.group(0)])
           for m in re.finditer(f"[{CIRCLED}]", body)]
    pos = _seq_filter(pos, lambda x: x[1])
    if not pos:
        return [(0, body.strip())]
    out = []
    if pos[0][0] > 0:
        head = body[:pos[0][0]].strip()
        if head:
            out.append((0, head))
    for i, (st, n) in enumerate(pos):
        en = pos[i + 1][0] if i + 1 < len(pos) else len(body)
        out.append((n, body[st:en].strip()))
    return out


def split_ho(text: str):
    """항(또는 조) 본문을 호 단위로 나눈다."""
    cands = [(m.start(), int(m.group(1)), int(m.group(2) or 0), m.end())
             for m in RE_HO_CAND.finditer(text)]
    cands = _seq_filter(cands, lambda x: x[1] if x[2] == 0 else x[1])
    if not cands:
        return [(0, 0, text.strip())]
    out = []
    if cands[0][0] > 0:
        head = text[:cands[0][0]].strip()
        if head:
            out.append((0, 0, head))
    for i, (st, n, br, _e) in enumerate(cands):
        en = cands[i + 1][0] if i + 1 < len(cands) else len(text)
        out.append((n, br, text[st:en].strip()))
    return out


def split_mok(text: str):
    cands = [(m.start(), m.group(1)) for m in RE_MOK_CAND.finditer(text)
             if m.group(1) in MOK_ORDER]
    cands = _seq_filter(cands, lambda x: MOK_ORDER.index(x[1]) + 1)
    if not cands:
        return [("", text.strip())]
    out = []
    if cands[0][0] > 0:
        head = text[:cands[0][0]].strip()
        if head:
            out.append(("", head))
    for i, (st, ch) in enumerate(cands):
        en = cands[i + 1][0] if i + 1 < len(cands) else len(text)
        out.append((ch, text[st:en].strip()))
    return out


def parse(rec: dict):
    s = rec.get("AdmRulService", rec)
    info = s.get("행정규칙기본정보", {})
    seq = str(info.get("행정규칙일련번호", ""))
    base = f"admrul:{seq}"
    meta = dict(doc_name=info.get("행정규칙명", ""), doc_type=info.get("행정규칙종류", ""),
                doc_id=seq, rule_id=str(info.get("행정규칙ID", "")),
                issue_no=str(info.get("발령번호", "")),
                effective_date=str(info.get("시행일자", "")),
                ministry=info.get("소관부처명", ""),
                jo_format=info.get("조문형식여부", ""))
    units, chapter, section = [], "", ""
    stats = dict(jo=0, deleted=0, hang=0, ho=0, mok=0, header=0, unparsed=0,
                 uid_collision=0)
    _seen: set[str] = set()

    def uniq(uid: str) -> str:
        """unit_id 유일성 보장. 충돌은 파서 결함 신호이므로 카운트한다."""
        if uid not in _seen:
            _seen.add(uid)
            return uid
        stats["uid_collision"] += 1
        i = 2
        while f"{uid}~{i}" in _seen:
            i += 1
        _seen.add(f"{uid}~{i}")
        return f"{uid}~{i}"

    def add(level, uid, text, parent="", **kw):
        units.append(dict(unit_id=uniq(uid), tier="T4_행정규칙", level=level,
                          parent_id=parent, chapter=chapter, section=section,
                          text=text, char_len=len(text), **meta, **kw))

    for raw in s.get("조문내용", []):
        if not isinstance(raw, str) or not raw.strip():
            continue
        line = raw.strip()
        if RE_HEADER.match(line):
            stats["header"] += 1
            if re.match(r"^\s*제\s*\d+\s*[편장]", line):
                chapter, section = line, ""
            else:
                section = line
            continue
        m = RE_JO_HEAD.match(line)
        if not m:
            stats["unparsed"] += 1
            continue
        jo_n, br = int(m.group(1)), int(m.group(2) or 0)
        title = (m.group(3) or "").strip()
        code = jo_code(jo_n, br)
        deleted = bool(RE_DELETED.search(line))
        stats["jo"] += 1
        if deleted:
            stats["deleted"] += 1
        add("jo", f"{base}:{code}", line, jo=jo_n, jo_branch=br,
            jo_title=title, deleted=deleted)
        if deleted:
            continue
        body = line[m.end():]
        for hn, htxt in split_hang(body):
            hid = f"{base}:{code}:{num_code(hn)}" if hn else f"{base}:{code}:000000"
            if hn:
                stats["hang"] += 1
                add("hang", hid, htxt, f"{base}:{code}", jo=jo_n, jo_branch=br,
                    jo_title=title, hang=hn, deleted=False)
            for on, obr, otxt in split_ho(htxt):
                if not on:
                    continue
                stats["ho"] += 1
                oid = f"{hid}:{num_code(on, obr)}"
                add("ho", oid, otxt, hid, jo=jo_n, jo_branch=br, jo_title=title,
                    hang=hn, ho=on, ho_branch=obr, deleted=False)
                for mk, mtxt in split_mok(otxt):
                    if not mk:
                        continue
                    stats["mok"] += 1
                    add("mok", f"{oid}:{mk}", mtxt, oid, jo=jo_n, jo_branch=br,
                        jo_title=title, hang=hn, ho=on, ho_branch=obr,
                        mok=mk, deleted=False)

    # 부칙 필드는 문서에 따라 리스트가 아니라 단일 문자열로 온다.
    # 그대로 enumerate 하면 문자를 하나씩 돌면서 한 글자짜리 unit 을
    # 수백 개 만들어낸다. 반드시 리스트로 정규화해야 한다.
    def _lst(x):
        if x is None:
            return []
        return x if isinstance(x, list) else [x]

    bc = s.get("부칙", {}) or {}
    nos = _lst(bc.get("부칙공포번호"))
    txts = _lst(bc.get("부칙내용"))
    dts = _lst(bc.get("부칙공포일자"))
    for i, t in enumerate(txts):
        no = str(nos[i]) if i < len(nos) else str(i)
        add("buchik", f"{base}:buchik:{i:03d}:{no}",
            t if isinstance(t, str) else str(t),
            promulgation_no=no, promulgation_date=str(dts[i]) if i < len(dts) else "")

    bp = _lst((s.get("별표", {}) or {}).get("별표단위"))
    for bi, b in enumerate(bp):
        key = str(b.get("별표키", ""))
        gubun = str(b.get("별표구분", "별표"))
        cont = b.get("별표내용", "")
        if isinstance(cont, list):
            cont = "\n".join(str(x) for x in cont)
        add("byeolpyo", f"{base}:byeolpyo:{bi:03d}:{gubun}:{key}",
            str(cont)[:20000],
            byeolpyo_title=b.get("별표제목", ""), byeolpyo_no=str(b.get("별표번호", "")),
            byeolpyo_gubun=gubun, deleted=bool(RE_DELETED.search(str(cont)[:200])))
    return units, stats, meta

# ---------------------------------------------------------------- CLI

def _iter_records(path):
    import os
    if os.path.isdir(path):
        for f in sorted(Path(path).glob("*.json")):
            yield json.loads(f.read_text(encoding="utf-8"))
        return
    txt = open(path, encoding="utf-8").read().strip()
    if txt.startswith("["):
        yield from json.loads(txt)
    elif path.endswith(".json"):
        yield json.loads(txt)
    else:
        for ln in txt.splitlines():
            if ln.strip():
                yield json.loads(ln)


def run(path: str) -> None:
    all_units, reports = [], []
    for rec in _iter_records(path):
        units, stats, meta = parse(rec)
        all_units.extend(units)
        warn = []
        if meta["jo_format"] == "N":
            warn.append("조문형식여부=N")
        if stats["jo"] == 0:
            warn.append("조 인식 0")
        if stats["unparsed"]:
            warn.append(f"미분류 {stats['unparsed']}줄")
        if stats.get("uid_collision"):
            warn.append(f"unit_id 충돌 {stats['uid_collision']}건(자동 접미사)")
        mains = sorted({u["jo"] for u in units
                        if u["level"] == "jo" and u.get("jo_branch") == 0})
        gaps = ([n for n in range(mains[0], mains[-1] + 1) if n not in mains]
                if mains else [])
        if gaps:
            warn.append(f"조 결번 {len(gaps)}개")
        reports.append(dict(meta=meta, stats=stats, gaps=gaps, warn=warn,
                            units=len(units)))

    with open("corpus_units.jsonl", "w", encoding="utf-8") as f:
        for u in all_units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    L = ["# 행정규칙 파싱 검증 리포트", "",
         f"- 입력 문서 {len(reports)}건 / 생성 unit {len(all_units):,}개",
         f"- 총 문자수 {sum(u['char_len'] for u in all_units):,}",
         f"- 경고 발생 문서 {sum(1 for r in reports if r['warn'])}건",
         f"- unit_id 충돌 총 {sum(r['stats'].get('uid_collision',0) for r in reports)}건"
         " (접미사 ~N 으로 자동 해소)", "",
         "| 행정규칙명 | 발령 | 시행일 | 조 | 삭제 | 항 | 호 | 목 | 별표 | 부칙 | 경고 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        m, s = r["meta"], r["stats"]
        L.append(f"| {m['doc_name']} | {m['issue_no']} | {m['effective_date']} | "
                 f"{s['jo']} | {s['deleted']} | {s['hang']} | {s['ho']} | "
                 f"{s['mok']} | - | - | {'; '.join(r['warn'])} |")
    L += ["", "## 조 결번 상세", ""]
    for r in reports:
        if r["gaps"]:
            L.append(f"- {r['meta']['doc_name']} ({r['meta']['issue_no']}): "
                     f"{r['gaps'][:30]}")
    L += ["", "## 수동 검증 절차", "",
          "무작위 20개 조를 골라 law.go.kr 원문과 대조하고 항·호·목 분할 정확도를",
          "기록한다. 목표: 조 인식률 100%, 항·호 분할 정확도 95% 이상.",
          "결번은 삭제 후 조문 자체가 제거된 경우가 있으므로 오류가 아닐 수 있다."]
    open("parse_report.md", "w", encoding="utf-8").write("\n".join(L))
    print(f"-> corpus_units.jsonl ({len(all_units):,} units)")
    print(f"-> parse_report.md")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        u, st, mt = parse(json.load(open(sys.argv[2], encoding="utf-8")))
        print("meta :", mt)
        print("stats:", st)
        print("units:", len(u), "| unit_id 중복:",
              len(u) - len({x["unit_id"] for x in u}))
    elif len(sys.argv) > 1:
        run(sys.argv[1])
    else:
        print(__doc__)
