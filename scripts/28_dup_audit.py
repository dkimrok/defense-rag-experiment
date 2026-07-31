#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
28_dup_audit.py — 코퍼스 근사중복 감사

왜 필요한가
  22 의 커버리지 조작은 '문서/조 단위 제거'다. 그런데 한국 방위사업 법령
  코퍼스에는 문면이 거의 같은 보일러플레이트가 여러 문서에 흩어져 있다
  (계약특수조건 표준 7종의 '계약금액의 조정' 등). gold 문서를 지워도
  형제 조문이 남아 같은 답을 제공한다. 즉 '문서 제거 != 지식 제거'.
  이 상태로 q_status='none' 을 붙이면 거짓 라벨이 되고,
  '커버리지를 낮췄는데 성능이 안 떨어진다'는 잘못된 결론이 나온다.

무엇을 하는가
  (1) 전체 청크 쌍의 어휘 유사도로 근사중복 이웃을 찾는다.
      char n-gram TF-IDF 코사인. 보일러플레이트 탐지에는 의미유사도(BGE)보다
      어휘유사도가 정확하다. 의미유사도는 '같은 주제'를 잡지 '같은 문면'을
      잡지 않는다.
  (2) 코퍼스 수준 중복 통계(논문 구조적 발견 재료).
  (3) gold 청크별 중복 이웃 표(문항 설계 지침 재료).
      = 문항의 '도구 강도'. 형제가 많은 gold 로 만든 문항은
        커버리지 조작이 걸리지 않는 약한 도구다.

메모리
  HashingVectorizer 로 특징수를 2^20 으로 고정한다. 청크 수가 1만 미만이면
  배치 코사인으로 수 분 내 끝난다.

출력
  audit/dup_map.json    {chunk_id: [[neighbor_id, sim], ...]}  sim >= min-sim
  audit/dup_stats.json  코퍼스 수준 요약
  audit/gold_dup.tsv    gold 청크별 중복 현황(문항 설계용)

사용법
  py 28_dup_audit.py index question_final.jsonl --min-sim 0.6 --topn 10 --out audit
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

RE_AMEND = re.compile(r'<[^>]*>')          # <개정 2008.2.29, ...> 제거
RE_WS = re.compile(r'\s+')


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def norm_text(t: str) -> str:
    """어휘 유사도용 정규화. 개정이력·공백 제거."""
    t = RE_AMEND.sub(' ', t or '')
    t = t.replace('ㆍ', '·')
    return RE_WS.sub('', t)


def gold_chunk_ids(slot: dict) -> set:
    out = set()
    for g in slot.get("gold_evidence", []):
        parts = (g.get("unit_id") or "").split(":")
        if len(parts) >= 3:
            out.add(":".join(parts[:3]))
    return out


def main(index_dir: str, slots_path: str | None, min_sim: float,
         topn: int, out: str, batch: int = 256) -> int:
    import numpy as np
    from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
    from sklearn.preprocessing import normalize

    chunks = load(str(Path(index_dir) / "chunks.jsonl"))
    ids = [c["chunk_id"] for c in chunks]
    docs = [norm_text(c.get("text", "")) for c in chunks]
    n = len(chunks)
    print(f"청크 {n:,}개 벡터화 중(char 4-gram TF-IDF)...")

    hv = HashingVectorizer(analyzer="char", ngram_range=(4, 4),
                           n_features=2 ** 20, alternate_sign=False,
                           norm=None, lowercase=False)
    X = TfidfTransformer(sublinear_tf=True).fit_transform(hv.transform(docs))
    X = normalize(X)                     # 코사인 = 내적

    print(f"근사중복 탐색(min_sim={min_sim}, topn={topn})...")
    dup_map: dict[str, list] = {}
    max_sim = np.zeros(n, dtype=np.float32)
    XT = X.T.tocsc()
    for s in range(0, n, batch):
        e = min(s + batch, n)
        S = (X[s:e] @ XT).toarray()
        for i in range(e - s):
            S[i, s + i] = 0.0            # 자기 자신 제외
        for i in range(e - s):
            row = S[i]
            max_sim[s + i] = row.max() if row.size else 0.0
            k = min(topn, row.size)
            cand = np.argpartition(-row, k - 1)[:k]
            cand = cand[row[cand] >= min_sim]
            if cand.size:
                cand = cand[np.argsort(-row[cand])]
                dup_map[ids[s + i]] = [[ids[j], round(float(row[j]), 4)]
                                       for j in cand]
        print(f"  {e:,}/{n:,}", end="\r")
    print()

    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)
    (outd / "dup_map.json").write_text(
        json.dumps(dup_map, ensure_ascii=False), encoding="utf-8")

    # ---------------------------------------------- 코퍼스 수준 통계
    id2doc = {c["chunk_id"]: c.get("doc_name", "") for c in chunks}
    n_dup = len(dup_map)
    bands = Counter()
    for v in max_sim:
        if v >= 0.9: bands["0.9+"] += 1
        elif v >= 0.8: bands["0.8-0.9"] += 1
        elif v >= 0.7: bands["0.7-0.8"] += 1
        elif v >= 0.6: bands["0.6-0.7"] += 1
        else: bands["<0.6"] += 1

    pair = Counter()
    for cid, nbrs in dup_map.items():
        a = id2doc.get(cid, "")
        for nid, s in nbrs:
            b = id2doc.get(nid, "")
            if a and b and a != b:
                pair[tuple(sorted((a, b)))] += 1

    stats = dict(
        n_chunks=n, min_sim=min_sim, topn=topn,
        n_chunks_with_dup=n_dup,
        pct_chunks_with_dup=round(n_dup / n * 100, 1) if n else 0.0,
        max_sim_bands=dict(bands),
        top_doc_pairs=[dict(doc_a=a, doc_b=b, shared_chunks=c)
                       for (a, b), c in pair.most_common(25)],
    )

    # ---------------------------------------------- gold 청크 현황
    gold_rows = []
    if slots_path and Path(slots_path).exists():
        slots = load(slots_path)
        n_g = n_g_dup = 0
        for s in slots:
            if not s.get("answerable", True):
                continue
            for g in sorted(gold_chunk_ids(s)):
                nbrs = dup_map.get(g, [])
                ext = [x for x in nbrs if id2doc.get(x[0]) != id2doc.get(g)]
                n_g += 1
                n_g_dup += 1 if nbrs else 0
                gold_rows.append((s["qid"], g, id2doc.get(g, ""),
                                  len(nbrs), len(ext),
                                  nbrs[0][1] if nbrs else 0.0,
                                  ";".join(f"{i}({v})" for i, v in nbrs[:3])))
        stats["gold_chunks"] = n_g
        stats["gold_chunks_with_dup"] = n_g_dup
        stats["pct_gold_with_dup"] = round(n_g_dup / n_g * 100, 1) if n_g else 0.0

        with open(outd / "gold_dup.tsv", "w", encoding="utf-8") as f:
            f.write("qid\tgold_chunk\tdoc_name\tn_dup\tn_dup_other_doc\ttop_sim\ttop3\n")
            for r in gold_rows:
                f.write("\t".join(str(x) for x in r) + "\n")

    (outd / "dup_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------- 보고
    print(f"\n[코퍼스] 근사중복 보유 청크 {n_dup:,}/{n:,} "
          f"({stats['pct_chunks_with_dup']}%)")
    for b in ["0.9+", "0.8-0.9", "0.7-0.8", "0.6-0.7", "<0.6"]:
        print(f"   최대유사도 {b:9s} {bands.get(b,0):,}")
    if pair:
        print("\n[문서쌍] 근사중복 조문을 많이 공유하는 상위 10쌍")
        for (a, b), c in pair.most_common(10):
            print(f"   {c:4d}  {a}  <->  {b}")
    if gold_rows:
        print(f"\n[gold] 중복 보유 {stats['gold_chunks_with_dup']}/"
              f"{stats['gold_chunks']} ({stats['pct_gold_with_dup']}%)")
        weak = [r for r in gold_rows if r[4] > 0]
        print(f"   다른 문서에 형제가 있는 gold = {len(weak)}건 (약한 도구 후보)")
        for r in sorted(weak, key=lambda x: -x[5])[:10]:
            print(f"   {r[0]:14s} sim={r[5]:.3f} 타문서형제={r[4]}  {r[2]}")
    print(f"\n-> {outd}/dup_map.json, dup_stats.json, gold_dup.tsv")
    return 0


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        sys.exit(main(a[1], a[2] if len(a) > 2 and not a[2].startswith("-") else None,
                      float(opt("--min-sim", "0.6")), int(opt("--topn", "10")),
                      opt("--out", "audit"), int(opt("--batch", "256"))))
