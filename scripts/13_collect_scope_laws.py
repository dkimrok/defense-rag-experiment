#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
경계 확정분(to_collect) 추가 수집

11_finalize_scope.py 가 in_scope_to_collect 로 판정한 항목을 실제로 받아온다.
목록에는 두 종류가 섞여 있으므로 경로를 나눈다.

    T1 법률 / T2 대통령령 / T3 부령
        lawSearch  target=law    로 이름 -> MST 조회
        lawService target=eflaw  로 조문 본문 (조/항/호/목 구조)

    T4 행정규칙 (국방부 훈령, 산업부 고시 등)
        lawSearch  target=admrul 로 이름 -> 행정규칙일련번호 조회
        lawService target=admrul 로 본문

    UNK
        law 를 먼저 시도하고 실패하면 admrul 로 재시도

이름 매칭
    인용된 이름과 공식 명칭이 다를 수 있으므로(띄어쓰기·약칭·중점),
    검색 결과 중 nkey 완전일치를 우선하고, 없으면 유사도 최상위를 고른다.
    유사도가 임계 미만이면 미해결로 남기고 리포트에 표시한다.

사용법
    py 13_collect_scope_laws.py <OC> to_collect.json

출력
    raw/law_scope/{MST}.json
    raw/admrul_scope/{SEQ}.json
    collect_scope_report.md
"""

from __future__ import annotations

import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"
SLEEP = 0.35
MATCH_MIN = 0.82

OUT = Path("raw")
OC = ""


def nkey(s: str) -> str:
    s = re.sub(r'[ㆍ·・]', '', s)
    s = re.sub(r'\s+', '', s)
    return s.replace('(', '').replace(')', '')


def get(url: str, params: dict, retries: int = 3) -> dict | None:
    p = {"OC": OC, "type": "JSON", **params}
    for i in range(retries):
        try:
            r = requests.get(url, params=p, timeout=60)
            r.raise_for_status()
            time.sleep(SLEEP)
            return r.json()
        except Exception as e:                               # noqa: BLE001
            if i == retries - 1:
                print(f"      ! {params}: {type(e).__name__}")
                return None
            time.sleep(1.5 * (i + 1))
    return None


def unwrap(d: Any) -> dict:
    if not isinstance(d, dict):
        return {}
    for v in d.values():
        if isinstance(v, dict):
            return v
    return d


def as_list(x: Any) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def pick(cands: list[tuple[str, dict]], want: str) -> tuple[dict, float] | None:
    """이름 후보 중 가장 잘 맞는 것을 고른다."""
    k = nkey(want)
    best, score = None, 0.0
    for nm, item in cands:
        pk = nkey(nm)
        if pk == k:
            return item, 1.0
        r = SequenceMatcher(None, k, pk).ratio()
        if len(k) >= 6 and (k in pk or pk in k):
            r = max(r, 0.92)
        if r > score:
            best, score = item, r
    return (best, score) if best else None


# ---------------------------------------------------------------- 법령 경로

def resolve_law(name: str) -> tuple[dict, float] | None:
    d = get(SEARCH, {"target": "law", "query": name, "display": 50})
    if not d:
        return None
    body = unwrap(d)
    items = as_list(body.get("law"))
    cands = [(str(i.get("법령명한글") or i.get("법령명") or ""), i) for i in items]
    cands = [(n, i) for n, i in cands if n]
    return pick(cands, name) if cands else None


def fetch_law(mst: str) -> dict | None:
    return get(SERVICE, {"target": "eflaw", "MST": mst})


# ------------------------------------------------------------- 행정규칙 경로

def resolve_admrul(name: str) -> tuple[dict, float] | None:
    d = get(SEARCH, {"target": "admrul", "query": name, "search": 1,
                     "nw": 1, "display": 100})
    if not d:
        return None
    body = unwrap(d)
    items = as_list(body.get("admrul"))
    cands = [(str(i.get("행정규칙명") or ""), i) for i in items]
    cands = [(n, i) for n, i in cands if n]
    return pick(cands, name) if cands else None


def fetch_admrul(seq: str) -> dict | None:
    return get(SERVICE, {"target": "admrul", "ID": seq})


# ---------------------------------------------------------------- 메인

def main(to_collect_path: str) -> None:
    items = json.loads(Path(to_collect_path).read_text(encoding="utf-8"))
    items.sort(key=lambda x: -x.get("citations", 0))
    print(f"수집 대상 {len(items)}종\n")

    rows: list[dict] = []
    (OUT / "law_scope").mkdir(parents=True, exist_ok=True)
    (OUT / "admrul_scope").mkdir(parents=True, exist_ok=True)

    for it in items:
        name = it["name"]
        tier = it.get("tier", "UNK")
        cit = it.get("citations", 0)
        print(f"  [{cit:3}회] {name}  ({tier})")

        routes = (["law"] if tier.startswith(("T1", "T2", "T3"))
                  else ["admrul"] if tier.startswith("T4")
                  else ["law", "admrul"])

        rec = dict(name=name, tier=tier, citations=cit,
                   route="", official="", key="", score=0.0,
                   status="not_found", path="")

        for route in routes:
            if route == "law":
                r = resolve_law(name)
                if not r or r[1] < MATCH_MIN:
                    continue
                item, sc = r
                mst = str(item.get("법령일련번호") or "")
                official = str(item.get("법령명한글") or item.get("법령명") or "")
                if not mst:
                    continue
                f = OUT / "law_scope" / f"{mst}.json"
                if not f.exists():
                    b = fetch_law(mst)
                    if not b:
                        continue
                    f.write_text(json.dumps(b, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
                body = unwrap(json.loads(f.read_text(encoding="utf-8")))
                njo = len(as_list((body.get("조문") or {}).get("조문단위")))
                rec.update(route="law", official=official, key=mst, score=round(sc, 2),
                           status="ok", path=str(f), n_units=njo)
                print(f"      -> 법령 MST={mst} 조문 {njo}개 (유사도 {sc:.2f})")
                break

            r = resolve_admrul(name)
            if not r or r[1] < MATCH_MIN:
                continue
            item, sc = r
            seq = str(item.get("행정규칙일련번호") or "")
            official = str(item.get("행정규칙명") or "")
            if not seq:
                continue
            f = OUT / "admrul_scope" / f"{seq}.json"
            if not f.exists():
                b = fetch_admrul(seq)
                if not b:
                    continue
                f.write_text(json.dumps(b, ensure_ascii=False, indent=1),
                             encoding="utf-8")
            body = unwrap(json.loads(f.read_text(encoding="utf-8")))
            njo = len(as_list(body.get("조문내용")))
            rec.update(route="admrul", official=official, key=seq,
                       score=round(sc, 2), status="ok", path=str(f), n_units=njo)
            print(f"      -> 행정규칙 seq={seq} 조문 {njo}줄 (유사도 {sc:.2f})")
            break

        if rec["status"] != "ok":
            print("      -> 미해결")
        rows.append(rec)

    ok = [r for r in rows if r["status"] == "ok"]
    ng = [r for r in rows if r["status"] != "ok"]
    low = [r for r in ok if r["score"] < 0.95]

    L = ["# 경계 확정분 추가 수집 결과", "",
         f"- 대상 {len(rows)}종 / 성공 {len(ok)} / 미해결 {len(ng)}", "",
         "## 수집 성공", "",
         "| 인용 | 요청 이름 | 공식 명칭 | 경로 | 키 | 단위수 | 유사도 |",
         "|---|---|---|---|---|---|---|"]
    for r in sorted(ok, key=lambda x: -x["citations"]):
        L.append(f"| {r['citations']} | {r['name']} | {r['official']} | "
                 f"{r['route']} | {r['key']} | {r.get('n_units','-')} | {r['score']} |")

    if low:
        L += ["", "## 이름 매칭 확인 필요 (유사도 0.95 미만)", "",
              "요청 이름과 공식 명칭이 다르다. 같은 문서가 맞는지 눈으로 확인한다.", "",
              "| 요청 | 매칭된 공식명 | 유사도 |", "|---|---|---|"]
        for r in low:
            L.append(f"| {r['name']} | {r['official']} | {r['score']} |")

    if ng:
        L += ["", "## 미해결", "",
              "검색에서 임계 이상 후보를 찾지 못했다. 이름을 확인하거나",
              "11_finalize_scope.py 의 CANONICAL 에 정식명칭을 추가한 뒤 재시도한다.", "",
              "| 인용 | 이름 | 위계 |", "|---|---|---|"]
        for r in sorted(ng, key=lambda x: -x["citations"]):
            L.append(f"| {r['citations']} | {r['name']} | {r['tier']} |")

    L += ["", "## 다음", "",
          "1. 미해결·매칭확인 항목을 정리한다.",
          "2. raw/admrul_scope 를 07_parse_admrul_v2.py 로 파싱해 corpus_units 에 합친다.",
          "3. raw/law_scope 는 법령용 파서(조문단위 → 조/항/호/목)로 별도 변환한다.",
          "4. 코퍼스 확정 후 L3 후보의 gold evidence 가 실제로 채워지는지 재검증한다."]

    Path("collect_scope_report.md").write_text("\n".join(L), encoding="utf-8")
    Path("collect_scope_result.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n성공 {len(ok)} / 미해결 {len(ng)} / 매칭확인 {len(low)}")
    print("-> collect_scope_report.md, collect_scope_result.json")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        OC = sys.argv[1].strip()
        main(sys.argv[2])
