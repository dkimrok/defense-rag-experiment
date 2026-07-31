#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG 실행기 — 검색(하이브리드) + 생성   [v2: 컨텍스트/에러/GPU 계측 강화]

변형 코퍼스(커버리지 조작 결과) × 문항으로 RAG 를 돌린다.
  1. 하이브리드 검색: BGE-m3 벡터 + BM25 를 결합해 top-k 조문 회수.
     변형 코퍼스에 남은 chunk 만 후보로 삼는다(커버리지 반영).
  2. 검색 품질 기록: gold 조가 top-k 에 들어왔는지 recall@k 를 남긴다.
  3. 생성: 회수한 조문 + 질문을 모델에게 주고 '답/근거/확신도' 형식으로 답받음.

핵심 설계
  - 임베딩은 24 가 만든 것을 재사용한다. 변형마다 재계산하지 않는다.
  - 커버리지 반영은 '남은 chunk_id 집합'으로 후보를 거르는 것으로 끝난다.
  - top-k 는 작게(기본 5). 커야 커버리지 조작 효과가 희석된다.
  - q_status(full/partial/none)를 응답에 실어 채점기로 넘긴다.

v2 변경점 (실험 타당성 방어용)
  (1) num_ctx 명시(기본 16384).
      기본값(4096)으로 돌리면 k=5 조 전체 청크가 컨텍스트를 넘겨
      프롬프트가 조용히 잘린다. 잘리면 '커버리지 때문에 못 맞춘 것'과
      '근거가 버려져서 못 맞춘 것'이 구분되지 않아 연구 주장이 무너진다.
  (2) 생성 실패를 raw_answer 에 문자열로 넣지 않고 error 필드로 분리.
      실패를 '기권'으로 오채점하는 것을 막는다.
  (3) prompt_eval_count / eval_count / done_reason 기록 → 잘림 사후 검증.
      "모든 조건에서 컨텍스트 잘림 0건"을 데이터로 증명할 수 있게 한다.
  (4) 연속 실패 시 조기 중단(기본 3회). 서버가 죽은 채 빈 레코드를
      수백 건 쌓는 것을 막는다.
  (5) 첫 생성 후 /api/ps 로 GPU 적재율 확인·기록. CPU 폴백 즉시 탐지.
  (6) run_meta.json 동시 출력(설정·계측 요약).
  (7) BM25 점수-청크 정렬 검증(순서 불일치 시 id 기준으로 재매핑).

입력
  index/            24 의 출력 (chunks.jsonl, embeddings.npy, bm25.pkl)
  변형 코퍼스        22 의 출력 corpus_covNNN_*.jsonl (남은 chunk 판정용)
  question_slots     문항 (질문, gold, answerable)
  coverage_manifest  문항별 q_status (선택; 없으면 gold 잔존으로 자동 판정)

사용법
  py 25_rag_run.py index question_final.jsonl \\
      --variant cov_core/corpus_cov100_core_doc.jsonl \\
      --manifest cov_core/coverage_manifest.json \\
      --model qwen3:8b --k 5 --alpha 0.5 --num-ctx 16384 --out runs
  py 25_rag_run.py index question_final.jsonl --variant ... --dry-run
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
import sys
import time
import urllib.request
from pathlib import Path

# 다중 GPU 병렬 실행을 위해 서버 주소를 바꿀 수 있게 둔다.
# T4 두 장이면 GPU 0/1 에 서버를 하나씩 띄우고 모델을 나눠 돌린다.
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_URL = OLLAMA_HOST + "/api/generate"
OLLAMA_PS = OLLAMA_HOST + "/api/ps"


def set_ollama_host(host: str) -> None:
    global OLLAMA_HOST, OLLAMA_URL, OLLAMA_PS
    host = host.rstrip("/")
    if not host.startswith("http"):
        host = "http://" + host
    OLLAMA_HOST, OLLAMA_URL, OLLAMA_PS = host, host + "/api/generate", host + "/api/ps"

# 컨텍스트 기본값. 관측된 최대 프롬프트(약 4,600토큰)의 3배 이상 여유.
# T4 15GiB 기준 KV 약 2.3GiB + 모델 4.9GiB ≈ 7.2GiB 로 충분히 들어간다.
DEFAULT_NUM_CTX = 16384
DEFAULT_NUM_PREDICT = 256

PROMPT_TMPL = """다음은 대한민국 방위사업 관련 법령·규정의 조문들입니다.

{context}

위 조문만을 근거로 질문에 답하십시오. 조문에 근거가 없으면 지어내지 말고 "근거 없음"이라고 답하십시오.

질문: {question}

반드시 한국어로, 아래 3줄 형식으로만 답하십시오. 설명이나 사고 과정을 쓰지 마십시오.
답: <핵심 답 또는 "근거 없음">
근거: <인용한 조문 번호 또는 "없음">
확신도: <높음|중간|낮음|모름>

지금 위 3줄만 출력하십시오:"""



def safe_name(s: str) -> str:
    """모델 이름을 파일명에 쓸 수 있게 정리한다.
    커뮤니티 모델은 'kamekichi128/qwen3-4b-instruct-2507:latest' 처럼
    슬래시를 포함한다. 그대로 파일명에 넣으면 없는 하위 폴더를 가리켜
    저장 단계에서 죽는다(실측: 97문항 생성 후 저장에서 실패).
    """
    return re.sub(r'[^A-Za-z0-9._-]', '-', s)


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def minmax(xs):
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-9:
        return [0.0] * len(xs)
    return [(x - lo) / (hi - lo) for x in xs]


# ---------------------------------------------------------------- 검색기

class Retriever:
    def __init__(self, index_dir: str, tokenizer,
                 allow_no_bm25: bool = False):
        idx = Path(index_dir)
        self.chunks = load(str(idx / "chunks.jsonl"))
        self.id2pos = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}
        self.tok = tokenizer

        self.meta = json.loads((idx / "index_meta.json").read_text(encoding="utf-8"))
        self.has_vec = self.meta.get("has_embeddings", False)
        if self.has_vec:
            import numpy as np
            self.np = np
            self.emb = np.load(idx / "embeddings.npy")
        bm = idx / "bm25.pkl"
        self.bm25 = None
        self.bm_pos = None          # bm25 점수 배열 index -> chunks 위치
        if bm.exists():
            # bm25.pkl 은 rank_bm25.BM25Okapi 객체를 담고 있어 그 패키지가
            # 설치돼 있어야 언피클된다. 없으면 벡터 검색만 남아 '하이브리드'
            # 조건이 조용히 바뀐다. 실험 조건이 달라진 줄 모르고 몇 시간을
            # 돌리는 일을 막기 위해, 기본은 중단이고 우회는 명시해야 한다.
            try:
                d = pickle.load(open(bm, "rb"))
            except ModuleNotFoundError as e:
                if not allow_no_bm25:
                    print(f"\n*** bm25.pkl 을 읽을 수 없습니다: {e}")
                    print("    BM25 인덱스가 rank_bm25 객체로 저장돼 있습니다.")
                    print("      pip install rank-bm25")
                    print("    를 실행하고 다시 돌리십시오.")
                    print("    BM25 없이 벡터 검색만으로 진행하려면"
                          " --allow-no-bm25 를 주십시오.")
                    print("    (그 경우 하이브리드 검색이 아니므로 다른 조건의"
                          " 결과와 직접 비교할 수 없습니다)")
                    raise SystemExit(3)
                print(f"  [경고] BM25 사용 불가({e}) — 벡터 검색만 사용합니다.")
                self.bm25_ids = []
                self._model = None
                return
            except Exception as e:                       # noqa: BLE001
                if not allow_no_bm25:
                    print(f"\n*** bm25.pkl 로드 실패: {type(e).__name__}: {e}")
                    print("    rank_bm25 버전이 인덱스 생성 시점과 다를 수 있습니다.")
                    print("    24_build_index.py 로 인덱스를 다시 만들거나,")
                    print("    --allow-no-bm25 로 벡터 검색만 쓰십시오.")
                    raise SystemExit(3)
                print(f"  [경고] BM25 로드 실패({type(e).__name__}) — 벡터만 사용.")
                self.bm25_ids = []
                self._model = None
                return
            self.bm25 = d["bm25"]
            self.bm25_ids = d["chunk_ids"]
            # 순서가 chunks 와 같다는 가정을 검증한다. 어긋나면 점수가
            # 엉뚱한 조문에 붙어 검색 결과 전체가 조용히 오염된다.
            same = (len(self.bm25_ids) == len(self.chunks) and
                    all(a == b["chunk_id"]
                        for a, b in zip(self.bm25_ids, self.chunks)))
            if not same:
                print("  [경고] bm25.pkl 순서가 chunks.jsonl 과 다릅니다. "
                      "chunk_id 기준으로 재매핑합니다.")
                self.bm_pos = {}
                for i, cid in enumerate(self.bm25_ids):
                    if cid in self.id2pos:
                        self.bm_pos[self.id2pos[cid]] = i

        if self.bm25 is None and not allow_no_bm25 and not bm.exists():
            print(f"\n*** {bm} 이 없습니다. 24_build_index.py 를 먼저 실행하거나,")
            print("    벡터 검색만 쓰려면 --allow-no-bm25 를 주십시오.")
            raise SystemExit(3)

        self._model = None      # 지연 로드(질의 임베딩용)
        self.qcache = None      # {qid: (vec_all, bm_all)} 전체 청크 기준 점수

    def _embed_query(self, q: str):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.meta["embed_model"])
        return self._model.encode([q], normalize_embeddings=True,
                                  convert_to_numpy=True)[0]

    # ------------------------------------------------------------ 질의 캐시
    def build_or_load_cache(self, items: list[tuple[str, str]],
                            path: Path, rebuild: bool = False) -> bool:
        """질문별 '전체 청크에 대한' 벡터·BM25 점수를 미리 계산해 저장한다.

        두 점수는 변형 코퍼스와 무관하다. 변형은 그 뒤에 살아있는 청크만
        고르는 필터일 뿐이다. 그런데 지금 구조는 (변형 x 모델) 실행마다
        전부 다시 계산한다. 조건이 50개면 같은 계산을 50번 한다.
        게다가 매 실행이 BGE-m3 를 새로 적재한다(2.3GB).

        캐시가 있으면 검색이 순수 numpy 슬라이싱이 되고, 임베딩 모델을
        아예 적재하지 않는다.

        크기: 질문 97 x 청크 7,481 x float32 x 2 = 약 5.8MB.
        """
        import numpy as np
        key = hashlib.md5(
            ("\n".join(c["chunk_id"] for c in self.chunks) + "\x00" +
             "\n".join(f"{i}\t{q}" for i, q in items)).encode()).hexdigest()

        if path.exists() and not rebuild:
            try:
                z = np.load(path, allow_pickle=False)
                if str(z["key"]) == key:
                    self.qcache = dict(zip(
                        [str(x) for x in z["qids"]],
                        zip(z["vec"], z["bm"])))
                    print(f"질의 캐시 사용: {path.name} "
                          f"({len(self.qcache)}문항) — 임베딩 모델 미적재")
                    return True
                print("  질의 캐시가 현재 인덱스/문항과 맞지 않아 다시 만듭니다.")
            except Exception as e:                       # noqa: BLE001
                print(f"  질의 캐시 로드 실패({type(e).__name__}) — 다시 만듭니다.")

        if not self.has_vec or self.bm25 is None:
            print("  임베딩 또는 BM25 가 없어 캐시를 만들지 않습니다.")
            return False

        print(f"질의 캐시 생성 중... ({len(items)}문항 x {len(self.chunks):,}청크)")
        t0 = time.time()
        vec = np.zeros((len(items), len(self.chunks)), dtype="float32")
        bm = np.zeros_like(vec)
        for i, (_, q) in enumerate(items):
            vec[i] = self.emb @ self._embed_query(q)
            sc = self.bm25.get_scores(self.tok(q))
            if self.bm_pos is None:
                bm[i] = np.asarray(sc[:len(self.chunks)], dtype="float32")
            else:
                for pos, j in self.bm_pos.items():
                    bm[i, pos] = sc[j]
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(items)}", end="\r")
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, key=key,
                            qids=np.array([i for i, _ in items]),
                            vec=vec, bm=bm)
        self.qcache = {qid: (vec[i], bm[i]) for i, (qid, _) in enumerate(items)}
        print(f"질의 캐시 저장: {path.name} "
              f"({path.stat().st_size/1024/1024:.1f}MB, {time.time()-t0:.0f}초)")
        return True

    def search(self, query: str, alive: set, k: int, alpha: float,
               qid: str | None = None) -> list[dict]:
        """alive = 변형 코퍼스에 남은 chunk_id 집합. 그 안에서만 검색."""
        # 정렬해 두면 동점 시 순서가 실행마다 흔들리지 않는다.
        alive_pos = sorted(self.id2pos[c] for c in alive if c in self.id2pos)
        if not alive_pos:
            return []

        # 캐시 경로: 전체 청크 점수에서 살아있는 위치만 잘라 쓴다.
        if self.qcache is not None and qid in self.qcache:
            import numpy as np
            v_all, b_all = self.qcache[qid]
            idx = np.asarray(alive_pos)
            vn = minmax(v_all[idx].tolist())
            bn = minmax(b_all[idx].tolist())
            comb = {p: alpha * vn[i] + (1 - alpha) * bn[i]
                    for i, p in enumerate(alive_pos)}
            top = sorted(comb, key=lambda p: -comb[p])[:k]
            return [dict(self.chunks[p], score=round(comb[p], 4)) for p in top]

        # 벡터 점수
        vec_scores = {}
        if self.has_vec:
            qv = self._embed_query(query)
            sub = self.emb[alive_pos]                 # (M, D)
            sims = sub @ qv                           # 정규화돼 있어 내적=코사인
            for pos, s in zip(alive_pos, sims):
                vec_scores[pos] = float(s)

        # BM25 점수
        bm_scores = {}
        if self.bm25 is not None:
            q_tok = self.tok(query)
            all_scores = self.bm25.get_scores(q_tok)
            for pos in alive_pos:
                j = pos if self.bm_pos is None else self.bm_pos.get(pos, -1)
                bm_scores[pos] = float(all_scores[j]) if 0 <= j < len(all_scores) else 0.0

        # 결합
        positions = alive_pos
        if vec_scores and bm_scores:
            vn = dict(zip(positions, minmax([vec_scores[p] for p in positions])))
            bn = dict(zip(positions, minmax([bm_scores[p] for p in positions])))
            combined = {p: alpha * vn[p] + (1 - alpha) * bn[p] for p in positions}
        elif vec_scores:
            combined = vec_scores
        else:
            combined = bm_scores

        top = sorted(combined, key=lambda p: -combined[p])[:k]
        return [dict(self.chunks[p], score=round(combined[p], 4)) for p in top]


# ---------------------------------------------------------------- 토크나이저(24와 동일)

def tokenize_ko(text: str) -> list[str]:
    text = text.lower()
    jo = [re.sub(r'\s+', '', t) for t in
          re.findall(r'제\s*\d+\s*조(?:의\s*\d+)?', text)]
    words = re.findall(r'[가-힣]+|[a-z]+|\d+', text)
    grams = []
    for w in words:
        grams.append(w)
        if len(w) > 4:
            for i in range(len(w) - 1):
                grams.append(w[i:i + 2])
    return jo + grams


# ---------------------------------------------------------------- 생성

def generate_ollama(model: str, prompt: str, timeout: int = 600,
                    think: bool = False,
                    num_ctx: int = DEFAULT_NUM_CTX,
                    num_predict: int = DEFAULT_NUM_PREDICT) -> dict:
    """성공 시 계측치를 포함한 dict 반환. 실패는 예외로 올린다(호출부에서 분리 기록).

    num_ctx 를 반드시 명시한다. 생략하면 서버 기본값(4096)이 적용되어
    k=5 조 전체 청크가 들어간 프롬프트가 잘린다.
    """
    opts = dict(temperature=0.0, num_predict=num_predict, num_ctx=num_ctx)
    payload = dict(model=model, prompt=prompt, stream=False, options=opts)
    if not think:
        # qwen3 는 think 를 최상위 파라미터로 받아야 확실히 꺼진다.
        payload["think"] = False
        # 폴백: 프롬프트 앞뒤로 /no_think 를 넣는다(일부 빌드는 위치를 탐).
        payload["prompt"] = "/no_think\n" + prompt + "\n/no_think"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read())
    return dict(
        response=j.get("response", ""),
        prompt_eval_count=j.get("prompt_eval_count"),
        eval_count=j.get("eval_count"),
        done_reason=j.get("done_reason"),
    )


def ollama_ps() -> list[dict]:
    """적재된 모델의 VRAM 비율. 100 이면 완전 GPU, 낮으면 CPU 폴백."""
    try:
        with urllib.request.urlopen(OLLAMA_PS, timeout=15) as r:
            d = json.loads(r.read())
    except Exception:                                    # noqa: BLE001
        return []
    out = []
    for m in d.get("models", []):
        tot = m.get("size") or 0
        vram = m.get("size_vram") or 0
        out.append(dict(name=m.get("name"),
                        gpu_pct=round(vram / tot * 100, 1) if tot else None,
                        size=tot, size_vram=vram))
    return out


# ---------------------------------------------------------------- recall

def gold_chunk_ids(slot: dict) -> set:
    """gold evidence 의 unit_id 를 조 청크 id 로 환원."""
    out = set()
    for g in slot.get("gold_evidence", []):
        uid = g.get("unit_id", "")
        # 청크 id = 조 수준 prefix (prefix:docid:jocode)
        parts = uid.split(":")
        if len(parts) >= 3:
            out.add(":".join(parts[:3]))
    return out


# ---------------------------------------------------------------- 메인

def main(index_dir: str, slots_path: str, variant: str, manifest: str | None,
         model: str, k: int, alpha: float, dry: bool, out: str,
         think: bool = False, timeout: int = 600,
         num_ctx: int = DEFAULT_NUM_CTX,
         num_predict: int = DEFAULT_NUM_PREDICT,
         max_consec_fail: int = 3,
         allow_no_bm25: bool = False,
         use_cache: bool = True, cache_path: str = "",
         rebuild_cache: bool = False) -> int:
    cache_path = cache_path or str(Path(index_dir) / "query_cache.npz")
    slots = {s["qid"]: s for s in load(slots_path)}
    retr = Retriever(index_dir, tokenize_ko, allow_no_bm25=allow_no_bm25)

    if use_cache:
        items = [(qid, sl.get("question_ko", "").strip())
                 for qid, sl in slots.items()
                 if sl.get("question_ko", "").strip()]
        retr.build_or_load_cache(items, Path(cache_path), rebuild=rebuild_cache)

    # 변형 코퍼스에 남은 chunk 집합
    variant_units = {json.loads(l)["unit_id"]
                     for l in Path(variant).read_text(encoding="utf-8").splitlines()
                     if l.strip()}
    alive_chunks = {c["chunk_id"] for c in retr.chunks
                    if c["chunk_id"] in variant_units}

    # 커버리지 조건 식별 (파일명에서)
    m = re.search(r'cov(\d+)_(\w+?)_(\w+)\.jsonl', Path(variant).name)
    cov = int(m.group(1)) if m else None
    strategy = m.group(2) if m else "na"
    unit = m.group(3) if m else "na"

    # q_status 로드
    qstat = {}
    if manifest and Path(manifest).exists():
        mf = json.loads(Path(manifest).read_text(encoding="utf-8"))
        for c in mf.get("conditions", []):
            if c.get("target_cov") == cov and c.get("strategy") == strategy \
               and c.get("unit") == unit:
                qstat = c.get("q_status", {})
                break

    print(f"변형 {Path(variant).name} | cov {cov}% {strategy}/{unit}")
    print(f"살아있는 청크 {len(alive_chunks):,} / 전체 {len(retr.chunks):,}")
    print(f"벡터검색 {'ON' if retr.has_vec else 'OFF(임베딩없음)'} | "
          f"BM25 {'ON' if retr.bm25 else 'OFF'} | k={k} alpha={alpha}")
    print(f"서버 {OLLAMA_HOST}")
    print(f"모델 {model} | reasoning {'ON' if think else 'OFF(/no_think)'} | "
          f"num_ctx={num_ctx} num_predict={num_predict} "
          f"{'(dry-run)' if dry else ''}\n")

    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)
    results = []
    recall_hit = 0
    recall_tot = 0
    n_err = 0
    consec_fail = 0
    aborted = False
    gpu_info = []

    for qid, slot in slots.items():
        q = slot.get("question_ko", "").strip()
        if not q:
            continue
        hits = retr.search(q, alive_chunks, k, alpha, qid=qid)
        hit_ids = {h["chunk_id"] for h in hits}

        # recall@k (답 가능 문항만, gold 가 애초에 코퍼스에 있었던 경우)
        gold_ids = gold_chunk_ids(slot)
        status = qstat.get(qid, _auto_status(gold_ids, alive_chunks, slot))
        recalled = None
        if slot.get("answerable", True) and gold_ids:
            alive_gold = gold_ids & alive_chunks
            if alive_gold:
                recalled = len(alive_gold & hit_ids) / len(alive_gold)
                recall_hit += 1 if (alive_gold & hit_ids) else 0
                recall_tot += 1

        context = "\n\n".join(
            f"[{h['doc_name']} {h.get('jo_title','')}]\n{h['text'][:1200]}"
            for h in hits) or "(검색된 조문 없음)"
        prompt = PROMPT_TMPL.format(context=context, question=q)

        raw = ""
        err = None
        gen = {}
        dt = None
        if not dry:
            t0 = time.time()
            try:
                gen = generate_ollama(model, prompt, timeout=timeout, think=think,
                                      num_ctx=num_ctx, num_predict=num_predict)
                raw = gen.get("response", "")
                dt = time.time() - t0
                consec_fail = 0
                if len(results) == 0:      # 첫 문항: 속도·GPU·토큰수 즉시 보고
                    print(f"  [1번 문항 생성 {dt:.0f}초] "
                          f"전체 예상 ~{dt*len(slots)/60:.0f}분 | "
                          f"프롬프트 {gen.get('prompt_eval_count')}토큰 / "
                          f"출력 {gen.get('eval_count')}토큰")
                    gpu_info = ollama_ps()
                    for g in gpu_info:
                        tag = "정상(GPU)" if (g["gpu_pct"] or 0) >= 99 else "*** CPU 폴백 의심 ***"
                        print(f"  [적재] {g['name']} VRAM {g['gpu_pct']}% {tag}")
            except Exception as e:                       # noqa: BLE001
                dt = time.time() - t0
                raw = None
                err = f"{type(e).__name__}: {e}"
                n_err += 1
                consec_fail += 1
                print(f"  [실패] {qid} ({dt:.0f}초): {err}")
                if consec_fail == 1:
                    print(f"  Ollama 연결/모델을 확인하세요: ollama run {model} \"테스트\"")

        # 잘림 의심 판정: 프롬프트 토큰이 컨텍스트 한계에 붙었는지.
        # (서버가 자르면 prompt_eval_count 가 한계값에 고정된다)
        ptok = gen.get("prompt_eval_count")
        trunc_suspect = bool(ptok and ptok >= num_ctx - num_predict - 16)

        results.append(dict(
            qid=qid, condition=f"cov{cov}_{strategy}_{unit}", cov=cov,
            strategy=strategy, unit=unit, model=model,
            q_status=status,
            retrieved=[h["chunk_id"] for h in hits],
            retrieved_titles=[f"{h['doc_name']} {h.get('jo_title','')}" for h in hits],
            gold_chunks=sorted(gold_ids),
            recall_at_k=recalled,
            prompt=prompt if dry else None,
            prompt_chars=len(prompt),
            prompt_eval_count=ptok,
            eval_count=gen.get("eval_count"),
            done_reason=gen.get("done_reason"),
            trunc_suspect=trunc_suspect,
            num_ctx=num_ctx,
            gen_seconds=round(dt, 1) if dt is not None else None,
            error=err,
            raw_answer=raw))

        if consec_fail >= max_consec_fail:
            aborted = True
            print(f"\n*** 연속 {consec_fail}회 실패 — 중단합니다. "
                  f"서버가 죽었을 가능성이 큽니다. ***")
            print("   여기까지의 결과는 파일로 저장합니다.")
            break

    # ------------------------------------------------ 저장
    covtag = f"{cov:03d}" if isinstance(cov, int) else "NA"
    fn = outd / f"responses_cov{covtag}_{strategy}_{unit}_{safe_name(model)}.jsonl"
    with open(fn, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_ok = sum(1 for r in results if (r["raw_answer"] or "").strip())
    n_trunc = sum(1 for r in results if r["trunc_suspect"])
    ptoks = [r["prompt_eval_count"] for r in results if r["prompt_eval_count"]]
    rec = recall_hit / recall_tot * 100 if recall_tot else 0

    meta = dict(variant=Path(variant).name, condition=f"cov{cov}_{strategy}_{unit}",
                model=model, k=k, alpha=alpha, num_ctx=num_ctx,
                retrieval="hybrid" if retr.bm25 is not None else "vector_only",
                query_cache=bool(retr.qcache), ollama_host=OLLAMA_HOST,
                num_predict=num_predict, think=think,
                n_questions=len(results), n_ok=n_ok, n_error=n_err,
                n_trunc_suspect=n_trunc,
                max_prompt_tokens=max(ptoks) if ptoks else None,
                recall_at_k_any=round(rec, 1), aborted=aborted,
                gpu=gpu_info)
    (outd / f"meta_cov{covtag}_{strategy}_{unit}_{safe_name(model)}.json"
     ).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n문항 {len(results)}개 처리 | 응답 {n_ok} | 실패 {n_err}")
    print(f"recall@{k} (any-gold): {rec:.0f}% ({recall_hit}/{recall_tot})")
    if ptoks:
        print(f"프롬프트 토큰 최대 {max(ptoks)} / num_ctx {num_ctx}")
    if n_trunc:
        print(f"*** 잘림 의심 {n_trunc}건 — num_ctx 를 더 키우십시오 ***")
    print(f"-> {fn.name}")

    if dry:
        ex = next((r for r in results if r["retrieved"]), None)
        if ex:
            print(f"\n[예시 검색] {ex['qid']}")
            for t in ex["retrieved_titles"][:k]:
                print(f"  - {t}")

    # 오케스트레이터가 실패를 감지할 수 있도록 종료코드로 알린다.
    return 1 if (aborted or n_err) else 0


def _auto_status(gold_ids: set, alive: set, slot: dict) -> str:
    if not slot.get("answerable", True):
        return "oos"
    if not gold_ids:
        return "none"
    kept = gold_ids & alive
    if not kept:
        return "none"
    if kept == gold_ids:
        return "full"
    return "partial"


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 3 or "--variant" not in a:
        print(__doc__)
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        if "--ollama-url" in a:
            set_ollama_host(opt("--ollama-url", ""))
        code = main(a[1], a[2], opt("--variant", ""), opt("--manifest", None),
                    opt("--model", "qwen3:8b"), int(opt("--k", "5")),
                    float(opt("--alpha", "0.5")), "--dry-run" in a,
                    opt("--out", "runs"), "--think" in a,
                    int(opt("--timeout", "600")),
                    int(opt("--num-ctx", str(DEFAULT_NUM_CTX))),
                    int(opt("--num-predict", str(DEFAULT_NUM_PREDICT))),
                    int(opt("--max-consec-fail", "3")),
                    "--allow-no-bm25" in a,
                    "--no-cache" not in a, opt("--cache", ""),
                    "--rebuild-cache" in a)
        sys.exit(code)
