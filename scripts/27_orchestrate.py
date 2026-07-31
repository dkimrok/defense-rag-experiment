#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
체크포인트 오케스트레이터 — 전체 실험 자동 순회 + 재개

변형 코퍼스 × 모델의 모든 조합을 순회하며 RAG 생성을 돌린다.
Kaggle/Colab 은 세션이 끊기므로, 이미 끝난 조건은 건너뛰고 남은 것만
이어서 돌리는 것이 핵심이다. 실행할 때마다 진행 상황을 파일에 남긴다.

동작
  1. cov 디렉터리들에서 변형 코퍼스 목록을 모은다.
  2. (변형 × 모델) 조합마다 응답 파일이 이미 있으면 건너뛴다.
     응답 파일이 완결(문항 수 일치)이면 완료로 본다.
  3. 25_rag_run 을 서브프로세스로 호출해 생성한다.
  4. progress.json 에 각 조건의 상태(done/failed/pending)를 기록한다.
  5. 중간에 죽어도 다시 실행하면 pending 부터 재개한다.

재개 판정
  응답 파일의 줄 수가 문항 수와 같고, '[생성 실패' 가 없으면 done.
  일부만 있거나 실패가 섞이면 그 조건을 다시 돌린다(덮어씀).

사용법
  py 27_orchestrate.py index question_final.jsonl \\
      --cov-dirs cov_core,cov_periph,cov_random \\
      --models qwen3:8b,qwen3:4b \\
      --k 5 --out runs

  # 특정 전략/커버리지만
  py 27_orchestrate.py index question_final.jsonl \\
      --cov-dirs cov_core --models qwen3:4b --covs 100,70,40,10,0 --k 5 --out runs

  # 진행 상황만 보기
  py 27_orchestrate.py --status --out runs

중복 조건
  run_plan.json(30 이 생성)에 같은 코퍼스가 여러 이름으로 잡힌 목록이 있다.
  temperature 0.0 이므로 동일 코퍼스는 동일 응답이다. 대표 하나만 돌리고
  나머지는 결과를 복제한다(레코드에 aliased_from 을 남긴다).
  --run-plan '' 로 끄면 전부 실제로 돌린다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
RAG_SCRIPT = str(HERE / "25_rag_run.py")


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def n_questions(slots_path: str) -> int:
    return sum(1 for s in load_jsonl(Path(slots_path))
               if (s.get("question_ko") or "").strip())


def variant_files(cov_dirs: list[str], covs: list[int] | None) -> list[Path]:
    files = []
    for d in cov_dirs:
        dd = Path(d)
        if not dd.exists():
            print(f"  ! 변형 디렉터리 없음: {d}")
            continue
        for f in sorted(dd.glob("corpus_cov*.jsonl")):
            if covs is not None:
                import re
                m = re.search(r'cov(\d+)_', f.name)
                if m and int(m.group(1)) not in covs:
                    continue
            files.append(f)
    return files


def safe_name(s: str) -> str:
    """모델 이름의 슬래시·콜론을 파일명 안전 문자로 바꾼다."""
    import re as _r
    return _r.sub(r'[^A-Za-z0-9._-]', '-', s)


def _key(p) -> tuple:
    """OS 별 경로 구분자 차이를 흡수해 (디렉터리명, 파일명) 으로 비교한다.
    run_plan.json 은 Windows 에서 만들어져 역슬래시가 들어 있을 수 있다."""
    q = str(p).replace("\\", "/")
    parts = q.split("/")
    return (parts[-2] if len(parts) > 1 else "", parts[-1])


def load_run_plan(path: str | None) -> dict:
    """중복 변형 -> 대표 변형 매핑. temperature 0.0 이면 동일 코퍼스는
    동일 검색·동일 프롬프트·동일 응답이므로 한 번만 돌리면 된다."""
    if not path or not Path(path).exists():
        return {}
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    alias = {}
    for grp in plan.get("duplicate_groups", []):
        canon = grp[0]
        for dup in grp[1:]:
            alias[_key(dup)] = _key(canon)
    return alias


def response_path(out: str, variant: Path, model: str) -> Path:
    import re
    m = re.search(r'(cov\d+_\w+_\w+)\.jsonl', variant.name)
    tag = m.group(1) if m else variant.stem
    return Path(out) / f"responses_{tag}_{safe_name(model)}.jsonl"


def is_done(resp: Path, nq: int) -> bool:
    if not resp.exists():
        return False
    rows = load_jsonl(resp)
    if len(rows) < nq:
        return False
    # 생성 실패가 섞였으면 미완으로 본다.
    # 25 v2 는 실패를 error 필드로 분리하고 raw_answer 를 None 으로 둔다.
    # 구버전 판정('[생성 실패' 문자열)만 보면 실패한 실행이 전부 done 으로
    # 넘어간다. 두 형식을 모두 본다.
    fail = 0
    for r in rows:
        if r.get("error"):
            fail += 1
        elif not str(r.get("raw_answer") or "").strip():
            fail += 1
        elif str(r.get("raw_answer", "")).startswith("[생성 실패"):
            fail += 1
    return fail == 0


def manifest_of(variant: Path) -> Path | None:
    mf = variant.parent / "coverage_manifest.json"
    return mf if mf.exists() else None


def load_progress(out: str) -> dict:
    p = Path(out) / "progress.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_progress(out: str, prog: dict) -> None:
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "progress.json").write_text(
        json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")


def show_status(out: str) -> None:
    prog = load_progress(out)
    if not prog:
        print("진행 기록이 없습니다.")
        return
    done = sum(1 for v in prog.values() if v.get("status") == "done")
    fail = sum(1 for v in prog.values() if v.get("status") == "failed")
    pend = sum(1 for v in prog.values() if v.get("status") == "pending")
    print(f"전체 {len(prog)} 조건 / 완료 {done} · 실패 {fail} · 대기 {pend}")
    for k, v in sorted(prog.items()):
        mark = {"done": "✓", "failed": "✗", "pending": "·"}.get(v.get("status"), "?")
        dt = v.get("seconds")
        extra = f" ({dt:.0f}s)" if dt else ""
        print(f"  {mark} {k}{extra}")


def main(index_dir: str, slots_path: str, cov_dirs: list[str],
         models: list[str], covs: list[int] | None, k: int, alpha: float,
         out: str, think: bool, timeout: int, num_ctx: int, num_predict: int,
         run_plan: str | None, ollama_url: str = "") -> None:
    nq = n_questions(slots_path)
    variants = variant_files(cov_dirs, covs)

    # 중복 변형은 대표 하나만 돌리고, 끝난 뒤 결과를 복제한다.
    alias = load_run_plan(run_plan)
    skipped_dup = [v for v in variants if _key(v) in alias]
    if alias:
        variants = [v for v in variants if _key(v) not in alias]
        print(f"중복 변형 {len(skipped_dup)}개는 대표 조건으로 갈음합니다 "
              f"({run_plan})")

    jobs = [(v, m) for v in variants for m in models]

    prog = load_progress(out)
    print(f"문항 {nq}개 | 변형 {len(variants)}개 × 모델 {len(models)}개 "
          f"= {len(jobs)} 조건")
    print(f"출력 {out}/ | k={k} alpha={alpha} think={think} timeout={timeout}"
          + (f" | 서버 {ollama_url}" if ollama_url else "") + "\n")

    todo = []
    for v, m in jobs:
        resp = response_path(out, v, m)
        key = resp.stem
        if is_done(resp, nq):
            prog[key] = dict(status="done", file=resp.name,
                             seconds=prog.get(key, {}).get("seconds"))
            continue
        todo.append((v, m, resp, key))

    save_progress(out, prog)
    done_already = sum(1 for v in prog.values() if v.get("status") == "done")
    print(f"이미 완료 {done_already} 조건 (건너뜀) | 이번에 돌릴 것 {len(todo)} 조건\n")

    for i, (v, m, resp, key) in enumerate(todo, 1):
        mf = manifest_of(v)
        cmd = [sys.executable, RAG_SCRIPT, index_dir, slots_path,
               "--variant", str(v), "--model", m, "--k", str(k),
               "--alpha", str(alpha), "--out", out, "--timeout", str(timeout),
               "--num-ctx", str(num_ctx), "--num-predict", str(num_predict)]
        if ollama_url:
            cmd += ["--ollama-url", ollama_url]
        if mf:
            cmd += ["--manifest", str(mf)]
        if think:
            cmd += ["--think"]

        print(f"[{i}/{len(todo)}] {key}")
        prog[key] = dict(status="pending", file=resp.name)
        save_progress(out, prog)

        t0 = time.time()
        try:
            r = subprocess.run(cmd, timeout=timeout * nq + 300)
            dt = time.time() - t0
            if r.returncode == 3:
                # 25 가 BM25/인덱스 문제로 중단한 경우. 재시도해도 같으므로
                # 즉시 전체를 멈춘다(수십 조건을 헛돌리지 않도록).
                prog[key] = dict(status="failed", file=resp.name,
                                 note="인덱스/BM25 오류(종료코드 3)")
                save_progress(out, prog)
                print("     ! 인덱스 또는 BM25 문제로 중단합니다. "
                      "pip install rank-bm25 후 다시 실행하십시오.")
                return
            if is_done(resp, nq):
                prog[key] = dict(status="done", file=resp.name, seconds=round(dt))
                print(f"     완료 ({dt:.0f}s)\n")
            else:
                prog[key] = dict(status="failed", file=resp.name,
                                 seconds=round(dt), note="일부 실패 또는 미완")
                print(f"     ! 미완 — 재실행 시 다시 시도\n")
        except subprocess.TimeoutExpired:
            prog[key] = dict(status="failed", file=resp.name,
                             note="전체 타임아웃")
            print(f"     ! 타임아웃\n")
        except Exception as e:                              # noqa: BLE001
            prog[key] = dict(status="failed", file=resp.name, note=str(e))
            print(f"     ! 오류: {e}\n")
        save_progress(out, prog)

    # 중복 변형의 응답 파일을 대표 결과에서 복제한다.
    # 코퍼스가 바이트 단위로 같고 temperature 0.0 이므로 응답이 동일하다.
    # 조건 표시만 각자 이름으로 바꾸고, 어디서 복제됐는지 남긴다.
    n_alias = 0
    for v in skipped_dup:
        canon_dir, canon_name = alias[_key(v)]
        canon = Path(canon_dir) / canon_name
        for m in models:
            src = response_path(out, canon, m)
            dst = response_path(out, v, m)
            if not src.exists() or dst.exists():
                continue
            import re as _re
            mm = _re.search(r'cov(\d+)_(\w+?)_(\w+)\.jsonl', v.name)
            rows = load_jsonl(src)
            for r in rows:
                if mm:
                    r["cov"] = int(mm.group(1))
                    r["strategy"] = mm.group(2)
                    r["unit"] = mm.group(3)
                    r["condition"] = f"cov{mm.group(1).lstrip('0') or '0'}_" \
                                     f"{mm.group(2)}_{mm.group(3)}"
                r["aliased_from"] = src.name
            with open(dst, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            prog[dst.stem] = dict(status="done", file=dst.name,
                                  note=f"복제: {src.name}")
            n_alias += 1
    if n_alias:
        save_progress(out, prog)
        print(f"\n중복 조건 {n_alias}개를 대표 결과에서 복제했습니다.")

    done = sum(1 for v in prog.values() if v.get("status") == "done")
    fail = sum(1 for v in prog.values() if v.get("status") == "failed")
    print(f"\n종료: 완료 {done} / 실패 {fail} / 전체 {len(prog)}")
    if fail:
        print("실패한 조건은 이 스크립트를 다시 실행하면 재시도합니다.")
    print(f"진행 상황: py 27_orchestrate.py --status --out {out}")


if __name__ == "__main__":
    a = sys.argv
    if "--status" in a:
        outp = a[a.index("--out") + 1] if "--out" in a else "runs"
        show_status(outp)
    elif len(a) < 3:
        print(__doc__)
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        cov_dirs = opt("--cov-dirs", "cov_core").split(",")
        models = opt("--models", "qwen3:4b").split(",")
        covs = None
        if "--covs" in a:
            covs = [int(x) for x in opt("--covs", "").split(",")]
        main(a[1], a[2], cov_dirs, models, covs,
             int(opt("--k", "5")), float(opt("--alpha", "0.5")),
             opt("--out", "runs"), "--think" in a, int(opt("--timeout", "600")),
             int(opt("--num-ctx", "16384")), int(opt("--num-predict", "256")),
             opt("--run-plan", "run_plan.json"), opt("--ollama-url", ""))
