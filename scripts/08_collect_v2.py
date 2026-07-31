#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
방위사업 획득절차 코퍼스 수집기 v2

v1 대비 수정 사항 (실응답으로 확인)
  - 응답 래퍼 키 확정
        lawSearch  target=admrul -> AdmRulSearch.admrul[]
        lawService target=admrul -> AdmRulService.{행정규칙기본정보,조문내용,부칙,별표}
        lawService target=eflaw  -> 법령.{기본정보,조문.조문단위}
        lawService target=thdCmp knd=1 -> ThdCmpLawXService
                              knd=2 -> LspttnThdCmpLawXService
  - org(소관부처) 코드 확정: 방위사업청 = 1690000
        검색어 매칭 대신 소관부처 기준으로 전수 수집한다.
  - thdCmp 는 관련삼단비교목록의 상세링크에 prslId(시행령ID)·prmlId(시행규칙ID)가
    들어 있다. 공식 가이드 표에 없는 파라미터이며, 이것을 지정해야
    방위사업법 + 시행령 + 시행규칙 조합을 얻을 수 있다.

특징
  - 재개 가능: 이미 받은 파일은 건너뛴다. 중간에 끊겨도 다시 돌리면 이어서 받는다.
  - 단계 선택 실행: py 08_collect_v2.py <OC> --phase 3
  - 마지막에 inventory.md 를 생성한다. 문항 100개 배분의 근거 자료다.

사용법
    py 08_collect_v2.py YOUROC            # 전 단계
    py 08_collect_v2.py YOUROC --phase 1  # 1단계만
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import requests

SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "http://www.law.go.kr/DRF/lawService.do"

DAPA_ORG = "1690000"          # 방위사업청 소관부처코드 (실응답에서 확인)
SLEEP = 0.35

# 연혁 본문까지 받을 규정. 전부 받으면 호출량이 과도하므로 선별한다.
# 개정 이력 본문까지 받을 규정.
# L4 문항이 한 규정에 몰리면 커버리지 조작에서 그 규정을 제거할 때
# L4 전체가 한꺼번에 죽어 수준 효과와 문서 효과가 교란된다.
# 그래서 버전이 많은 규정 여러 개로 분산한다.
HISTORY_TARGETS = [
    "방위사업관리규정",                          # 65버전 / 229조
    "군수품조달관리규정",                        # 25버전 / 194조
    "방산원가대상물자의 원가계산에 관한 시행세칙",  # 27버전
    "일반무기체계 연구개발 계약특수조건 표준",      # 26버전
]

# T1~T3 법령 (MST는 스모크테스트에서 확인)
LAWS = {
    "방위사업법": "281867",
    "방위사업법 시행령": "287575",
    "방위사업법 시행규칙": "287869",
}

EXPC_QUERIES = ["방위사업법", "방위사업청", "방산", "무기체계", "군수품",
                "방위력개선", "국방규격", "절충교역", "방위산업", "국방조달"]

OUT = Path("raw")
OC = ""


# --------------------------------------------------------------- 공통

def get(url: str, params: dict, retries: int = 3) -> dict | None:
    p = {"OC": OC, "type": "JSON", **params}
    for attempt in range(retries):
        try:
            r = requests.get(url, params=p, timeout=60)
            r.raise_for_status()
            time.sleep(SLEEP)
            return r.json()
        except Exception as e:                               # noqa: BLE001
            if attempt == retries - 1:
                print(f"    ! 실패 {params}: {type(e).__name__}: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def unwrap(d: dict) -> dict:
    """최상위 서비스 래퍼를 한 겹 벗긴다."""
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


def save(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"    -> {path} ({len(rows)}건)")


def paged(url: str, params: dict, item_key: str,
          wrapper_hint: str | None = None) -> Iterator[dict]:
    """display=100 페이지네이션."""
    page = 1
    while True:
        d = get(url, {**params, "display": 100, "page": page})
        if not d:
            return
        body = d.get(wrapper_hint) if wrapper_hint else unwrap(d)
        if not isinstance(body, dict):
            body = unwrap(d)
        items = as_list(body.get(item_key))
        if not items:
            return
        yield from items
        try:
            total = int(body.get("totalCnt", 0))
        except (TypeError, ValueError):
            total = 0
        if page * 100 >= total:
            return
        page += 1


# --------------------------------------------------------------- 1단계

def phase1_list_current() -> list[dict]:
    print("[1] 방위사업청 소관 행정규칙 현행 목록 (org=%s, nw=1)" % DAPA_ORG)
    rows = list(paged(SEARCH, {"target": "admrul", "org": DAPA_ORG, "nw": 1,
                               "sort": "efdes"}, "admrul", "AdmRulSearch"))
    if not rows:
        print("    org 파라미터로 결과가 없습니다. 검색어 방식으로 대체합니다.")
        seen, rows = set(), []
        for q in ["방위사업", "방위", "국방", "군수", "계약", "규정"]:
            for it in paged(SEARCH, {"target": "admrul", "query": q, "search": 1,
                                     "nw": 1}, "admrul", "AdmRulSearch"):
                if DAPA_ORG not in str(it.get("소관부처명", "")) and \
                   "방위사업청" not in str(it.get("소관부처명", "")):
                    continue
                k = str(it.get("행정규칙일련번호"))
                if k not in seen:
                    seen.add(k)
                    rows.append(it)
    save_jsonl(OUT / "admrul_list_current.jsonl", rows)
    kinds: dict[str, int] = {}
    for r in rows:
        k = str(r.get("행정규칙종류", "?"))
        kinds[k] = kinds.get(k, 0) + 1
    print("    종류별:", kinds)
    return rows


# --------------------------------------------------------------- 2단계

def phase2_list_history() -> list[dict]:
    print("[2] 행정규칙 연혁 포함 목록 (nw=2)")
    rows = list(paged(SEARCH, {"target": "admrul", "org": DAPA_ORG, "nw": 2,
                               "sort": "efdes"}, "admrul", "AdmRulSearch"))
    if not rows:
        seen, rows = set(), []
        for q in HISTORY_TARGETS + ["방위사업"]:
            for it in paged(SEARCH, {"target": "admrul", "query": q, "search": 1,
                                     "nw": 2}, "admrul", "AdmRulSearch"):
                k = str(it.get("행정규칙일련번호"))
                if k not in seen:
                    seen.add(k)
                    rows.append(it)
    save_jsonl(OUT / "admrul_list_history.jsonl", rows)

    byname: dict[str, int] = {}
    for r in rows:
        n = str(r.get("행정규칙명", "?")).strip()
        byname[n] = byname.get(n, 0) + 1
    multi = {k: v for k, v in byname.items() if v >= 5}
    print(f"    규정 {len(byname)}종 / 버전 5개 이상 보유 {len(multi)}종")
    for k, v in sorted(multi.items(), key=lambda x: -x[1])[:10]:
        print(f"      {v:3}버전  {k}")
    return rows


# --------------------------------------------------------------- 3·4단계

def _fetch_bodies(rows: list[dict], subdir: str, label: str) -> None:
    d = OUT / subdir
    d.mkdir(parents=True, exist_ok=True)
    todo = [r for r in rows
            if not (d / f"{r.get('행정규칙일련번호')}.json").exists()]
    print(f"    대상 {len(rows)}건 중 미수집 {len(todo)}건")
    for i, r in enumerate(todo, 1):
        seq = str(r.get("행정규칙일련번호"))
        b = get(SERVICE, {"target": "admrul", "ID": seq})
        if b:
            save(d / f"{seq}.json", b)
        if i % 20 == 0 or i == len(todo):
            print(f"      {i}/{len(todo)}")
    print(f"    -> {d}/ ({len(list(d.glob('*.json')))} 파일)")


def phase3_bodies_current(rows: list[dict]) -> None:
    print("[3] 현행 행정규칙 본문")
    _fetch_bodies(rows, "admrul_body_current", "현행")


def phase4_bodies_history(rows: list[dict]) -> None:
    """이름이 아니라 행정규칙ID 로 버전을 모은다.

    같은 규정이 시기별로 다른 이름을 쓴다.
      일반무기체계 연구개발 계약특수조건 표준 <-> 일반무기체계 연구개발 표준계약특수조건
      함정건조 계약특수조건 표준(...) <-> 함정건조 표준계약특수조건(...)
    이름 정확일치로 거르면 옛 이름을 쓰던 버전이 통째로 누락된다.
    행정규칙ID 는 개명과 무관하게 유지되므로 이것을 기준으로 삼는다.
    """
    print(f"[4] 연혁 본문 (대상: {', '.join(HISTORY_TARGETS)})")
    ids = {str(r.get("행정규칙ID")) for r in rows
           if str(r.get("행정규칙명", "")).strip() in HISTORY_TARGETS
           and r.get("행정규칙ID")}
    tgt = [r for r in rows if str(r.get("행정규칙ID")) in ids]
    print(f"    행정규칙ID {len(ids)}개로 확장 → 버전 {len(tgt)}건")
    byname: dict[str, int] = {}
    for r in tgt:
        n = str(r.get("행정규칙명", "")).strip()
        byname[n] = byname.get(n, 0) + 1
    for n, cnt in sorted(byname.items(), key=lambda x: -x[1]):
        print(f"      {cnt:3}건  {n}")
    _fetch_bodies(tgt, "admrul_body_history", "연혁")


# --------------------------------------------------------------- 5단계

def phase5_laws() -> None:
    print("[5] 법령 본문 (target=eflaw)")
    d = OUT / "law"
    for name, mst in LAWS.items():
        f = d / f"{mst}.json"
        if f.exists():
            print(f"    건너뜀 {name}")
            continue
        r = get(SERVICE, {"target": "eflaw", "MST": mst})
        if not r:
            continue
        save(f, r)
        body = unwrap(r)
        jos = as_list((body.get("조문") or {}).get("조문단위"))
        info = body.get("기본정보", {})
        print(f"    {name}: 조문 {len(jos)}개 / 시행 {info.get('시행일자')}")


# --------------------------------------------------------------- 6단계

def phase6_thdcmp() -> None:
    print("[6] 3단비교 체인 (thdCmp)")
    d = OUT / "thdcmp"
    mst = LAWS["방위사업법"]

    root = get(SERVICE, {"target": "thdCmp", "MST": mst, "knd": 1})
    if not root:
        return
    save(d / "knd1_root.json", root)
    body = unwrap(root)
    combos = as_list((body.get("관련삼단비교목록") or {}).get("삼단비교"))
    print(f"    관련 삼단비교 조합 {len(combos)}개")

    for c in combos:
        link = str(c.get("삼단비교목록상세링크", ""))
        q = parse_qs(urlparse(link).query)
        law_id = (q.get("ID") or [""])[0]
        prsl = (q.get("prslId") or ["0"])[0]
        prml = (q.get("prmlId") or ["0"])[0]
        name = str(c.get("목록명", ""))[:60]
        tag = f"knd1_{law_id}_{prsl}_{prml}"
        f = d / f"{tag}.json"
        if f.exists():
            continue
        # prslId/prmlId 는 가이드 표에 없지만 상세링크에서 확인된 파라미터다
        r = get(SERVICE, {"target": "thdCmp", "ID": law_id, "knd": 1,
                          "prslId": prsl, "prmlId": prml})
        if not r:
            continue
        save(f, r)
        b = unwrap(r)
        arts = as_list((b.get("인용조문삼단비교") or {}).get("법률조문"))
        txt = json.dumps(r, ensure_ascii=False)
        print(f"    {name}\n        법률조문 {len(arts)}개 / "
              f"시행령조문 {'O' if '시행령조문' in txt else 'X'} / "
              f"위임행정규칙 {'O' if '위임행정규칙' in txt else 'X'}")

    r2 = get(SERVICE, {"target": "thdCmp", "MST": mst, "knd": 2})
    if r2:
        save(d / "knd2_root.json", r2)
        b2 = unwrap(r2)
        arts = as_list((b2.get("위임조문삼단비교") or {}).get("법률조문"))
        print(f"    knd=2 위임조문 {len(arts)}개")


# --------------------------------------------------------------- 7단계

def phase7_expc() -> None:
    print("[7] 법령해석례")
    seen: dict[str, dict] = {}
    for q in EXPC_QUERIES:
        n0 = len(seen)
        for it in paged(SEARCH, {"target": "expc", "query": q, "search": 2},
                        "expc"):
            k = str(it.get("법령해석례일련번호"))
            if k not in seen:
                it["_query"] = q
                seen[k] = it
        print(f"    {q:8} 누적 {len(seen)}건 (신규 {len(seen)-n0})")
    rows = list(seen.values())
    save_jsonl(OUT / "expc_list.jsonl", rows)

    # 본문 조회. lawService target=expc 의 파라미터는 가이드 미확인이므로
    # admrul/prec 와 동일한 ID 방식을 시도하고, 실패해도 진행한다.
    d = OUT / "expc_body"
    d.mkdir(parents=True, exist_ok=True)
    ok = 0
    for i, r in enumerate(rows, 1):
        seq = str(r.get("법령해석례일련번호"))
        f = d / f"{seq}.json"
        if f.exists():
            ok += 1
            continue
        b = get(SERVICE, {"target": "expc", "ID": seq}, retries=1)
        if b and isinstance(b, dict):
            save(f, b)
            ok += 1
        if i % 25 == 0:
            print(f"      본문 {i}/{len(rows)}")
    print(f"    본문 확보 {ok}/{len(rows)}건")
    if ok == 0:
        print("    ! 본문 조회 실패. 목록의 '법령해석례상세링크'로 대체 수집 필요")


# --------------------------------------------------------------- 8단계

def phase8_inventory() -> None:
    print("[8] 인벤토리 리포트")

    def load_jsonl(p: Path) -> list[dict]:
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    cur = load_jsonl(OUT / "admrul_list_current.jsonl")
    his = load_jsonl(OUT / "admrul_list_history.jsonl")
    exp = load_jsonl(OUT / "expc_list.jsonl")

    kinds: dict[str, int] = {}
    for r in cur:
        k = str(r.get("행정규칙종류", "?"))
        kinds[k] = kinds.get(k, 0) + 1

    byname: dict[str, list[dict]] = {}
    for r in his:
        byname.setdefault(str(r.get("행정규칙명", "?")).strip(), []).append(r)

    L = ["# 방위사업 코퍼스 인벤토리", "",
         "## 1. 행정규칙 (T4)", "",
         f"- 현행 {len(cur)}건", ""]
    L.append("| 종류 | 건수 |")
    L.append("|---|---|")
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        L.append(f"| {k} | {v} |")

    L += ["", "## 2. 개정 이력 (버전충돌 조작 재료)", "",
          f"- 연혁 포함 총 {len(his)}건 / 규정 {len(byname)}종", "",
          "| 규정명 | 버전수 | 최신 시행일 | 최초 시행일 |", "|---|---|---|---|"]
    for n, rs in sorted(byname.items(), key=lambda x: -len(x[1]))[:25]:
        ds = sorted(str(r.get("시행일자", "")) for r in rs)
        L.append(f"| {n} | {len(rs)} | {ds[-1]} | {ds[0]} |")

    L += ["", "## 3. 법령 (T1~T3)", "", "| 법령 | MST | 조문수 |", "|---|---|---|"]
    for name, mst in LAWS.items():
        f = OUT / "law" / f"{mst}.json"
        n = "-"
        if f.exists():
            b = unwrap(json.loads(f.read_text(encoding="utf-8")))
            n = str(len(as_list((b.get("조문") or {}).get("조문단위"))))
        L.append(f"| {name} | {mst} | {n} |")

    L += ["", "## 4. 법령해석례 (문항 원천 A)", "",
          f"- 중복 제거 후 {len(exp)}건", ""]
    orgs: dict[str, int] = {}
    for r in exp:
        o = str(r.get("질의기관명", "?"))
        orgs[o] = orgs.get(o, 0) + 1
    L.append("| 질의기관 | 건수 |")
    L.append("|---|---|")
    for k, v in sorted(orgs.items(), key=lambda x: -x[1])[:15]:
        L.append(f"| {k} | {v} |")

    L += ["", "## 5. 다음 단계 판단 근거", "",
          "- 문항 100개 배분: 위 규정 수와 개정 버전 수를 보고 L1~L4 비율을 확정한다.",
          "- L4(적용판단) 문항은 버전수가 많은 규정에서 우선 생성한다.",
          "- 법령해석례 건수가 30건 미만이면 원천 A 비중을 낮추고",
          "  개정이력 기반 문항 비중을 높인다."]

    Path("inventory.md").write_text("\n".join(L), encoding="utf-8")
    print("    -> inventory.md")


# --------------------------------------------------------------- main

def main() -> None:
    global OC
    if len(sys.argv) < 2:
        sys.exit("사용법: py 08_collect_v2.py <OC값> [--phase N]")
    OC = sys.argv[1].strip()
    phase = None
    if "--phase" in sys.argv:
        phase = int(sys.argv[sys.argv.index("--phase") + 1])

    cur: list[dict] = []
    his: list[dict] = []

    def want(n: int) -> bool:
        return phase is None or phase == n

    if want(1):
        cur = phase1_list_current()
    if want(2):
        his = phase2_list_history()
    if want(3):
        if not cur:
            cur = [json.loads(x) for x in
                   (OUT / "admrul_list_current.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        phase3_bodies_current(cur)
    if want(4):
        if not his:
            his = [json.loads(x) for x in
                   (OUT / "admrul_list_history.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        phase4_bodies_history(his)
    if want(5):
        phase5_laws()
    if want(6):
        phase6_thdcmp()
    if want(7):
        phase7_expc()
    if want(8) or phase is None:
        phase8_inventory()

    print("\n완료. 다음:")
    print("  py 07_parse_admrul_v2.py raw/admrul_body_current  (디렉터리 지원은 추가 예정)")
    print("  inventory.md 를 보고 문항 100개 배분을 확정합니다.")


if __name__ == "__main__":
    main()
