#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
29_status_content.py — q_status 내용 기반 재계산

문제
  현행 q_status 는 'gold unit_id 가 살아있는가'로 판정한다(단위 기준).
  그러나 근사중복 형제가 남아 같은 답을 제공하면, 라벨은 none 인데
  지식은 살아있다. 실측 확인 사례:
    DAPA-L4-002  gold=방위사업관리규정 제155조 제거 -> 국방전력발전업무훈령
                 「전시 전력발전업무 방침」이 동일 내용 보유, 검색 1위, 답 동일
    DAPA-L4-011  gold=일반무기체계 연구개발 계약특수조건 표준 제거
                 -> 계약특수조건 표준 형제 5종이 동일 조항 보유, 답 동일

해법
  단위 기준 라벨을 버리지 않고 내용 기준 라벨을 병기한다.
    q_status_unit     현행(gold unit 잔존)
    q_status_content  full / partial / surrogate / none / oos
      surrogate = gold 는 전멸했으나 '대체 청크'가 살아있음
  대체 청크 판정(두 조건 모두 충족):
    (1) gold 와 어휘 근사중복  (28 의 dup_map, sim >= --sim)
    (2) 정답 내용을 담고 있음  (정규화 부분일치 또는 토큰 포함률 >= --tok)
  (1) 없이 (2) 만 쓰면 '10근무일' 같은 일반 표현이 무관 문서에서
  걸려 대량 오탐이 난다. (2) 없이 (1) 만 쓰면 같은 조항 형식이되
  값이 다른 형제가 걸린다. 둘의 논리곱이 필요하다.

부산물
  instrument_strength: 전체 코퍼스에서 그 문항의 대체 청크 수.
  0 이면 gold 제거가 곧 지식 제거인 '강한 도구'.
  나머지 85문항 작성 시 이 값이 0 인 gold 를 고르면 된다.

출력
  status_content.json  {condition: {qid: {...}}}
  콘솔                 단위기준 vs 내용기준 불일치 요약(논문 수치)

사용법
  py 29_status_content.py index question_final.jsonl audit/dup_map.json \\
      --variants cov_core,cov_periph,cov_random --sim 0.6 --tok 0.8 --out .
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

RE_AMEND = re.compile(r'<[^>]*>')
RE_WS = re.compile(r'\s+')
RE_TOK = re.compile(r'[가-힣]{2,}|[A-Za-z]{2,}|\d+')
CIRC = {c: str(i + 1) for i, c in enumerate('①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮')}


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def norm(t: str) -> str:
    t = RE_AMEND.sub(' ', t or '')
    for k, v in CIRC.items():
        t = t.replace(k, v)
    t = t.replace('ㆍ', '·').replace('，', ',')
    return RE_WS.sub('', t)


def answer_keys(slot: dict) -> list[str]:
    ks = [slot.get("answer_short") or ""]
    ks += list(slot.get("answer_alternatives") or [])
    return [k for k in ks if k and k.strip()]


def covers(ans: str, text: str, tok_ratio: float) -> bool:
    """정답이 이 청크에 담겨 있는가."""
    na, nt = norm(ans), norm(text)
    if not na:
        return False
    if na in nt:
        return True
    toks = RE_TOK.findall(ans)
    if not toks:
        return False
    hit = sum(1 for t in toks if norm(t) in nt)
    return hit / len(toks) >= tok_ratio


def gold_chunk_ids(slot: dict) -> set:
    out = set()
    for g in slot.get("gold_evidence", []):
        parts = (g.get("unit_id") or "").split(":")
        if len(parts) >= 3:
            out.add(":".join(parts[:3]))
    return out


def main(index_dir: str, slots_path: str, dupmap_path: str,
         variants: list[str], sim_th: float, tok_th: float, out: str) -> int:
    chunks = {c["chunk_id"]: c for c in load(str(Path(index_dir) / "chunks.jsonl"))}
    slots = load(slots_path)
    dup_map = json.loads(Path(dupmap_path).read_text(encoding="utf-8"))

    # 문항별 '대체 후보' 를 코퍼스 전체 기준으로 1회 계산
    cand: dict[str, dict] = {}
    for s in slots:
        qid = s["qid"]
        if not s.get("answerable", True):
            cand[qid] = dict(gold=set(), surro=set())
            continue
        gold = gold_chunk_ids(s)
        keys = answer_keys(s)
        surro = set()
        for g in gold:
            for nid, v in dup_map.get(g, []):
                if v < sim_th or nid in gold:
                    continue
                c = chunks.get(nid)
                if c and any(covers(k, c.get("text", ""), tok_th) for k in keys):
                    surro.add(nid)
        cand[qid] = dict(gold=gold, surro=surro)

    strong = sum(1 for s in slots
                 if s.get("answerable", True) and not cand[s["qid"]]["surro"])
    ansable = sum(1 for s in slots if s.get("answerable", True))
    print(f"[도구 강도] 대체 청크 0건인 문항 {strong}/{ansable} "
          f"({strong/ansable*100:.0f}%) — 나머지는 gold 제거로 지식이 안 지워짐\n")

    # 변형별 재계산
    result: dict[str, dict] = {}
    flip = Counter()
    files = []
    for vd in variants:
        files += sorted(Path(vd).glob("corpus_cov*_*.jsonl"))
    if not files:
        print("변형 코퍼스를 찾지 못했습니다.")
        return 1

    for f in files:
        alive = {json.loads(l)["unit_id"]
                 for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}
        alive_ch = {c for c in chunks if c in alive}
        m = re.search(r'cov(\d+)_(\w+?)_(\w+)\.jsonl', f.name)
        cond = f"cov{int(m.group(1))}_{m.group(2)}_{m.group(3)}" if m else f.stem
        per = {}
        for s in slots:
            qid = s["qid"]
            g, sur = cand[qid]["gold"], cand[qid]["surro"]
            if not s.get("answerable", True):
                per[qid] = dict(q_status_unit="oos", q_status_content="oos",
                                n_surrogate_alive=0, surrogate_alive=[])
                continue
            kept = g & alive_ch
            su = "full" if kept == g and g else ("partial" if kept else "none")
            sa = sorted(sur & alive_ch)
            if kept == g and g:
                sc = "full"
            elif kept:
                sc = "partial"
            elif sa:
                sc = "surrogate"
            else:
                sc = "none"
            per[qid] = dict(q_status_unit=su, q_status_content=sc,
                            n_surrogate_alive=len(sa), surrogate_alive=sa)
            if su != sc:
                flip[(su, sc)] += 1
        result[cond] = per
        n_sur = sum(1 for v in per.values() if v["q_status_content"] == "surrogate")
        print(f"{cond:26s} 살아있는청크 {len(alive_ch):6,} | surrogate {n_sur}")

    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "status_content.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    tot = sum(len(v) for v in result.values())
    nflip = sum(flip.values())
    print(f"\n[불일치] 전체 (문항×조건) {tot:,}건 중 라벨 변경 {nflip:,}건 "
          f"({nflip/tot*100:.1f}%)")
    for (a, b), c in flip.most_common():
        print(f"   {a:8s} -> {b:10s} {c:,}")
    print(f"\n-> {out}/status_content.json")
    return 0


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 4:
        print(__doc__)
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        sys.exit(main(a[1], a[2], a[3],
                      opt("--variants", "cov_core").split(","),
                      float(opt("--sim", "0.6")), float(opt("--tok", "0.8")),
                      opt("--out", ".")))
