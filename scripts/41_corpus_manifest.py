#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
41_corpus_manifest.py — 코퍼스 문서 매니페스트 생성

왜 필요한가
  08_collect_v2.py 와 13_collect_scope_laws.py 는 '현행' 버전을 받아온다.
  법령과 행정규칙은 개정되므로, 몇 년 뒤 같은 스크립트를 돌리면 본문이
  달라진다. 그러면 "코퍼스는 법제처 OPEN API 로 재현 가능하다"는 진술이
  사실이 아니게 된다.

  이 스크립트는 실제로 사용한 232개 문서의 버전 식별자를 뽑아낸다.
  행정규칙은 행정규칙일련번호, 법령은 법령ID 이며, 공포번호와 시행일자를
  함께 남기므로 재현자가 우리가 쓴 것과 같은 판본을 지목해 받을 수 있다.

  본문을 재배포하지 않으면서 재현을 가능하게 하는 최소 정보다.

출력
  corpus_manifest.json   문서 수준 목록 + 집계
  corpus_manifest.csv    같은 내용의 표 (검토용)

사용법
  py 41_corpus_manifest.py corpus_final.jsonl --out .
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def load(p: str):
    for line in Path(p).read_text(encoding='utf-8').splitlines():
        if line.strip():
            yield json.loads(line)


def main() -> int:
    a = sys.argv
    if len(a) < 2:
        print(__doc__)
        return 0

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d

    out = Path(opt('--out', '.'))
    out.mkdir(parents=True, exist_ok=True)

    docs: dict[str, dict] = {}
    counts = defaultdict(lambda: [0, 0])          # doc_id -> [units, chars]
    n_units = 0
    for u in load(a[1]):
        did = u.get('doc_id')
        if not did:
            continue
        n_units += 1
        counts[did][0] += 1
        counts[did][1] += u.get('char_len') or 0
        if did not in docs:
            uid = u.get('unit_id', '')
            docs[did] = dict(
                doc_id=did,
                source='admrul' if uid.startswith('admrul:') else
                       ('law' if uid.startswith('law:') else uid.split(':')[0]),
                doc_name=u.get('doc_name', ''),
                doc_type=u.get('doc_type', ''),
                tier=u.get('tier', ''),
                issue_no=str(u.get('issue_no') or ''),
                effective_date=str(u.get('effective_date') or ''),
            )

    for did, d in docs.items():
        d['n_units'], d['n_chars'] = counts[did]

    rows = sorted(docs.values(), key=lambda d: (d['tier'], d['doc_name']))
    by_tier = defaultdict(lambda: [0, 0, 0])
    for d in rows:
        t = by_tier[d['tier'] or 'unknown']
        t[0] += 1
        t[1] += d['n_units']
        t[2] += d['n_chars']

    manifest = dict(
        note=('Version identifiers for the documents used in this study. '
              'Administrative rules are keyed by 행정규칙일련번호 and statutes by '
              '법령ID, both as returned by the Korean Ministry of Government '
              'Legislation open API. issue_no and effective_date pin the edition, '
              'because the API serves the current version by default and these '
              'documents are amended.'),
        n_documents=len(rows),
        n_units=n_units,
        n_chars=sum(d['n_chars'] for d in rows),
        by_tier={k: dict(documents=v[0], units=v[1], chars=v[2])
                 for k, v in sorted(by_tier.items())},
        documents=rows,
    )
    (out / 'corpus_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')

    cols = ['doc_id', 'source', 'tier', 'doc_type', 'doc_name',
            'issue_no', 'effective_date', 'n_units', 'n_chars']
    with open(out / 'corpus_manifest.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for d in rows:
            w.writerow({c: d.get(c, '') for c in cols})

    print(f"문서 {len(rows)}종 / unit {n_units:,} / 문자 {manifest['n_chars']:,}")
    for k, v in sorted(by_tier.items()):
        print(f"  {k:16s} 문서 {v[0]:3d}  unit {v[1]:6,}  문자 {v[2]:10,}")
    miss = [d['doc_name'] for d in rows if not d['effective_date']]
    if miss:
        print(f"\n*** 시행일자 없는 문서 {len(miss)}종 — 재현 시 판본을 특정할 수 없다")
        for m in miss[:8]:
            print('   ', m)
    print(f"\n-> {out}/corpus_manifest.json, corpus_manifest.csv")
    return 0


if __name__ == '__main__':
    sys.exit(main())
