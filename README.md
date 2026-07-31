# Knowledge Before Models — replication package

Replication material for:

> Kim, Dongjin. "Knowledge Before Models: A Coverage Audit for Air-Gapped
> Retrieval-Augmented Generation." *AI Magazine* (under review).

**Archived version (cite this):** Zenodo DOI `[10.5281/zenodo.21712890]`
**Development version:** `https://github.com/dkimrok/defense-rag-experiment`

The study manipulates two factors that are normally confounded — how much of the
task a corpus covers, and how large the corpus is — and measures their separate
effects on a retrieval-augmented generation system built over Korean defense
acquisition law. This package contains everything needed to regenerate the
conditions, re-run the evaluation, re-grade the responses, and reproduce every
table and figure in the article.

---

## 1. Contents

| Path | Contents |
|---|---|
| `scripts/` | The full pipeline, 32 scripts. Numbering follows the order of use and has gaps where steps were merged or abandoned. See §4. |
| `questions/question_final.jsonl` | The 97 evaluation questions used in every condition: 80 answerable (levels L1–L4) and the original 17 out of scope. Each carries gold evidence with provision text, a difficulty rationale, and distractors. |
| `questions/question_oos_extra_filled.jsonl` | 25 further out-of-scope questions, written after the main experiment and evaluated only on the volume axis. |
| `questions/question_slots.jsonl` | Unfilled slots as produced by stratified sampling, for anyone wanting to write a different question set over the same sample. |
| `questions/oos_sources.jsonl` | The pool of naturally occurring knowledge gaps — general statutes cited but not held, abolished regulations, unobtainable documents, deleted provisions — from which out-of-scope questions were drawn. |
| `corpus_meta/corpus_manifest.json`, `.csv` | Version identifiers for all 232 documents. The Legislation API serves current versions and these documents are amended, so reproducing the corpus requires pinning the editions used here. |
| `corpus_meta/scope_map.json` | The converged corpus boundary decision. Automated triage reduced the undecided set; the residue was decided by hand and fed back through scope finalization, so this file is **not reproducible from the scripts alone**. |
| `corpus_meta/refs.jsonl` | The citation graph. Used by the coverage engine to rank documents by how often they are cited internally. |
| `conditions/cov_core/`, `cov_periph/`, `cov_random/`, `cov_vol/` | `coverage_manifest.json` for each axis: target and achieved coverage, achieved character ratio, and per-question status. |
| `conditions/run_plan.json` | Which of the 30 conditions are byte-identical duplicates of which. |
| `conditions/status_content.json` | Content-based coverage status, distinguishing a removed gold unit from removed knowledge. |
| `audit/` | Near-duplicate audit: neighbour map, summary statistics, and per-question instrument strength. |
| `runs/` | 69 response files and 57 metadata files. One JSON object per question per condition. |
| `runs_closedbook/` | The closed-book control: three models, 97 questions each. |
| `runs_oos/` | The out-of-scope extension, volume axis only. |
| `grade_out/` | Grading of the main experiment, the merged file used for analysis, the report, and the judge cache. |
| `grade_oos/` | Grading of the out-of-scope extension. |
| `analysis/analysis_main/`, `analysis_bal3/`, `analysis_all/` | Statistical output and the underlying data for every figure. See §3. |
| `figures/` | The four published figures, the graphical abstract, and the scripts that draw the two schematic figures. |
| `notebooks/` | The Kaggle and Colab drivers actually used to run the experiment. See §6. |

### File counts, and why they are not round numbers

**`runs/`.** 69 responses but only 57 metadata files. Five of the 30 conditions
are byte-identical to another and were copied rather than generated, so they have
no metadata of their own: `cov000_random`, `cov100_periph`, `cov100_random`,
`cov100_vol040`, and `cov100_vol100`. Every copied response record carries
`aliased_from`.

**`runs_oos/`.** Fifteen response files, not eighteen. The extension was run over
the volume axis, whose canonical condition at 100% is the full-corpus condition on
the coverage axis; that condition was not part of the extension run, so the volume
axis at 100% has only the original 17 out-of-scope questions and appears in
`runs/` rather than here. Section 5.6 of the article therefore reports four volume
levels, not five.

**`scripts/`.** Numbering runs 07 to 41 with gaps. Scripts 01–06 were API
diagnostics used during development and are not part of the pipeline. Gaps at 18,
20, and 21 are steps that were folded into 31–33.

### Not included, and why

**The source corpus.** Korean statutes and administrative rules are retrieved from
the Ministry of Government Legislation open API. `scripts/` contains the
collection and parsing code, and `corpus_meta/corpus_manifest.json` pins the
editions, so `corpus_final.jsonl` (232 documents, 50,550 units, 11,732,966
characters) can be rebuilt as it stood. Provision text for the gold evidence of
each question *is* included, inside the question files.

**Embeddings and the BM25 index.** `index/embeddings.npy` (about 30 MB) is
regenerated deterministically by `24_build_index.py`. `index/bm25.pkl` is a live
`BM25Okapi` object, and a pickle written by one version of `rank_bm25` may fail to
load under another, so it must be rebuilt rather than shipped.

**The 30 condition corpora.** Several hundred megabytes, regenerated by
`30_regen.py` from the corpus and the manifests included here.

---

## 2. Environment

```
python >= 3.10
pip install -r requirements.txt
```

Generation and judging use [Ollama](https://ollama.com) as a local inference
server. Models used:

| Role | Model | Ollama tag |
|---|---|---|
| System under test | Qwen3-4B-Instruct-2507 | `kamekichi128/qwen3-4b-instruct-2507:latest` |
| System under test | Qwen3-8B | `qwen3:8b` |
| System under test | Qwen3-14B | `qwen3:14b` |
| Judge | Gemma 2 9B | `gemma2:9b` |
| Judge | Llama 3.1 8B | `llama3.1:8b` |
| Judge | Mistral NeMo | `mistral-nemo` |

The 4B model is a community build of the vendor's non-reasoning release; the 8B
and 14B are reasoning-capable models run with reasoning suppressed.

A single 16 GB GPU is sufficient for every step. Reproducing all 30 conditions for
one model took about three hours on a T4; grading with three judges took one to
two hours.

**Stages 1 to 6 of the coverage audit described in the article require no GPU at
all.** Only generation (`25`, `27`, `36`) and judging (`23 --judges`) do.

---

## 3. Reproducing the published numbers

Grading output is included, so the analysis can be checked without running
generation. From the repository root:

```
python scripts/38_analyze.py grade_out/graded_all.jsonl --covdirs conditions/cov_core,conditions/cov_periph,conditions/cov_random,conditions/cov_vol --models 8b,4b --common-qids --out analysis/analysis_main
python scripts/38_analyze.py grade_out/graded_all.jsonl --covdirs conditions/cov_core,conditions/cov_periph,conditions/cov_random,conditions/cov_vol --balanced --out analysis/analysis_bal3
python scripts/38_analyze.py grade_out/graded_all.jsonl --covdirs conditions/cov_core,conditions/cov_periph,conditions/cov_random,conditions/cov_vol --out analysis/analysis_all
```

- `analysis_main` is the primary specification. Table 1 and all four figures come
  from it: the 97 common questions and the two models evaluated on all 30
  conditions.
- `analysis_bal3` is the three-model robustness check, restricted to the
  conditions all three models share.
- `analysis_all` supplies the descriptive tables, the McNemar tests, the
  closed-book contrast, and the decomposition of overconfident error.

`--common-qids` matters. Without it the 25 later-written out-of-scope questions,
which exist only on the volume axis, enter the regression and make character ratio
correlate with question composition rather than with anything causal.

To redraw the schematic figures:

```
cd figures && python fig4_framework.py && python graphical_abstract.py
```

---

## 4. The pipeline

### Corpus construction

| Script | Purpose |
|---|---|
| `07_parse_admrul_v2.py` | Parse administrative rules into provision-level units. Article, paragraph, subparagraph, and item arrive concatenated in a single string, so candidate markers are accepted only where they number from one upward; otherwise inline text such as a cross-reference is read as a subparagraph. |
| `08_collect_v2.py` | Collect administrative rules and statutes from the Legislation API |
| `09_extract_refs.py` | Extract cross-tier references, resolving each document's own abbreviations before interpreting them; produces `refs.jsonl` and the L3 candidate pool |
| `10_extract_revisions.py` | Compare adjacent versions of the same rule and keep only amendments where the answer actually changes; produces the L4 candidate pool and the `stale_versions` distractors |
| `11_finalize_scope.py` | Decide the corpus boundary by rule, normalizing names and joining against what was collected |
| `12_triage_undecided.py` | Reduce the undecided set by noise removal, fuzzy matching, and suffix inheritance; emits overrides that `11` reads on its next run, so `11 → 12 → 11` converges. Items above a citation threshold are decided by hand. |
| `13_collect_scope_laws.py` | Collect the documents that scope finalization marked for collection |
| `14_parse_law.py` | Parse statutes, whose API response structure differs from administrative rules |
| `15_merge_corpus.py` | Merge the parsed tiers into `corpus_final.jsonl` and re-check the boundary |
| `16_verify_gold.py` | Resolve every reference to a real unit in the corpus, so a candidate is dropped when the cited provision has been deleted or renumbered |
| `41_corpus_manifest.py` | Emit the document-level version manifest from `corpus_final.jsonl` |

### Question authoring

| Script | Purpose |
|---|---|
| `17_sample_questions.py` | Stratified sample of target provisions; emits unfilled slots with gold evidence and provision text |
| `31_make_worksheet.py` | Render slots as per-level Markdown worksheets carrying the full provision text, so questions can be written without consulting the corpus |
| `32_fill_worksheet.py` | Parse completed worksheets back into slots and run the authoring checks |
| `26_merge_slots.py` | Merge separately authored slot files |
| `33_rebuild_questions.py` | Regenerate slots and carry written questions across, refusing to carry any whose gold evidence changed |
| `34_fix_spans.py` | Remove duplication in assembled provision text |
| `39_sample_oos.py` | Sample further out-of-scope candidates, capped per cited target so no single general statute dominates |
| `19_check_questions.py` | Authoring checks: lexical leakage, short-answer length, proper nouns, reference-date disclosure, positional references, and whether an out-of-scope question names its absent target |
| `35_scan_refs.py` | Report positional and document-name references for editorial judgment |
| `40_recover_slots.py` | Reconstruct minimal slots from response files, if a question file is lost |

### Index and conditions

| Script | Purpose |
|---|---|
| `24_build_index.py` | Assemble provision-level chunks, embed with BGE-m3, build BM25. `--dry-run` skips embedding and needs no GPU. |
| `22_coverage_engine.py` | Generate condition corpora. `--mode coverage` removes gold-bearing documents; `--mode volume` removes only documents with no gold. Removal order is fixed once per strategy so that variants nest. |
| `28_dup_audit.py` | Near-duplicate audit over the corpus |
| `29_status_content.py` | Content-based coverage status, distinguishing a removed gold unit from removed knowledge |
| `30_regen.py` | Run 22, 28, and 29 together and verify nesting, strategy separation, and volume-axis coverage |

### Evaluation

| Script | Purpose |
|---|---|
| `25_rag_run.py` | Hybrid retrieval and generation for one condition. Caches query embeddings, so the embedding model is loaded once rather than once per condition. |
| `27_orchestrate.py` | Run all conditions with checkpointing; skips byte-identical duplicates and copies their results |
| `36_closedbook.py` | Closed-book control: same questions, same output format, no retrieval |
| `37_snapshot.py` | Periodic snapshot of results, for use on ephemeral compute |

### Grading and analysis

| Script | Purpose |
|---|---|
| `23_grade.py` | Five-state grading. Keyword matching first; ambiguous cases go to a majority vote of three judge models, batched per model so each is loaded once rather than reloaded per item. Verdicts are cached by a hash of question, gold answer, and response. |
| `38_analyze.py` | Cluster-robust logistic regression, Wilson intervals, McNemar tests, and the four figures |

### Order

```
07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 41     corpus
17, 31, → write by hand, 32, 26, 19, 35, 39    questions
24                                              index
30  (= 22, 28, 29)                              conditions
27  (calls 25), 36                              generation
23                                              grading
38                                              analysis
```

---

## 5. Things a replicator should know

**Seeds.** Stratified sampling and removal ordering use seed `20260721`.
Generation uses temperature 0. An identical corpus therefore yields identical
retrieval, prompts, and responses.

**Duplicate conditions.** Of the 30 conditions, five are byte-identical to
another: the three full-corpus variants coincide with each other and with the
volume axis at 100%; the peripheral and random strategies coincide at zero
coverage; the two lowest volume targets coincide at the 43% floor. These were
generated once and copied.

**Nesting.** Removal order is fixed once per strategy, so the corpus at lower
coverage is a subset of the corpus at higher coverage. `30_regen.py` checks this;
if it reports a break, the variants were generated by a version of
`22_coverage_engine.py` that reshuffled at each level.

**The out-of-scope extension is unbalanced.** Twenty-five of the 42 out-of-scope
questions were written after the main experiment and run only on the volume axis.
Use `--common-qids` for anything that pools across axes.

**The corpus boundary is partly a human decision.** `12_triage_undecided.py`
resolves most of the undecided set automatically, but items above a citation
threshold were decided by hand. `corpus_meta/scope_map.json` records those
decisions and is required to rebuild the same 232-document corpus.

**The attribution test compares provision numbers, not document–provision
pairs.** A citation to Article 6 of an absent statute counts as present whenever
any retrieved provision is numbered 6. The 98% presence figure reported in the
article is therefore conservative, and the share of genuine invention may be
higher.

**Judges are language models.** Three families other than the one under test, by
majority vote. Agreement against human adjudication was not measured.

---

## 6. Notebooks

`notebooks/kaggle_main_experiment.ipynb` ran the main experiment: 30 conditions
across two models on two T4 GPUs, the closed-book arm, and the Qwen3-14B subset.
`notebooks/colab_grading_and_oos.ipynb` ran judge-based grading and the
out-of-scope extension, writing results to Google Drive after each stage.

These are environment-specific drivers. **The authoritative pipeline is
`scripts/`; the notebooks only orchestrate it**, and their paths, GPU assignments,
and model-download steps are particular to those two platforms. Their outputs are
left in place because the per-condition timings, VRAM occupancy, and retrieval
statistics they record are useful for comparison.

---

## 7. Licenses

| Component | License |
|---|---|
| `scripts/`, `figures/*.py` | MIT — see `LICENSE` |
| Everything else | CC BY 4.0 — see `LICENSE-CC-BY-4.0.txt` |

See `NOTICE.txt` for the per-directory mapping and for a note on the provision
text included in the question files. Korean statutes and administrative rules are
excluded from copyright protection under Article 7 of the Korean Copyright Act;
the CC BY grant covers the selection, annotation, and arrangement of that
material.

---

## 8. Citation

```bibtex
@dataset{kim2026coverage_data,
  author    = {Kim, Dongjin},
  title     = {Knowledge Before Models: replication package},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.21712890}
}

@article{kim2026coverage,
  author  = {Kim, Dongjin},
  title   = {Knowledge Before Models: A Coverage Audit for
             Air-Gapped Retrieval-Augmented Generation},
  journal = {AI Magazine},
  year    = {2026},
  note    = {Under review}
}
```

Contact: Dongjin Kim, Korea Institute for Defense Analyses.
ORCID [0009-0009-6414-3477](https://orcid.org/0009-0009-6414-3477)
