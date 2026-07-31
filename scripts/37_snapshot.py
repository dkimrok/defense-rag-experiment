#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
37_snapshot.py — 실험 결과 주기 스냅샷

왜 필요한가
  Kaggle 의 /kaggle/working 은 커밋(Save Version) 없이 세션이 끝나면
  통째로 사라진다. 실측으로 2.8시간짜리 본실험 결과를 잃었다.
  커널만 재시작되는 경우(OOM 등)에는 디스크가 남으므로, 주기적으로
  압축해 두면 그 손실은 막을 수 있다.

  다만 세션 자체가 끝나면 스냅샷도 같이 사라진다. 근본 대책은
  'Save & Run All (Commit)' 배치 실행이다. 이 스크립트는 그 보조 수단이며,
  마지막에 반드시 커밋하거나 zip 을 내려받아야 한다.

동작
  --watch  백그라운드 스레드로 N초마다 압축(노트북 셀에서 import 해 사용)
  --once   한 번만 압축
  압축 대상은 지정한 폴더들. 이전 스냅샷과 내용이 같으면 건너뛴다.

노트북에서
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location('snap', '37_snapshot.py')
    snap = importlib.util.module_from_spec(spec); spec.loader.exec_module(snap)
    snap.start_watch(['runs', 'runs_closedbook', 'grade_out'], every=600)
    # ... 실험 셀 실행 ...
    snap.snapshot_once(['runs', 'runs_closedbook', 'grade_out'])   # 끝나고 한 번 더

명령행
    py 37_snapshot.py --once --dirs runs,runs_closedbook --out /kaggle/working
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import threading
import time
from pathlib import Path

_state = {"thread": None, "stop": False, "last": {}}


def _fingerprint(d: Path) -> str:
    """폴더의 파일명·크기·수정시각으로 지문을 만든다. 내용이 안 바뀌면
    같은 값이 나오므로 불필요한 재압축을 건너뛴다."""
    h = hashlib.md5()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            st = f.stat()
            h.update(f"{f.relative_to(d)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()


def snapshot_once(dirs, out: str = "/kaggle/working", quiet: bool = False) -> list:
    made = []
    outp = Path(out)
    outp.mkdir(parents=True, exist_ok=True)
    for d in dirs:
        src = Path(d)
        if not src.is_dir():
            continue
        fp = _fingerprint(src)
        if _state["last"].get(str(src)) == fp:
            if not quiet:
                print(f"  [스냅샷] {src.name}: 변경 없음")
            continue
        base = outp / f"snapshot_{src.name}"
        shutil.make_archive(str(base), "zip", root_dir=str(src.parent),
                            base_dir=src.name)
        _state["last"][str(src)] = fp
        z = base.with_suffix(".zip")
        made.append(z)
        if not quiet:
            n = sum(1 for f in src.rglob("*") if f.is_file())
            print(f"  [스냅샷] {z.name} ({z.stat().st_size/1024/1024:.1f}MB, "
                  f"파일 {n}개)")
    return made


def _loop(dirs, out, every):
    while not _state["stop"]:
        for _ in range(every):
            if _state["stop"]:
                return
            time.sleep(1)
        try:
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] 스냅샷")
            snapshot_once(dirs, out)
        except Exception as e:                           # noqa: BLE001
            print(f"  [스냅샷 실패] {type(e).__name__}: {e}")


def start_watch(dirs, out: str = "/kaggle/working", every: int = 600) -> None:
    """백그라운드로 every 초마다 압축한다. 노트북 셀을 막지 않는다."""
    if _state["thread"] and _state["thread"].is_alive():
        print("이미 감시 중입니다.")
        return
    _state["stop"] = False
    t = threading.Thread(target=_loop, args=(dirs, out, every), daemon=True)
    t.start()
    _state["thread"] = t
    print(f"스냅샷 감시 시작: {', '.join(str(d) for d in dirs)} "
          f"→ {out} ({every}초 간격)")
    print("주의: 세션 자체가 끝나면 이 스냅샷도 사라집니다. "
          "반드시 커밋하거나 zip 을 내려받으십시오.")


def stop_watch() -> None:
    _state["stop"] = True
    print("스냅샷 감시 중지")


if __name__ == "__main__":
    a = sys.argv
    dirs = (a[a.index("--dirs") + 1].split(",") if "--dirs" in a
            else ["runs", "runs_closedbook", "grade_out"])
    out = a[a.index("--out") + 1] if "--out" in a else "/kaggle/working"
    if "--watch" in a:
        every = int(a[a.index("--watch") + 1]) if len(a) > a.index("--watch") + 1 \
            and a[a.index("--watch") + 1].isdigit() else 600
        start_watch(dirs, out, every)
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            stop_watch()
    else:
        snapshot_once(dirs, out)
