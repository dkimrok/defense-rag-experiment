#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
법령(T1~T3) 파서 — eflaw 응답 → corpus unit

07_parse_admrul_v2.py 는 행정규칙 전용이다. 법령은 응답 구조가 전혀 다르다.

    법령
      기본정보  법령명_한글, 법령ID, 공포번호/일자, 시행일자,
                법종구분{content, 법종구분코드}, 소관부처{content, 소관부처코드}
      조문
        조문단위  (조문이 하나면 dict, 전체 조회면 list)
          조문번호, 조문가지번호, 조문제목, 조문내용, 조문키,
          조문시행일자, 조문변경여부, 조문제개정유형, 조문여부
          항  (항이 없으면 {호:[...]}, 있으면 [{항번호, 항내용, 호:[...]}])
            호  [{호번호:'1.'|'9의2.', 호내용, 목:[{목번호:'가.', 목내용}]}]

주의할 점 세 가지
  1. 항이 dict 인 경우가 있다. 제3조처럼 항 번호 없이 호만 나열되는 조문이다.
  2. 호번호에 가지번호가 붙는다. '9의2.' -> 호 9, 가지 2 (unit_id 000902)
  3. 목내용이 중첩 리스트로 온다. 방위사업법 제3조제13호가목이 실제 사례이며
     [[ '가. ...', '  1) ...', '  2) ...' ]] 형태다. 평탄화가 필요하다.

행정규칙과 동일한 unit_id 좌표계를 쓴다. 그래야 T1~T4가 한 코퍼스로 조인된다.
    law:{법령ID}:{조6}:{항6}:{호6}:{목}
    조6 = 조번호 4자리 + 조가지번호 2자리 (제10조의2 -> 001002)

사용법
    py 14_parse_law.py raw/law_scope raw/law
        -> corpus_units_law.jsonl, parse_law_report.md
    py 14_parse_law.py --selftest <단일 eflaw json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# 법종구분 -> tier
TIER_BY_KIND = {
    "법률": "T1_법률",
    "대통령령": "T2_대통령령",
    "총리령": "T3_부령",
    "부령": "T3_부령",
    "국방부령": "T3_부령",
}

RE_NO = re.compile(r'(\d{1,3})(?:\s*의\s*(\d{1,2}))?')

# 법제처는 항번호를 원문자로 주는 경우가 있다. 숫자만 파싱하면 항이 전부
# 0으로 떨어져 제1항제1호와 제2항제1호의 unit_id 가 충돌한다.
CIRCLED = ("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
           "㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵")
CIRC_MAP = {c: i + 1 for i, c in enumerate(CIRCLED)}


def code6(n: int, br: int = 0) -> str:
    return f"{n:04d}{br:02d}"


def parse_no(s: Any) -> tuple[int, int]:
    """'9의2.' -> (9, 2), '1.' -> (1, 0), '①' -> (1, 0)"""
    t = str(s or "")
    for ch in t:
        if ch in CIRC_MAP:
            return (CIRC_MAP[ch], 0)
    m = RE_NO.search(t)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))


def flatten(x: Any) -> str:
    """목내용이 중첩 리스트로 오는 경우를 평탄화한다."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, list):
        return "\n".join(p for p in (flatten(i) for i in x) if p)
    if isinstance(x, dict):
        return "\n".join(p for p in (flatten(v) for v in x.values()) if p)
    return str(x).strip()


def as_list(x: Any) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def unwrap(d: Any) -> dict:
    if not isinstance(d, dict):
        return {}
    if "기본정보" in d:
        return d
    for v in d.values():
        if isinstance(v, dict):
            return v
    return d


def parse(rec: dict) -> tuple[list[dict], dict, dict]:
    body = unwrap(rec)
    info = body.get("기본정보", {}) or {}

    kind = info.get("법종구분")
    kind = kind.get("content") if isinstance(kind, dict) else str(kind or "")
    ministry = info.get("소관부처")
    ministry = ministry.get("content") if isinstance(ministry, dict) else str(ministry or "")

    law_id = str(info.get("법령ID") or "")
    meta = dict(
        doc_name=str(info.get("법령명_한글") or ""),
        doc_type=kind,
        doc_id=law_id,
        issue_no=str(info.get("공포번호") or ""),
        effective_date=str(info.get("시행일자") or ""),
        ministry=ministry,
        jo_format="Y",
    )
    tier = TIER_BY_KIND.get(kind, "T3_부령" if "령" in kind else "T1_법률")
    base = f"law:{law_id}"

    units: list[dict] = []
    stats = dict(jo=0, deleted=0, hang=0, ho=0, mok=0, header=0, unparsed=0,
                 uid_collision=0)
    chapter = ""
    _seen: set[str] = set()

    def uniq(uid: str) -> str:
        if uid not in _seen:
            _seen.add(uid)
            return uid
        stats["uid_collision"] += 1
        i = 2
        while f"{uid}~{i}" in _seen:
            i += 1
        _seen.add(f"{uid}~{i}")
        return f"{uid}~{i}"

    def add(level: str, uid: str, text: str, parent: str = "", **kw) -> None:
        units.append(dict(unit_id=uniq(uid), tier=tier, level=level,
                          parent_id=parent, chapter=chapter, section="",
                          text=text, char_len=len(text), **meta, **kw))

    for jo in as_list((body.get("조문") or {}).get("조문단위")):
        if not isinstance(jo, dict):
            continue

        # 편/장/절 헤더는 조문여부가 '조문'이 아니다
        if str(jo.get("조문여부", "조문")) != "조문":
            chapter = flatten(jo.get("조문내용"))
            stats["header"] += 1
            continue

        jn = int(str(jo.get("조문번호") or 0) or 0)
        jb = int(str(jo.get("조문가지번호") or 0) or 0)
        jc = code6(jn, jb)
        title = str(jo.get("조문제목") or "")
        jtext = flatten(jo.get("조문내용"))
        deleted = "삭제" in jtext[:40] and len(jtext) < 60
        stats["jo"] += 1
        if deleted:
            stats["deleted"] += 1

        add("jo", f"{base}:{jc}", jtext, jo=jn, jo_branch=jb, jo_title=title,
            deleted=deleted, jo_effective=str(jo.get("조문시행일자") or ""),
            jo_changed=str(jo.get("조문변경여부") or ""),
            jo_revision_type=str(jo.get("조문제개정유형") or ""))
        if deleted:
            continue

        hang_raw = jo.get("항")
        # 항이 dict 이고 호만 있으면, 항 번호 없는 조문이다
        if isinstance(hang_raw, dict) and "항번호" not in hang_raw:
            hangs = [{"항번호": "", "항내용": "", "호": hang_raw.get("호")}]
        else:
            hangs = as_list(hang_raw)

        multi_hang = len(hangs) > 1
        for idx, h in enumerate(hangs, 1):
            if not isinstance(h, dict):
                continue
            htext = flatten(h.get("항내용"))
            hn, _ = parse_no(h.get("항번호"))
            if not hn:                       # 항번호가 비면 본문 선두 원문자에서
                hn, _ = parse_no(htext[:4])
            if not hn and multi_hang:        # 그래도 없으면 등장 순서로
                hn = idx
                stats["hang_by_index"] = stats.get("hang_by_index", 0) + 1
            hid = f"{base}:{jc}:{code6(hn)}" if hn else f"{base}:{jc}:000000"
            if hn:
                stats["hang"] += 1
                add("hang", hid, htext, f"{base}:{jc}", jo=jn, jo_branch=jb,
                    jo_title=title, hang=hn, deleted=False)

            for o in as_list(h.get("호")):
                if not isinstance(o, dict):
                    continue
                on, ob = parse_no(o.get("호번호"))
                if not on:
                    continue
                otext = flatten(o.get("호내용"))
                oid = f"{hid}:{code6(on, ob)}"
                stats["ho"] += 1
                add("ho", oid, otext, hid, jo=jn, jo_branch=jb, jo_title=title,
                    hang=hn, ho=on, ho_branch=ob, deleted=False)

                for mk in as_list(o.get("목")):
                    if not isinstance(mk, dict):
                        continue
                    mno = str(mk.get("목번호") or "").strip().rstrip(".")
                    if not mno:
                        continue
                    stats["mok"] += 1
                    add("mok", f"{oid}:{mno}", flatten(mk.get("목내용")), oid,
                        jo=jn, jo_branch=jb, jo_title=title, hang=hn,
                        ho=on, ho_branch=ob, mok=mno, deleted=False)

    # 부칙 / 별표
    for i, b in enumerate(as_list(body.get("부칙", {}).get("부칙단위")
                                  if isinstance(body.get("부칙"), dict) else None)):
        if isinstance(b, dict):
            add("buchik", f"{base}:buchik:{i:03d}", flatten(b.get("부칙내용")),
                promulgation_no=str(b.get("부칙공포번호") or ""),
                promulgation_date=str(b.get("부칙공포일자") or ""))

    return units, stats, meta


# ---------------------------------------------------------------- CLI

def run(paths: list[str]) -> None:
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        files += sorted(pp.glob("*.json")) if pp.is_dir() else [pp]

    all_units: list[dict] = []
    reports: list[dict] = []
    seen_ids: set[str] = set()

    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:                               # noqa: BLE001
            print(f"  ! {f.name}: {e}")
            continue
        units, stats, meta = parse(rec)
        if not meta["doc_id"]:
            print(f"  ! {f.name}: 법령ID 없음, 건너뜀")
            continue
        if meta["doc_id"] in seen_ids:
            print(f"  = {meta['doc_name']}: 중복 법령ID, 건너뜀")
            continue
        seen_ids.add(meta["doc_id"])
        all_units += units
        warn = []
        if stats["jo"] == 0:
            warn.append("조 인식 0")
        if stats.get("uid_collision"):
            warn.append(f"unit_id 충돌 {stats['uid_collision']}건(자동 접미사)")
        reports.append(dict(meta=meta, stats=stats, warn=warn, tier=units[0]["tier"] if units else "?"))

    from collections import Counter
    dup = [k for k, v in Counter(u["unit_id"] for u in all_units).items() if v > 1]
    if dup:
        print(f"  !! unit_id 충돌 {len(dup)}건 — 항 파싱 실패 의심")
        for k in dup[:5]:
            print(f"     {k}")

    with open("corpus_units_law.jsonl", "w", encoding="utf-8") as fh:
        for u in all_units:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")

    n_hang = sum(r["stats"]["hang"] for r in reports)
    n_jo = sum(r["stats"]["jo"] for r in reports)
    L = ["# 법령 파싱 결과", "",
         f"- 법령 {len(reports)}건 / unit {len(all_units):,}개",
         f"- 총 문자수 {sum(u['char_len'] for u in all_units):,}",
         f"- unit_id 충돌 {len(dup)}건" + (" **점검 필요**" if dup else ""),
         f"- 조 {n_jo:,} / 항 {n_hang:,}"
         + ("  **항이 0이면 항번호 파싱 실패다**" if n_jo and not n_hang else ""), "",
         "| 법령 | 위계 | 소관 | 시행일 | 조 | 항 | 호 | 목 | 경고 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(reports, key=lambda x: (x["tier"], x["meta"]["doc_name"])):
        m, s = r["meta"], r["stats"]
        L.append(f"| {m['doc_name']} | {r['tier']} | {m['ministry']} | "
                 f"{m['effective_date']} | {s['jo']} | {s['hang']} | "
                 f"{s['ho']} | {s['mok']} | {'; '.join(r['warn'])} |")
    L += ["", "## 다음", "",
          "corpus_units.jsonl(T4) 과 corpus_units_law.jsonl(T1~T3) 을 합쳐",
          "최종 코퍼스를 만든다. unit_id 좌표계가 동일하므로 그대로 병합하면 된다."]
    Path("parse_law_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"-> corpus_units_law.jsonl ({len(all_units):,} units)")
    print("-> parse_law_report.md")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        u, st, mt = parse(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
        print("meta :", mt)
        print("stats:", st)
        print("units:", len(u), "| 중복:", len(u) - len({x['unit_id'] for x in u}))
        for x in u[:14]:
            print(f"  {x['level']:5} {x['unit_id']:34} {x['text'][:52]}")
    elif len(sys.argv) > 1:
        run(sys.argv[1:])
    else:
        print(__doc__)
