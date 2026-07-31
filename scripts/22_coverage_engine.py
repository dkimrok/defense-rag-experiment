#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
커버리지 조작 엔진  [v2]

원본 코퍼스에서 문서/조를 제거해, 조건이 서로 다른 변형 코퍼스를 만든다.

v2 변경점
  (1) refs.jsonl 중첩 스키마 파싱 수정.  ★가장 중요★
      실제 스키마는 인용 주체 unit 이 레코드이고, 인용 간선은 그 안의
      refs 배열에 있다. v1 은 최상위에서 target_name 을 찾아 매칭률 0% 였고,
      그 결과 모든 문서의 피인용도가 0 → core/periph/random 정렬이
      전부 동순위가 되어 세 전략이 완전히 동일한 파일을 만들었다.
      (MD5 일치로 확인됨. 전략 축이 통째로 무효였다.)
  (2) 문서명 정규화 강화. 「」『』 제거, 선행 기관명 괄호 제거 보조 인덱스.
      '(방위사업청) 보직관리규정' 과 '「보직관리규정」' 이 매칭되게 한다.
  (3) 인용 매칭 진단 출력. 매칭률·gold 문서 피인용 분포를 찍고,
      core/periph 인데 분포가 축퇴면 경고한다. 조용히 무효가 되지 않게 한다.
  (4) --mode volume 추가. 아래 참조.

두 가지 조작 모드
  --mode coverage (기본)
      gold 를 제거해 '답할 수 있는 문항 비율'을 낮춘다. 문자수도 같이 준다.
      즉 커버리지와 분량이 교락(confound)된다.
  --mode volume
      gold 를 하나도 건드리지 않고, gold 비보유 문서만 제거해 문자수만 낮춘다.
      커버리지는 100% 로 고정된다.
      두 모드를 겹쳐 그리면 x축=문자비율일 때 두 곡선이 갈라지고,
      x축=커버리지일 때 겹친다. 이것이 'Coverage > Volume' 의 직접 증거다.
      회귀 공변량 통제보다 훨씬 강한 논증이 된다.

제거 단위 (--unit)
  jo   : gold 가 가리키는 조만 제거 (정밀)
  doc  : 그 조가 속한 문서 전체 제거 (배치 현실적, 부수 제거 발생)

제거 전략 (--strategy)
  core     : 피인용 많은 문서부터
  periph   : 피인용 적은 문서부터
  random   : 무작위
  tier_up  : 상위법(T1~T3) 먼저 (coverage 모드 전용)

출력 (out_dir/)
  [coverage] corpus_cov{NN}_{strategy}_{unit}.jsonl
  [volume]   corpus_cov100_vol{NN}_{unit}.jsonl
             (커버리지는 100% 이므로 cov100 으로 적는다. NN 은 목표 문자비율.
              25/29 의 기존 파일명 정규식이 그대로 먹도록 맞춘 형식이다.)
  coverage_manifest.json / coverage_report.md

사용법
  py 22_coverage_engine.py corpus_final.jsonl question_final.jsonl \\
      --unit doc --strategy core --refs refs.jsonl --out cov_core
  py 22_coverage_engine.py corpus_final.jsonl question_final.jsonl \\
      --mode volume --unit doc --strategy periph --refs refs.jsonl \\
      --levels 100,85,70,55,40,30 --out cov_vol
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20260721
DEFAULT_LEVELS = [100, 85, 70, 55, 40, 25, 10, 0]
DEFAULT_VOL_LEVELS = [100, 85, 70, 55, 40, 30]

RE_BRACKET = re.compile(r'[「」『』\[\]<>]')
RE_LEADPAREN = re.compile(r'^\s*\([^)]*\)\s*')
RE_DROP = re.compile(r'[ㆍ·・()\s]')


def load(p: str) -> list[dict]:
    return [json.loads(l) for l in
            Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def nkey(s: str) -> str:
    """문서명 정규화. 「」 등 인용부호와 구두점·공백 제거."""
    return RE_DROP.sub('', RE_BRACKET.sub('', s or ''))


def nkey_alt(s: str) -> str:
    """선행 기관명 괄호까지 제거한 보조 키. '(방위사업청) 보직관리규정' -> '보직관리규정'"""
    return RE_DROP.sub('', RE_LEADPAREN.sub('', RE_BRACKET.sub('', s or '')))


# ---------------------------------------------------------------- 피인용도

def citation_counts(refs_path: str | None,
                    corpus: list[dict]) -> tuple[dict[str, int], dict]:
    """문서별 피인용 횟수 + 매칭 진단.

    refs.jsonl 스키마(실측):
      {"doc_id":..., "unit_id":..., "n_refs":2,
       "refs":[{"kind":"full","target_name":"군인사법","target_tier":"T1_법률",...}, ...]}
    인용 간선은 refs 배열 안에 있다. 최상위에는 target_name 이 없다.
    """
    cit: dict[str, int] = defaultdict(int)
    diag = dict(file=refs_path, records=0, edges=0, matched=0,
                docs_with_citation=0, unmatched_top=[])
    if not (refs_path and Path(refs_path).exists()):
        return cit, diag

    idx, idx_alt = {}, {}
    for u in corpus:
        dn = u.get("doc_name", "")
        idx.setdefault(nkey(dn), u.get("doc_id"))
        idx_alt.setdefault(nkey_alt(dn), u.get("doc_id"))

    miss = Counter()
    for r in load(refs_path):
        diag["records"] += 1
        edges = r.get("refs")
        if edges is None:                      # 평면 스키마 폴백
            edges = [r] if r.get("target_name") else []
        for e in edges:
            if not isinstance(e, dict):
                continue
            diag["edges"] += 1
            name = e.get("target_name", "")
            did = idx.get(nkey(name)) or idx_alt.get(nkey_alt(name))
            if did:
                cit[did] += 1
                diag["matched"] += 1
            elif name:
                miss[name] += 1

    diag["docs_with_citation"] = len(cit)
    diag["unmatched_top"] = miss.most_common(15)
    return cit, diag


# ---------------------------------------------------------------- 엔진

class CoverageEngine:
    def __init__(self, corpus_path: str, slots_path: str,
                 refs_path: str | None, seed: int):
        self.corpus = load(corpus_path)
        self.slots = load(slots_path)
        self.seed = seed
        self.rng = random.Random(seed)
        self._order_cache: dict[str, list] = {}
        self._pool_cache: dict[str, list] = {}
        self.cit, self.cit_diag = citation_counts(refs_path, self.corpus)

        self.by_id = {u["unit_id"]: u for u in self.corpus}
        self.doc_units: dict[str, set] = defaultdict(set)
        self.doc_chars: dict[str, int] = defaultdict(int)
        for u in self.corpus:
            self.doc_units[u["doc_id"]].add(u["unit_id"])
            self.doc_chars[u["doc_id"]] += u.get("char_len", 0)
        self.total_chars = sum(u.get("char_len", 0) for u in self.corpus)

        self.q_required: dict[str, set] = {}
        self.q_all_gold: dict[str, set] = {}
        for s in self.slots:
            req, allg = set(), set()
            for g in s.get("gold_evidence", []):
                uid = g.get("unit_id")
                if not uid:
                    continue
                allg.add(uid)
                if g.get("necessity", "required") == "required":
                    req.add(uid)
            self.q_required[s["qid"]] = req or allg
            self.q_all_gold[s["qid"]] = allg

        self.answerable_qids = [s["qid"] for s in self.slots
                                if s.get("answerable", True)
                                and self.q_required.get(s["qid"])]

        # gold 를 담고 있는 문서 = 분량 모드에서 절대 건드리면 안 되는 집합
        self.gold_docs = {self.by_id[u]["doc_id"]
                          for q in self.answerable_qids
                          for u in self.q_all_gold[q] if u in self.by_id}

    # -------- 인용 진단 보고
    def report_citation(self, strategy: str) -> None:
        d = self.cit_diag
        if not d["file"]:
            print("피인용 정보: 없음 (--refs 미지정)")
        else:
            pct = d["matched"] / d["edges"] * 100 if d["edges"] else 0
            print(f"피인용 정보: {d['file']} | 레코드 {d['records']:,} "
                  f"인용간선 {d['edges']:,} | 매칭 {d['matched']:,} ({pct:.1f}%) "
                  f"→ 문서 {d['docs_with_citation']}종")
            if d["unmatched_top"]:
                head = ", ".join(f"{n}({c})" for n, c in d["unmatched_top"][:5])
                print(f"  미매칭 상위: {head}")

        vals = {dd: self.cit.get(dd, 0) for dd in sorted(self.gold_docs)}
        distinct = len(set(vals.values()))
        nz = sum(1 for v in vals.values() if v > 0)
        print(f"gold 보유 문서 {len(vals)}종 | 피인용>0 {nz}종 | 서로 다른 값 {distinct}종")
        if strategy in ("core", "periph") and distinct < 2:
            print("\n*** 경고: gold 문서의 피인용도가 모두 같습니다. ***")
            print("    core/periph 정렬이 동순위가 되어 random 과 같은 결과가 나옵니다.")
            print("    --refs 경로/스키마/문서명 매칭을 먼저 해결하십시오.\n")

    # -------- 제거 순서
    def removal_order(self, strategy: str) -> list[str]:
        # 전략별로 단 한 번만 계산해 캐시한다.
        # 레벨마다 다시 셔플하면 변형들이 중첩되지 않아, 커버리지를 낮췄는데
        # 코퍼스가 커지는 비단조가 생긴다(실측: cov10 86.2% -> cov0 87.7%).
        # 스윕은 '제거 깊이'만 달라져야 하므로 순서를 고정한다.
        if strategy in self._order_cache:
            return self._order_cache[strategy]
        gold_units = sorted({uid for q in self.answerable_qids
                             for uid in self.q_required[q]})

        def cit_of(uid: str) -> int:
            return self.cit.get(self.by_id[uid]["doc_id"], 0)

        def tier_rank(uid: str) -> int:
            t = self.by_id[uid].get("tier", "")
            return {"T1_법률": 0, "T2_대통령령": 1,
                    "T3_부령": 2, "T4_행정규칙": 3}.get(t, 4)

        random.Random(self.seed).shuffle(gold_units)   # 호출 순서 비의존
        if strategy == "core":
            gold_units.sort(key=lambda u: -cit_of(u))
        elif strategy == "periph":
            gold_units.sort(key=lambda u: cit_of(u))
        elif strategy == "tier_up":
            gold_units.sort(key=tier_rank)
        self._order_cache[strategy] = gold_units
        return gold_units

    # -------- 커버리지 모드
    def make_variant(self, target_cov: int, strategy: str, unit: str) -> dict:
        order = self.removal_order(strategy)
        removed_units: set[str] = set()
        removed_docs: set[str] = set()
        n_ans = len(self.answerable_qids)
        target_full = int(round(n_ans * target_cov / 100))

        def full_answerable() -> int:
            return sum(1 for q in self.answerable_qids
                       if self.q_required[q] and
                       not (self.q_required[q] & removed_units))

        for uid in order:
            if full_answerable() <= target_full:
                break
            if unit == "doc":
                did = self.by_id[uid]["doc_id"]
                if did not in removed_docs:
                    removed_docs.add(did)
                    removed_units |= self.doc_units[did]
            else:
                removed_units.add(uid)

        return self._finish(removed_units, removed_docs, target_cov,
                            strategy, unit, mode="coverage")

    # -------- 분량 모드
    def make_volume_variant(self, target_char_pct: int, strategy: str,
                            unit: str) -> dict:
        """gold 비보유 문서만 제거해 문자비율을 target 까지 낮춘다.
        gold 는 절대 건드리지 않으므로 커버리지는 100% 로 고정된다."""
        if strategy in self._pool_cache:
            pool = self._pool_cache[strategy]
        else:
            pool = sorted(d for d in self.doc_units if d not in self.gold_docs)
            random.Random(self.seed).shuffle(pool)
            if strategy == "core":
                pool.sort(key=lambda d: -self.cit.get(d, 0))
            elif strategy == "periph":
                pool.sort(key=lambda d: self.cit.get(d, 0))
            self._pool_cache[strategy] = pool

        floor_chars = sum(self.doc_chars[d] for d in self.gold_docs)
        floor_pct = floor_chars / self.total_chars * 100
        removed_units: set[str] = set()
        removed_docs: set[str] = set()
        kept_chars = self.total_chars
        for d in pool:
            if kept_chars / self.total_chars * 100 <= target_char_pct:
                break
            removed_docs.add(d)
            removed_units |= self.doc_units[d]
            kept_chars -= self.doc_chars[d]

        v = self._finish(removed_units, removed_docs, 100, f"vol{target_char_pct:03d}",
                         unit, mode="volume")
        v["target_char_pct"] = target_char_pct
        v["char_floor_pct"] = round(floor_pct, 1)
        return v

    def _finish(self, removed_units, removed_docs, target_cov, strategy,
                unit, mode) -> dict:
        kept = [u for u in self.corpus if u["unit_id"] not in removed_units]
        status = {}
        for q in self.answerable_qids:
            req = self.q_required[q]
            gone = req & removed_units
            status[q] = "full" if not gone else ("none" if gone == req else "partial")
        sc = Counter(status.values())
        kc = sum(u.get("char_len", 0) for u in kept)
        return dict(
            mode=mode, target_cov=target_cov, strategy=strategy, unit=unit,
            removed_unit_count=len(removed_units),
            removed_doc_count=len(removed_docs),
            kept_unit_count=len(kept), kept_chars=kc,
            char_ratio=round(kc / self.total_chars, 4),
            full=sc["full"], partial=sc["partial"], none=sc["none"],
            actual_cov=round(sc["full"] / len(self.answerable_qids) * 100, 1),
            q_status=status, _kept=kept)


# ---------------------------------------------------------------- 실행

def main(corpus_path: str, slots_path: str, unit: str, strategy: str,
         levels: list[int] | None, refs_path: str | None, seed: int,
         out: str, mode: str) -> int:
    eng = CoverageEngine(corpus_path, slots_path, refs_path, seed)
    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)
    if levels is None:
        levels = DEFAULT_VOL_LEVELS if mode == "volume" else DEFAULT_LEVELS

    print(f"코퍼스 {len(eng.corpus):,} unit / 문서 {len(eng.doc_units)}종 "
          f"/ {eng.total_chars:,}자")
    print(f"답 가능 문항 {len(eng.answerable_qids)}개 | 모드={mode} "
          f"전략={strategy} 단위={unit}")
    eng.report_citation(strategy)
    if mode == "volume":
        fl = sum(eng.doc_chars[d] for d in eng.gold_docs) / eng.total_chars * 100
        print(f"gold 비보유 문서 {len(eng.doc_units)-len(eng.gold_docs)}종 제거 가능 "
              f"| 문자비율 하한 {fl:.1f}%")
    print()

    manifest = dict(source=corpus_path, mode=mode, unit=unit, strategy=strategy,
                    seed=seed, total_chars=eng.total_chars,
                    n_answerable=len(eng.answerable_qids),
                    citation_diag=eng.cit_diag, conditions=[])

    for lv in levels:
        if mode == "volume":
            v = eng.make_volume_variant(lv, strategy, unit)
            fn = outd / f"corpus_cov100_vol{lv:03d}_{unit}.jsonl"
        else:
            v = eng.make_variant(lv, strategy, unit)
            fn = outd / f"corpus_cov{lv:03d}_{strategy}_{unit}.jsonl"
        with open(fn, "w", encoding="utf-8") as f:
            for u in v["_kept"]:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
        v.pop("_kept")
        v["file"] = fn.name
        manifest["conditions"].append(v)
        tag = f"문자 {lv:3}%" if mode == "volume" else f"cov {lv:3}%"
        print(f"  {tag} → 커버리지 {v['actual_cov']:5}% | "
              f"완전 {v['full']:3} 부분 {v['partial']:3} 불가 {v['none']:3} | "
              f"문자 {v['char_ratio']*100:5.1f}% | {fn.name}")

    (outd / "coverage_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    L = ["# 조작 매니페스트", "",
         f"- 원본 {corpus_path} / {eng.total_chars:,}자 / 답가능 문항 "
         f"{len(eng.answerable_qids)}개",
         f"- 모드 {mode} · 전략 {strategy} · 단위 {unit} · seed {seed}", "",
         "| 목표 | 커버리지 | 완전 | 부분 | 불가 | 문자비율 | 제거doc | 파일 |",
         "|---|---|---|---|---|---|---|---|"]
    for v in manifest["conditions"]:
        t = v.get("target_char_pct", v["target_cov"])
        L.append(f"| {t}% | {v['actual_cov']}% | {v['full']} | {v['partial']} | "
                 f"{v['none']} | {v['char_ratio']*100:.1f}% | "
                 f"{v['removed_doc_count']} | {v['file']} |")
    if mode == "volume":
        L += ["", "분량 모드는 gold 를 제거하지 않으므로 커버리지가 100% 로 고정된다.",
              "커버리지 모드 곡선과 겹쳐 그리면, 같은 문자비율에서 성능이 갈린다.",
              "이것이 'Coverage > Volume' 의 직접 실험 증거다."]
    (outd / "coverage_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"\n-> {out}/ 변형 {len(levels)}개 + manifest + report")
    return 0


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 3:
        print(__doc__)
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        lv = opt("--levels", None)
        sys.exit(main(a[1], a[2], opt("--unit", "jo"), opt("--strategy", "core"),
                      [int(x) for x in lv.split(",")] if lv else None,
                      opt("--refs", None), int(opt("--seed", str(SEED))),
                      opt("--out", "cov_out"), opt("--mode", "coverage")))
