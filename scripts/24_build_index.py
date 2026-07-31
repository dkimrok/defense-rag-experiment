#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
인덱스 빌더 — 원본 코퍼스 임베딩 + BM25 인덱스 (한 번만, 캐시)

검색 청크는 '조 전체'다. 조 unit 하나에 그 조의 항/호/목 본문을 조립해
붙인 것을 하나의 검색 문서로 삼는다. gold evidence 가 조 단위이므로
recall@k 를 '정답 조가 top-k 에 들어왔는가'로 깔끔하게 측정할 수 있다.

두 인덱스를 만든다.
  (1) BGE-m3 임베딩 — 의미 검색용. 조문 텍스트를 밀집 벡터로.
  (2) BM25 — 정확 매칭용. '제46조의2', '착수금' 같은 조번호·고유용어를
             벡터가 놓치는 것을 보완한다. 법률 RAG 의 표준 조합.

임베딩은 코퍼스 전체에 대해 한 번만 계산해 저장한다. 변형 코퍼스(커버리지
조작 결과)는 '어떤 조가 남았는가'만 다르므로, 검색 시 chunk_id 로 필터링만
하면 된다. 8단계 × 여러 전략을 돌려도 임베딩은 재계산하지 않는다.

의존성
    pip install sentence-transformers rank-bm25
    (BGE-m3 는 최초 실행 시 자동 다운로드. 오프라인이면 미리 받아둔다.)
    설치 안 돼 있으면 --dry-run 으로 청크 구성만 확인할 수 있다.

출력 (index_dir/)
    chunks.jsonl        검색 문서들 {chunk_id, doc_id, jo_code, tier, text, ...}
    embeddings.npy      (N, D) float32  BGE-m3 벡터
    bm25.pkl            BM25 인덱스 (토큰화된 코퍼스 포함)
    index_meta.json     모델명·차원·청크수 등

사용법
    py 24_build_index.py corpus_final.jsonl --out index
    py 24_build_index.py corpus_final.jsonl --out index --dry-run   # 청크만
    py 24_build_index.py corpus_final.jsonl --out index --model BAAI/bge-m3
"""

from __future__ import annotations

import json
import pickle
import re
import sys
from pathlib import Path

DEFAULT_MODEL = "BAAI/bge-m3"


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------- 청크 구성


# ---------------------------------------------------------------- 조 전문 조립

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


def build_chunks(corpus: list[dict]) -> list[dict]:
    """조 unit 마다 하위 항/호/목을 조립해 '조 전체' 검색 문서를 만든다."""
    by_id = {u["unit_id"]: u for u in corpus}
    # 조별로 하위 unit 을 모은다 (unit_id prefix 매칭)
    ids_sorted = sorted(by_id)
    chunks = []
    for u in corpus:
        if u.get("level") != "jo":
            continue
        if u.get("deleted"):
            continue                       # 삭제된 조는 검색 대상에서 제외
        base = u["unit_id"]                 # 예: law:010107:004602
        parts = [u.get("text", "").strip()]
        for uid in ids_sorted:
            if uid.startswith(base + ":"):
                t = by_id[uid].get("text", "").strip()
                if t:
                    parts.append(t)
        full = dedup_parts(parts)
        chunks.append(dict(
            chunk_id=base,
            doc_id=u.get("doc_id", ""),
            doc_name=u.get("doc_name", ""),
            jo_code=base.rsplit(":", 1)[-1],
            tier=u.get("tier", ""),
            jo_title=u.get("jo_title", ""),
            text=full,
            char_len=len(full)))
    return chunks


# ---------------------------------------------------------------- BM25 토큰화

def tokenize_ko(text: str) -> list[str]:
    """형태소 분석기 없이 쓰는 경량 토크나이저.

    한국어는 공백 분절 + 2~4그램 음절을 섞어, 조사가 붙어도 부분 매칭이
    되도록 한다. '제46조의2', '착수금' 같은 토큰이 살아있어야 BM25 가
    제 역할을 한다. 형태소 분석기(mecab 등)를 쓸 수 있으면 더 좋지만,
    설치 부담 없이 재현되도록 규칙 기반으로 둔다.
    """
    text = text.lower()
    # 조 번호 패턴은 통째로 토큰화
    jo_tokens = re.findall(r'제\s*\d+\s*조(?:의\s*\d+)?', text)
    jo_tokens = [re.sub(r'\s+', '', t) for t in jo_tokens]
    # 일반 단어 (공백/기호 분절)
    words = re.findall(r'[가-힣]+|[a-z]+|\d+', text)
    grams = []
    for w in words:
        if len(w) <= 4:
            grams.append(w)
        else:
            grams.append(w)
            for i in range(len(w) - 1):     # 2그램
                grams.append(w[i:i + 2])
    return jo_tokens + grams


# ---------------------------------------------------------------- 메인

def main(corpus_path: str, out: str, model_name: str, dry: bool) -> None:
    corpus = load(corpus_path)
    chunks = build_chunks(corpus)
    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)

    with open(outd / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"검색 청크 {len(chunks):,}개 (조 전체 단위)")
    print(f"  평균 {sum(c['char_len'] for c in chunks)//max(len(chunks),1):,}자 "
          f"/ 최대 {max((c['char_len'] for c in chunks), default=0):,}자")

    # BM25 (경량 의존성이라 dry-run 에서도 시도)
    try:
        from rank_bm25 import BM25Okapi
        tokenized = [tokenize_ko(c["text"]) for c in chunks]
        bm25 = BM25Okapi(tokenized)
        with open(outd / "bm25.pkl", "wb") as f:
            pickle.dump(dict(bm25=bm25, chunk_ids=[c["chunk_id"] for c in chunks]), f)
        print(f"BM25 인덱스 저장 (평균 토큰 "
              f"{sum(len(t) for t in tokenized)//max(len(tokenized),1)}개)")
    except ImportError:
        print("  (rank-bm25 미설치 — BM25 건너뜀. pip install rank-bm25)")

    if dry:
        print("\n--dry-run: 임베딩은 건너뛴다. 청크 구성만 확인했다.")
        _write_meta(outd, model_name, len(chunks), 0, dry=True)
        return

    # BGE-m3 임베딩
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        print("\n! sentence-transformers/numpy 미설치.")
        print("  pip install sentence-transformers")
        print("  설치 후 다시 실행하거나, 지금은 --dry-run 으로 청크만 확인하세요.")
        _write_meta(outd, model_name, len(chunks), 0, dry=True)
        return

    print(f"\n임베딩 모델 로드: {model_name}")
    print("  (최초 실행은 모델 다운로드로 시간이 걸립니다)")
    model = SentenceTransformer(model_name)
    texts = [c["text"] for c in chunks]
    emb = model.encode(texts, batch_size=16, show_progress_bar=True,
                       normalize_embeddings=True, convert_to_numpy=True)
    emb = emb.astype("float32")
    np.save(outd / "embeddings.npy", emb)
    print(f"임베딩 저장: {emb.shape} → embeddings.npy")
    _write_meta(outd, model_name, len(chunks), emb.shape[1], dry=False)
    print(f"\n-> {out}/ (chunks.jsonl, embeddings.npy, bm25.pkl, index_meta.json)")


def _write_meta(outd: Path, model_name: str, n: int, dim: int, dry: bool) -> None:
    (outd / "index_meta.json").write_text(json.dumps(dict(
        embed_model=model_name, n_chunks=n, dim=dim,
        chunk_unit="jo_fulltext", has_embeddings=not dry,
        tokenizer="rule_based_ko_ngram"), ensure_ascii=False, indent=1),
        encoding="utf-8")


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
    else:
        mdl = a[a.index("--model") + 1] if "--model" in a else DEFAULT_MODEL
        outp = a[a.index("--out") + 1] if "--out" in a else "index"
        main(a[1], outp, mdl, "--dry-run" in a)
