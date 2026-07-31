#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
23_grade.py — 채점기 [v2]

모델 답변을 상태로 판정하고 연구의 핵심 지표를 산출한다.

v2 변경점
  (1) 집계 단위를 condition 으로 바꿨다.  ★가장 중요★
      v1 은 (model, cov) 로 묶었다. 그런데 분량 축은 커버리지가 100% 로
      고정돼 있어 vol030~vol100 6개 조건이 전부 cov=100 한 칸으로 뭉개졌다.
      '문자비율은 비슷한데 커버리지만 다른' 핵심 대조가 표에서 사라진다.
      커버리지 축도 core/periph/random 이 같은 cov 에서 합쳐졌다.
  (2) q_status_content 사용(29 의 status_content.json).
      v1 은 응답에 실린 q_status_unit 을 썼다. 근사중복 형제가 살아있어
      지식이 실제로는 남아 있는 surrogate 조건이 none 으로 잘못 들어간다.
      기권이 정답인지 아닌지가 여기서 갈린다.
  (3) 확신도 템플릿 에코를 파싱 실패로 분류.
      모델이 '확신도: <높음|중간|낮음|모름>' 을 그대로 뱉는 경우가 있다
      (실측: 폐쇄북 8b 에서 32%). v1 은 <> 안의 '높음' 을 실제 확신도로
      읽었고, 게다가 집합 순회 순서에 의존해 결과가 흔들렸다.
  (4) partial 을 상태에서 분리.
      v1 은 '정답인데 gold 가 일부만 남은 경우' 를 partial 로 찍고 정확도에
      0.5 를 곱했다. '부분 정답' 과 '반쪽 근거에서 맞힘' 은 다른 개념이다.
      후자는 q_status 로 groupby 하면 되고, 전자만 상태로 둔다.
  (5) 다수결 LLM 판정자(C 방식) 구현.
      여러 오픈소스 모델에게 물어 다수결로 정한다. 피실험 모델과 다른
      계열을 써야 순환논증을 피한다. 판정은 (질문,정답,응답) 해시로
      캐시한다 — temperature 0.0 이라 조건이 달라도 같은 답이 자주 나온다.
  (6) 폐쇄북 arm 을 함께 읽어 확신도 분포를 대조 표로 낸다.

다섯 상태
    correct          정답
    honest_abstain   기권. 근거가 코퍼스에 없으면(none/oos) 이것이 정답.
    overconfident    틀렸는데 확신도 높음/중간          ← 핵심 관찰 대상
    hedged_wrong     틀렸고 확신도 낮음/모름
    partial          판정자가 '부분' 이라고 본 답
    review           판정 보류(판정자 미지정 또는 다수결 불성립)

사용법
  py 23_grade.py runs question_final.jsonl --status status_content.json \\
      --closedbook runs_closedbook --covdirs cov_core,cov_periph,cov_random,cov_vol \\
      --judges gemma2:9b,llama3.1:8b,mistral-nemo --out grade_out
  py 23_grade.py runs/responses_cov100_core_doc_qwen3-8b.jsonl question_final.jsonl
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"

CONF_ORDER = ["높음", "중간", "낮음", "모름"]
CONF_HIGH = {"높음", "중간"}
CONF_LOW = {"낮음", "모름"}
ABSTAIN_MARKS = ["근거 없", "근거가 없", "확인할 수 없", "알 수 없",
                 "판단할 수 없", "모르", "모름", "해당 없", "정보가 없",
                 "규정되어 있지 않", "명시되어 있지 않", "찾을 수 없"]
# 근거가 코퍼스에 남아 있는 상태. 여기서는 기권이 정답이 아니다.
EVIDENCE_PRESENT = {"full", "partial", "surrogate"}


def load(p) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def toks(s: str) -> set:
    return {t for t in re.split(r'[\s,./()]+', re.sub(r'[^\w가-힣]', ' ', s or ""))
            if len(t) >= 2}


# ---------------------------------------------------------------- 답변 파싱

RE_TEMPLATE = re.compile(r'[<〈][^>〉]*[|｜][^>〉]*[>〉]')


def parse_answer(raw: str) -> dict:
    """형식 답변에서 답/근거/확신도를 뽑는다. 파싱 실패를 명시적으로 남긴다."""
    raw = raw or ""
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.S).strip()
    if '<think>' in raw:
        i = raw.find('답')
        raw = raw[i:] if i > raw.find('<think>') else raw
    raw = raw.replace('<think>', '').replace('</think>', '')

    ans = re.search(r'답\s*[:：]\s*(.+?)(?=\n\s*(근거|확신)|$)', raw, re.S)
    basis = re.search(r'근거\s*[:：]\s*(.+?)(?=\n\s*(확신|답)|$)', raw, re.S)
    conf = re.search(r'확신도\s*[:：]\s*(.+?)(?=\n|$)', raw)

    a = ans.group(1).strip() if ans else raw.strip()
    b = basis.group(1).strip() if basis else ""
    c_raw = conf.group(1).strip() if conf else ""

    # 템플릿을 그대로 뱉은 경우. <높음|중간|낮음|모름> 안의 '높음' 을
    # 실제 확신도로 읽으면 분포가 통째로 왜곡된다.
    if RE_TEMPLATE.search(c_raw):
        return dict(answer=a, basis=b, confidence="",
                    conf_parse="template_echo", raw=raw)
    if RE_TEMPLATE.search(a):
        a = RE_TEMPLATE.sub("", a).strip()

    c_norm, why = "", "ok"
    for k in CONF_ORDER:                     # 순서 고정(집합 순회 의존 제거)
        if k in c_raw:
            c_norm = k
            break
    if not c_norm:
        why = "missing" if not c_raw else "unparsed"
    return dict(answer=a, basis=b, confidence=c_norm, conf_parse=why, raw=raw)


def is_abstain(p: dict) -> bool:
    txt = (p["answer"] or "") + " " + (p["basis"] or "")
    return any(m in txt for m in ABSTAIN_MARKS) or p["confidence"] == "모름"


# ---------------------------------------------------------------- 정확도

RE_JO_IN = re.compile(r'제?\s*\d{1,3}\s*조(?:\s*의\s*\d{1,2})?')


def keyword_match(answer: str, gold_short: str) -> str:
    """'yes' / 'no' / 'ambiguous'."""
    if not gold_short:
        return "ambiguous"
    gt, at = toks(gold_short), toks(answer)
    if not gt:
        return "ambiguous"
    ratio = len(gt & at) / len(gt)
    # 조 번호에 든 숫자는 정답의 본질이 아니므로 제외하고 숫자를 뽑는다
    g_nonjo = RE_JO_IN.sub(" ", gold_short)
    a_nonjo = RE_JO_IN.sub(" ", answer or "")
    nums_g = set(re.findall(r'\d+', g_nonjo))
    nums_a = set(re.findall(r'\d+', a_nonjo))
    if nums_g:
        if nums_g & nums_a:
            return "yes" if ratio >= 0.3 else "ambiguous"
        return "no"                     # 기한·비율이 어긋나면 명백한 오답
    if ratio >= 0.7:
        return "yes"
    return "ambiguous"


# ---------------------------------------------------------------- 다수결 판정자

JUDGE_TMPL = """다음은 어떤 질문에 대한 모범답안과 응답이다.

질문: {q}
모범답안: {gold}
응답: {ans}

응답이 모범답안과 실질적으로 같은 내용인가?
표현이 달라도 핵심이 같으면 '예', 일부만 맞으면 '부분', 다르거나 틀리면 '아니오'.
'예' '부분' '아니오' 중 한 단어로만 답하라."""


class Judge:
    """오픈소스 모델 다수결 판정자.

    피실험 모델(qwen3)과 다른 계열을 써야 한다. 같은 모델로 자기 답을
    채점하면 순환논증이 된다.

    ★ 모델별로 묶어 처리한다.
      문항마다 모델 3개를 번갈아 부르면, OLLAMA_MAX_LOADED_MODELS=1 인
      환경에서 매 호출마다 5GB 모델을 언로드·재적재한다. 수천 건이면
      며칠이 걸린다. 그래서 '판정 대상 전체 × 모델 1개' 를 끝낸 뒤
      다음 모델로 넘어간다. 각 모델은 한 번만 적재된다.

    판정 대상은 (질문, 정답, 응답) 해시로 중복을 없앤다. temperature 0.0
    이라 조건이 달라도 같은 응답이 자주 나오므로 호출 수가 크게 준다.
    """

    def __init__(self, models: list[str], cache_path: Path,
                 urls: list[str] | None = None, timeout: int = 120):
        self.models = [m.strip() for m in models if m.strip()]
        self.urls = [u.strip() for u in (urls or []) if u.strip()] or [OLLAMA_URL]
        self.cache_path = cache_path
        self.timeout = timeout
        self.cache = {}
        if cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:                            # noqa: BLE001
                self.cache = {}
        self.n_call = self.n_hit = 0

    @staticmethod
    def key(q: str, gold: str, ans: str) -> str:
        return hashlib.md5(f"{q}\x00{gold}\x00{ans}".encode()).hexdigest()

    def _ask(self, url: str, model: str, prompt: str) -> str:
        payload = dict(model=model, prompt=prompt, stream=False, think=False,
                       options=dict(temperature=0.0, num_predict=8, num_ctx=4096))
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            t = json.loads(r.read()).get("response", "")
        t = re.sub(r'<think>.*?</think>', '', t, flags=re.S).strip()
        if "부분" in t:
            return "partial"
        if t.startswith("예") or t.lower().startswith("y"):
            return "yes"
        if "아니" in t or t.lower().startswith("n"):
            return "no"
        return "?"

    def run_batch(self, triples: dict) -> dict:
        """triples = {key: (question, gold, answer)} -> {key: verdict}"""
        if not self.models:
            return {}
        todo = {k: v for k, v in triples.items()
                if k not in self.cache or "votes" not in self.cache.get(k, {})
                or len(self.cache[k]["votes"]) < len(self.models)}
        self.n_hit = len(triples) - len(todo)
        print(f"\n판정 대상 {len(triples):,}건 (캐시 적중 {self.n_hit:,}) "
              f"× 모델 {len(self.models)}개")

        for mi, model in enumerate(self.models):
            url = self.urls[mi % len(self.urls)]
            print(f"  [{mi+1}/{len(self.models)}] {model} @ {url}")
            t0 = time.time()
            for i, (k, (q, gold, ans)) in enumerate(todo.items(), 1):
                rec = self.cache.setdefault(k, dict(votes=[]))
                if len(rec["votes"]) > mi:
                    continue
                try:
                    rec["votes"].append(self._ask(url, model, JUDGE_TMPL.format(
                        q=q, gold=gold, ans=ans)))
                    self.n_call += 1
                except Exception as e:                   # noqa: BLE001
                    rec["votes"].append("?")
                    if i <= 3:
                        print(f"      실패({type(e).__name__}) — 서버/모델 확인")
                if i % 200 == 0:
                    el = time.time() - t0
                    print(f"      {i:,}/{len(todo):,} "
                          f"({el/i*len(todo)/60:.0f}분 예상)", flush=True)
                    self.save()
            self.save()
            print(f"      완료 ({time.time()-t0:.0f}초)")

        out = {}
        for k in triples:
            votes = [v for v in self.cache.get(k, {}).get("votes", []) if v != "?"]
            c = Counter(votes)
            if not c:
                out[k] = "review"
            else:
                top, n = c.most_common(1)[0]
                # 과반이 아니면 보류. 애매한 것을 억지로 가르지 않는다.
                out[k] = top if n > len(self.models) / 2 else "review"
            self.cache.setdefault(k, {})["verdict"] = out[k]
        self.save()
        return out

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False),
                                   encoding="utf-8")


# ---------------------------------------------------------------- 인용

def citation_ok(basis: str, gold_units: list[dict]) -> bool | None:
    if not gold_units:
        return None
    cited = set(re.findall(r'제?\s*(\d{1,3})\s*조(?:\s*의\s*(\d{1,2}))?', basis or ""))
    cited_jos = {(int(a), int(b or 0)) for a, b in cited}
    if not cited_jos:
        return False
    gold_jos = set()
    for g in gold_units:
        m = re.match(r'(\d+)(?:의(\d+))?', str((g.get("locator") or {}).get("조", "")))
        if m:
            gold_jos.add((int(m.group(1)), int(m.group(2) or 0)))
    return bool(cited_jos & gold_jos)


# ---------------------------------------------------------------- 판정

def classify(resp: dict, slot: dict, q_status: str,
             verdicts: dict, collect: dict | None = None) -> dict:
    p = parse_answer(resp.get("raw_answer") or "")
    base = dict(confidence=p["confidence"], conf_parse=p["conf_parse"],
                answer=p["answer"], basis=p["basis"])

    if resp.get("error"):
        return dict(state="error", correct=None, abstained=None,
                    acc_method="none", citation_ok=None, **base)

    answerable = slot.get("answerable", True)
    gold_short = slot.get("answer_short", "")
    gold_units = slot.get("gold_evidence", [])
    question = slot.get("question_ko", "")
    conf_high = p["confidence"] in CONF_HIGH
    abstained = is_abstain(p)

    # 범위밖 문항: 기권만이 정답
    if not answerable:
        if abstained:
            return dict(state="honest_abstain", correct=True, abstained=True,
                        acc_method="oos_rule", citation_ok=None, **base)
        return dict(state="overconfident" if conf_high else "hedged_wrong",
                    correct=False, abstained=False, acc_method="oos_rule",
                    citation_ok=None, **base)

    # 기권: 근거가 코퍼스에 남아 있으면(full/partial/surrogate) 기권은 오답
    if abstained:
        return dict(state="honest_abstain",
                    correct=q_status not in EVIDENCE_PRESENT, abstained=True,
                    acc_method="abstain_rule", citation_ok=None, **base)

    verdict = keyword_match(p["answer"], gold_short)
    method = "keyword"
    if verdict == "ambiguous":
        k = Judge.key(question, gold_short, p["answer"])
        if collect is not None:
            collect[k] = (question, gold_short, p["answer"])
        verdict = verdicts.get(k, "review")
        method = "judge" if verdict != "review" else "pending"

    cit = citation_ok(p["basis"], gold_units)

    if verdict == "yes":
        state, correct = "correct", True
    elif verdict == "partial":
        state, correct = "partial", True
    elif verdict == "no":
        state = "overconfident" if conf_high else "hedged_wrong"
        correct = False
    else:
        state, correct = "review", None

    return dict(state=state, correct=correct, abstained=False,
                acc_method=method, citation_ok=cit, **base)


# ---------------------------------------------------------------- 조건 메타

def load_condition_meta(covdirs: list[str]) -> dict:
    """조건별 실제 커버리지·문자비율. 짝지음 대조에 필요하다."""
    meta = {}
    for d in covdirs:
        mf = Path(d) / "coverage_manifest.json"
        if not mf.exists():
            continue
        for c in json.loads(mf.read_text(encoding="utf-8"))["conditions"]:
            key = f"cov{c['target_cov']}_{c['strategy']}_{c['unit']}"
            meta[key] = dict(cov=c["actual_cov"], char=c["char_ratio"] * 100,
                             mode=c.get("mode", "coverage"))
    return meta


# ---------------------------------------------------------------- 메인

def main() -> int:
    a = sys.argv
    if len(a) < 3:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    src = Path(a[1])
    slots = {s["qid"]: s for s in load(a[2])}
    out = Path(opt("--out", "grade_out"))
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(src.glob("responses_*.jsonl")) if src.is_dir() else [src]
    cb = opt("--closedbook", None)
    if cb and Path(cb).exists():
        files += sorted(Path(cb).glob("responses_*.jsonl"))
    if not files:
        print(f"응답 파일이 없습니다: {src}")
        return 1

    status = {}
    sp = opt("--status", "status_content.json")
    if Path(sp).exists():
        status = json.loads(Path(sp).read_text(encoding="utf-8"))
        print(f"내용기준 상태 사용: {sp} ({len(status)}조건)")
    else:
        print(f"! {sp} 없음 — 응답에 실린 q_status(단위기준)를 씁니다.")

    cmeta = load_condition_meta(opt("--covdirs",
                                    "cov_core,cov_periph,cov_random,cov_vol").split(","))
    judge = Judge(opt("--judges", "").split(","),
                  Path(opt("--judge-cache", str(out / "judge_cache.json"))),
                  urls=opt("--judge-urls", "").split(",") if "--judge-urls" in a
                  else None)
    if judge.models:
        print(f"판정자 다수결: {', '.join(judge.models)}")
    else:
        print("! 판정자 미지정 — 애매한 건은 review 로 남습니다 (--judges)")

    # 1단계: 키워드로 가릴 수 있는 것을 가르고, 애매한 것을 모은다
    items, collect = [], {}
    for f in files:
        rows = load(f)
        for r in rows:
            slot = slots.get(r["qid"])
            if not slot:
                continue
            cond = r.get("condition", "")
            qs = (status.get(cond, {}).get(r["qid"], {}).get("q_status_content")
                  or r.get("q_status", "full"))
            items.append((r, slot, qs, cond))
            classify(r, slot, qs, {}, collect)
        print(f"  {f.name}: {len(rows)}건")

    # 2단계: 판정자를 모델별로 묶어 일괄 처리 (모델 재적재 방지)
    verdicts = judge.run_batch(collect) if judge.models else {}

    # 3단계: 판정 결과를 반영해 최종 분류
    graded = []
    for r, slot, qs, cond in items:
        g = classify(r, slot, qs, verdicts)
        g.update(qid=r["qid"], condition=cond, model=r.get("model", ""),
                 arm=r.get("arm", "rag"), cov=r.get("cov"),
                 strategy=r.get("strategy", ""), q_status=qs,
                 q_status_unit=r.get("q_status"),
                 level=slot.get("level"), recall=r.get("recall_at_k"))
        graded.append(g)
    judge.save()

    with open(out / "graded.jsonl", "w", encoding="utf-8") as f:
        for g in graded:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    # ------------------------------------------------ 집계
    cells = defaultdict(Counter)
    conf_acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    conf_dist = defaultdict(Counter)
    cite = defaultdict(lambda: [0, 0])
    for g in graded:
        key = (g["model"], g["condition"])
        cells[key][g["state"]] += 1
        conf_dist[key][g["confidence"] or f"[{g['conf_parse']}]"] += 1
        # 캘리브레이션은 '답을 한 것' 만 센다. 기권을 넣으면
        # '올바른 기권' 이 정답으로 섞여 값이 부풀려진다.
        # (8b 는 기권할 때도 확신도 '높음' 이라 특히 심하게 왜곡된다)
        if (g["state"] in ("correct", "partial", "overconfident", "hedged_wrong")
                and g["correct"] is not None and g["confidence"]):
            c = "high" if g["confidence"] in CONF_HIGH else "low"
            conf_acc[key][c][1] += 1
            conf_acc[key][c][0] += 1 if g["correct"] else 0
        if g.get("citation_ok") is not None:
            cite[key][1] += 1
            cite[key][0] += 1 if g["citation_ok"] else 0

    def srt(items):
        return sorted(items, key=lambda x: (x[0][0], cmeta.get(x[0][1], {}).get("char", 999)))

    n_rev = sum(1 for g in graded if g["state"] == "review")
    n_err = sum(1 for g in graded if g["state"] == "error")
    n_bad = sum(1 for g in graded if g["conf_parse"] != "ok")

    L = ["# 채점 결과", "",
         f"- 응답 {len(graded)}개 / 판정보류 {n_rev} / 생성실패 {n_err} "
         f"/ 확신도 파싱실패 {n_bad}",
         f"- 판정자 호출 {judge.n_call}회 (캐시 적중 {judge.n_hit}회)", "",
         "확신도 파싱실패에는 모델이 '<높음|중간|낮음|모름>' 템플릿을 그대로",
         "출력한 경우가 포함된다. 이를 '높음' 으로 세면 분포가 왜곡되므로",
         "따로 집계하고 캘리브레이션에서 제외한다.", "",
         "## 1. 조건별 상태 분포", "",
         "| 모델 | 조건 | 커버리지 | 문자% | 정답 | 기권 | **과신오답** | 신중오답 | 부분 | 보류 | 정확도 | 과신오답률 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (model, cond), c in srt(cells.items()):
        tot = sum(c.values())
        m = cmeta.get(cond, {})
        judged = tot - c["review"] - c["error"]
        acc = (c["correct"] + c["partial"] * 0.5) / judged * 100 if judged else 0
        oc = c["overconfident"] / tot * 100 if tot else 0
        L.append(f"| {model} | {cond} | {m.get('cov','-')} | "
                 f"{m.get('char',0):.1f} | {c['correct']} | {c['honest_abstain']} | "
                 f"**{c['overconfident']}** | {c['hedged_wrong']} | {c['partial']} | "
                 f"{c['review']} | {acc:.0f}% | {oc:.0f}% |")

    L += ["", "## 2. 캘리브레이션 (확신도별 실제 정답률 — 기권 제외)", "",
          "**답을 한 응답만** 집계한다. 기권을 넣으면 '올바른 기권' 이",
          "정답으로 섞여 값이 부풀려진다(8b 는 기권 시에도 확신도 '높음').",
          "커버리지가 낮아질수록 '높음' 정답률이 떨어지면",
          "'모른다는 걸 모른다' 의 정량 증거다. 괄호는 표본 수.", "",
          "| 모델 | 조건 | 문자% | 높음/중간 정답률 | 낮음/모름 정답률 | 갭 |",
          "|---|---|---|---|---|---|"]
    for (model, cond), d in srt(conf_acc.items()):
        h, lo = d["high"], d["low"]
        ha = h[0] / h[1] * 100 if h[1] else 0
        la = lo[0] / lo[1] * 100 if lo[1] else 0
        L.append(f"| {model} | {cond} | {cmeta.get(cond,{}).get('char',0):.1f} | "
                 f"{ha:.0f}% ({h[1]}) | {la:.0f}% ({lo[1]}) | {ha-la:+.0f} |")

    L += ["", "## 3. 확신도 분포 — 폐쇄북 대조", "",
          "검색 컨텍스트가 없을 때 분산이 생기면, 척도는 살아있고",
          "검색 결과가 과신을 유발한 것이다.", "",
          "| 모델 | 조건 | " + " | ".join(CONF_ORDER) + " | 파싱실패 |",
          "|---|---|---|---|---|---|---|"]
    for (model, cond), c in sorted(conf_dist.items(),
                                   key=lambda x: (x[0][0], x[0][1] != "closedbook",
                                                  x[0][1])):
        bad = sum(v for k, v in c.items() if k.startswith("["))
        L.append(f"| {model} | {cond} | " +
                 " | ".join(str(c.get(k, 0)) for k in CONF_ORDER) +
                 f" | {bad} |")

    L += ["", "## 4. 짝지음 대조 (문자비율은 비슷, 커버리지만 다름)", "",
          "이 표가 'Coverage > Volume' 의 직접 증거다.", "",
          "| 모델 | 조건 | 커버리지 | 문자% | 기권 | 과신오답 | 정확도 |",
          "|---|---|---|---|---|---|---|"]
    pairs = [(k, v) for k, v in cells.items() if k[1] in cmeta]
    for (model, cond), c in sorted(pairs, key=lambda x: (x[0][0],
                                                         cmeta[x[0][1]]["char"])):
        m = cmeta[cond]
        tot = sum(c.values())
        judged = tot - c["review"] - c["error"]
        acc = (c["correct"] + c["partial"] * 0.5) / judged * 100 if judged else 0
        L.append(f"| {model} | {cond} | {m['cov']} | {m['char']:.1f} | "
                 f"{c['honest_abstain']} | {c['overconfident']} | {acc:.0f}% |")

    L += ["", "## 5. 인용 정확도", "",
          "| 모델 | 조건 | 인용한 답 | 인용 정확 | 비율 |", "|---|---|---|---|---|"]
    for (model, cond), (ok, tot) in srt(cite.items()):
        L.append(f"| {model} | {cond} | {tot} | {ok} | "
                 f"{ok/tot*100 if tot else 0:.0f}% |")

    L += ["", "## 다음", "",
          "1. 보류(review)가 남아 있으면 --judges 로 다수결 판정자를 붙인다.",
          "2. 1번 표의 과신오답률과 2번 표의 갭을 문자비율 축으로 플롯한다.",
          "3. 4번 표에서 문자비율이 비슷한 쌍을 골라 본문 그림으로 쓴다.",
          "4. q_status='surrogate' 문항만 따로 집계해, 문서 제거가 지식",
          "   제거가 아니었던 경우의 영향을 확인한다."]

    (out / "grade_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"\n채점 {len(graded)}개 | 보류 {n_rev} | 실패 {n_err} | 확신도 파싱실패 {n_bad}")
    print(f"판정자 호출 {judge.n_call} (캐시 {judge.n_hit})")
    print(f"-> {out}/graded.jsonl, grade_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
