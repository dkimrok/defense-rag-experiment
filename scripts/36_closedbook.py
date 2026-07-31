#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
36_closedbook.py — 폐쇄북 통제 arm

검색 컨텍스트를 전혀 주지 않고 같은 문항을 묻는다. RAG 논문의 표준
베이스라인이면서, 이 연구에서는 그보다 중요한 역할을 한다.

왜 필수인가
  본실험에서 확신도가 전 조건 95~100% '높음' 으로 고정된다.
  이것만 보면 "확신도 프롬프트를 잘못 짠 것 아니냐"는 반론이 가능하다.
  15문항 예비 실험에서 폐쇄북은 중간 8 / 모름 6 / 높음 1 로 분산이 있었다.
  즉 모델에게 불확실성을 표현할 능력은 있는데, 검색 결과를 받는 순간
  사라진다. 그 대조가 있어야 주장이 성립한다.

  동시에 사전학습 오염 통제이기도 하다. 폐쇄북에서 못 맞히면
  '방위사업 법령은 사전학습 오염이 낮다'는 도메인 선택 근거가 데이터로
  뒷받침된다.

출력
  23_grade.py 가 그대로 읽는 형식으로 쓴다.
    q_status : 답가능 문항은 'none'(근거가 아예 없음), 범위밖은 'oos'
               -> 23 의 규칙상 기권이 정답으로 처리된다. 폐쇄북에서
                  기권은 정직한 행동이므로 맞는 처리다.
    condition: 'closedbook'
    arm      : 'closedbook'  (본실험 레코드와 구분용)

사용법
  py 36_closedbook.py question_final.jsonl --model qwen3:8b --out runs_closedbook
  py 36_closedbook.py question_final.jsonl --model qwen3:4b --out runs_closedbook
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_URL = OLLAMA_HOST + "/api/generate"
OLLAMA_PS = OLLAMA_HOST + "/api/ps"


def set_ollama_host(host: str) -> None:
    global OLLAMA_HOST, OLLAMA_URL, OLLAMA_PS
    host = host.rstrip("/")
    if not host.startswith("http"):
        host = "http://" + host
    OLLAMA_HOST, OLLAMA_URL, OLLAMA_PS = host, host + "/api/generate", host + "/api/ps"

DEFAULT_NUM_CTX = 16384
DEFAULT_NUM_PREDICT = 256

# 본실험 프롬프트와 형식·어투를 맞춘다. 다른 것은 '조문이 주어지지
# 않는다'는 사실뿐이어야 대조가 성립한다.
PROMPT_TMPL = """다음 질문에 답하십시오. 참고할 조문은 주어지지 않습니다.
확실하지 않으면 지어내지 말고 "모름"이라고 답하십시오.

질문: {question}

반드시 한국어로, 아래 3줄 형식으로만 답하십시오. 설명이나 사고 과정을 쓰지 마십시오.
답: <핵심 답 또는 "모름">
근거: <관련 조문 번호 또는 "없음">
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


def generate(model: str, prompt: str, timeout: int, num_ctx: int,
             num_predict: int, think: bool = False) -> dict:
    opts = dict(temperature=0.0, num_predict=num_predict, num_ctx=num_ctx)
    payload = dict(model=model, prompt=prompt, stream=False, options=opts)
    if not think:
        payload["think"] = False
        payload["prompt"] = "/no_think\n" + prompt + "\n/no_think"
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read())
    return dict(response=j.get("response", ""),
                prompt_eval_count=j.get("prompt_eval_count"),
                eval_count=j.get("eval_count"),
                done_reason=j.get("done_reason"))


def ollama_ps() -> list[dict]:
    try:
        with urllib.request.urlopen(OLLAMA_PS, timeout=15) as r:
            d = json.loads(r.read())
    except Exception:                                    # noqa: BLE001
        return []
    out = []
    for m in d.get("models", []):
        tot, vram = m.get("size") or 0, m.get("size_vram") or 0
        out.append(dict(name=m.get("name"),
                        gpu_pct=round(vram / tot * 100, 1) if tot else None))
    return out


def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    if "--ollama-url" in a:
        set_ollama_host(opt("--ollama-url", ""))
    slots = load(a[1])
    model = opt("--model", "qwen3:8b")
    out = Path(opt("--out", "runs_closedbook"))
    num_ctx = int(opt("--num-ctx", str(DEFAULT_NUM_CTX)))
    num_predict = int(opt("--num-predict", str(DEFAULT_NUM_PREDICT)))
    timeout = int(opt("--timeout", "120"))
    think = "--think" in a
    max_consec_fail = int(opt("--max-consec-fail", "3"))

    out.mkdir(parents=True, exist_ok=True)
    tag = safe_name(model)
    fn = out / f"responses_closedbook_{tag}.jsonl"

    todo = [s for s in slots if (s.get("question_ko") or "").strip()]
    print(f"서버 {OLLAMA_HOST}")
    print(f"폐쇄북 arm | 문항 {len(todo)}개 | 모델 {model} | "
          f"num_ctx={num_ctx} reasoning {'ON' if think else 'OFF'}\n")

    results = []
    n_err = consec = 0
    gpu_info = []
    # 한 건씩 바로 기록한다. 마지막에 몰아 쓰면 중간에 죽었을 때 전부 잃는다.
    fh = open(fn, "w", encoding="utf-8")
    for s in todo:
        prompt = PROMPT_TMPL.format(question=s["question_ko"].strip())
        raw, err, gen, dt = None, None, {}, None
        t0 = time.time()
        try:
            gen = generate(model, prompt, timeout, num_ctx, num_predict, think)
            raw = gen.get("response", "")
            dt = time.time() - t0
            consec = 0
            if not results:
                print(f"  [1번 문항 {dt:.0f}초] 전체 예상 "
                      f"~{dt*len(todo)/60:.0f}분")
                gpu_info = ollama_ps()
                for g in gpu_info:
                    ok = (g["gpu_pct"] or 0) >= 99
                    print(f"  [적재] {g['name']} VRAM {g['gpu_pct']}% "
                          f"{'정상(GPU)' if ok else '*** CPU 폴백 의심 ***'}")
        except Exception as e:                           # noqa: BLE001
            dt = time.time() - t0
            err = f"{type(e).__name__}: {e}"
            n_err += 1
            consec += 1
            print(f"  [실패] {s['qid']} ({dt:.0f}초): {err}")

        results.append(dict(
            qid=s["qid"], condition="closedbook", arm="closedbook",
            cov=None, strategy="closedbook", unit="none", model=model,
            # 근거가 아예 주어지지 않으므로 답가능 문항도 'none' 이다.
            # 23 의 규칙상 기권이 정답으로 처리된다.
            q_status="oos" if not s.get("answerable", True) else "none",
            retrieved=[], retrieved_titles=[], gold_chunks=[],
            recall_at_k=None, prompt=None, prompt_chars=len(prompt),
            prompt_eval_count=gen.get("prompt_eval_count"),
            eval_count=gen.get("eval_count"),
            done_reason=gen.get("done_reason"),
            trunc_suspect=False, num_ctx=num_ctx,
            gen_seconds=round(dt, 1) if dt is not None else None,
            error=err, raw_answer=raw))
        fh.write(json.dumps(results[-1], ensure_ascii=False) + "\n")
        fh.flush()

        if consec >= max_consec_fail:
            print(f"\n*** 연속 {consec}회 실패 — 중단합니다. ***")
            break

    fh.close()

    n_ok = sum(1 for r in results if (r["raw_answer"] or "").strip())
    meta = dict(arm="closedbook", model=model, model_tag=tag, num_ctx=num_ctx,
                num_predict=num_predict, think=think,
                n_questions=len(results), n_ok=n_ok, n_error=n_err,
                gpu=gpu_info)
    (out / f"meta_closedbook_{tag}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 확신도 분포를 바로 보여준다. 본실험과의 대조가 이 arm 의 존재 이유다.
    from collections import Counter
    def conf(x):
        x = (x or "").split("</think>")[-1]
        for ln in x.splitlines():
            if ln.startswith("확신도"):
                return ln.split(":", 1)[-1].strip()
        return "?"
    dist = Counter(conf(r["raw_answer"]) for r in results)
    print(f"\n문항 {len(results)}개 | 응답 {n_ok} | 실패 {n_err}")
    print(f"확신도 분포: {dict(dist)}")
    print("  (본실험은 전 조건 95~100% '높음' 이었다. 여기서 분산이 나오면"
          " 척도는 살아있고 검색 컨텍스트가 과신을 유발한 것이다.)")
    print(f"-> {fn.name}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
