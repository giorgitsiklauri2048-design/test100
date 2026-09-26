# Resuming this Paper2MCP run

This is a **Paper2Agent (Paper2MCP) conversion of `kusterlab/curve_curator` into a
tested MCP server**, run with the real Paper2Agent skill. It is paused mid-Stage 3.

The container it ran in is ephemeral and will be gone. Everything needed to resume
is committed; the three restore steps below rebuild what was deliberately not.

## Where it stopped

| Stage | State | Gate |
|---|---|---|
| 1 — environment + tool selection | **complete** | `setup` passed |
| 2 — source execution | **complete** | `execution` passed |
| 3A — implement `src/tools/cli_wrapper.py` | **complete** | `extraction` passed |
| 3B — independent verification | **INTERRUPTED mid-run** | `verification` not run |
| 4 — MCP integration | not started | |
| 5 — runtime validation in a clean env | not started | |
| 6 — `USAGE.md` + ZIP delivery | not started | |

Markers present in `.pipeline/`: `project_setup_done`, `source_setup_done`,
`workspace_setup_done`, `environment_and_selection_done`, `reference_execution_done`.
**`implementation_and_verification_done` is absent** — that is the resume point.

At the pause, the verifier had **27 tests passing with 0 failures** (28 of 29 test functions completed; only `test_wrong_runtime_override_is_rejected` was never reached) and had not
modified `src/tools/cli_wrapper.py` (hash still
`18d3d5e503c90e3dc0424685f9c6f63f0de66c7363b1a365945a66bb563ff46b`, matching the
`produced_files` entry in `reports/agent-runs.json`). Its two reports
(`reports/verification-cli_wrapper.json`, `reports/mcp-acceptance-cli_wrapper.json`)
were **never written**, so Stage 3B must be re-run.

## Restore (3 steps, ~10 minutes)

```bash
cd paper2agent-curvecurator

# 1. pinned upstream source (111 MB, excluded from git)
git clone https://github.com/kusterlab/curve_curator.git repo/curve_curator
git -C repo/curve_curator checkout 71e46f7222f825f446e9aff3fb5a3bee9473e309
git -C repo/curve_curator status --porcelain   # MUST be empty

# 2. project environment (474 MB, excluded from git)
python3 -m venv .venv
uv pip install --python .venv/bin/python ./repo/curve_curator \
    'fastmcp==4.0.3' 'pytest>=7.4.3,<8.0.0' 'pytest-asyncio==0.23.8'
uv pip check --python .venv/bin/python

# 3. confirm identity — the executable is CurveCurator, NOT curve_curator
ls .venv/bin/CurveCurator && .venv/bin/CurveCurator -h | head -3
```

Full pinned dependency set: `reports/environment-requirements.txt` (96 packages,
Python 3.11.15). Re-verify the recorded state before doing anything else:

```bash
.venv/bin/python /root/.claude/skills/paper2agent/paper2mcp/scripts/verify_workflow.py \
  --project-root . --through extraction
```

The Paper2Agent skill itself installs with:

```bash
git clone https://github.com/jmiao24/Paper2Agent.git /tmp/p2a
mkdir -p "$HOME/.claude/skills/paper2agent"
cp -R /tmp/p2a/skills/paper2agent/. "$HOME/.claude/skills/paper2agent/"
```

## What is NOT restored, and the consequence

`notebooks/**/evidence.txt`, `proteinGroups.txt`, `*.tsv` and `*.html` are excluded
(~20 MB per example). The **input** files come back with the `repo/` clone; copy them
into the executor work directories if a test needs them in place.

All produced **text** reference outputs ARE committed (~7 MB): `curves*.txt`,
`decoys*.txt`, `fdr*.txt`, `mad*.txt`, logs, drivers and the before/after hash
captures. These are what Stage 3's comparisons assert against, so Stage 3B can be
re-run without redoing Stage 2. The bokeh dashboards are not committed; any test
asserting on a dashboard must regenerate one or assert only on its existence.

## Resume instruction for the next session

Re-run **Stage 3B only** — a fresh verifier for the `cli_wrapper` module. Its
`agent_id` must differ from **every** implementer id in `reports/agent-runs.json`
(currently `a0a778f78fc452cf4`) and from the interrupted verifier
(`aaf54bd89f104fd69`). Record the interrupted attempt as a terminal
`cancelled`/`failed` run with a retained report before appending a new attempt — do
not rewrite its record. Then run the `verification` gate, write
`.pipeline/implementation_and_verification_done`, and continue to Stages 4–6.

The existing test suite (`tests/code/test_run_dose_response_pipeline.py`, 31 tests)
and `pytest.ini` are committed and can be reused.

## Findings that must carry forward

These were established by verification, not assumption, and several are load-bearing.

1. **The executable is `CurveCurator`, not `curve_curator`.** `pyproject.toml`
   declares `CurveCurator = "curve_curator.__main__:main"`; the lowercase name is the
   importable module only and is not on PATH. This already fixed a real bug in the
   separate hand-built server on branch `claude/sweet-newton-2u7xfq`.
2. **CurveCurator exits 0 on fatal configuration errors.** `toml_parser` calls
   `ui.error(...)` then a bare `exit()` = `SystemExit(None)` = status 0. Reproduced
   directly against the real executable. Exit status alone therefore cannot mean
   success, which is why the wrapper post-checks that declared artifacts exist and
   are non-empty. **Confirming that check catches this is the most important test in
   the suite** — a passing test here could otherwise be vacuous.
3. **Absolute `[Paths]` entries pass through upstream unchanged.**
   `toml_parser.update_toml_paths` joins with the toml's directory only
   `if not os.path.isabs(path)`. This is what makes the wrapper's staging strategy
   sound: it rewrites a staged copy's paths to absolute rather than copying a
   16 MiB input on every call.
4. **Never join comparison tables on `Name`.**
   `kinobeads_Dasatinib/curves.txt` has 1170 rows with a duplicated `Name` (`TMPO`);
   an index join silently cross-expands and compares mismatched rows. Align by row
   order after asserting the identifier sequence matches position-by-position. This
   produced an impossible "1170 of 1169" match count before it was caught.
5. **Stratify numerical tolerance by significance.** Curves classified `up`/`down`
   agree with shipped references to ≤ 2e-06 on `pEC50` (714 curves across both
   examples); one non-significant curve (`GSU_NPC-26`, R² 0.345, F 2.165) differs by
   0.206. `Curve Regulation` matched exactly on all 2,381 curves, making it the
   sharpest regression signal. Apply tight parameter tolerances only to significant
   curves and say so; a loose global tolerance would hide a real regression.
6. **`--fdr` is not reproducible by value.** `data_simulator.py` draws unseeded at
   four sites and no seed is exposed anywhere in the CLI. Two `--fdr` runs on
   identical input gave bit-identical target fits (exactly 0.000e+00 difference on
   `pEC50`, `Curve Relevance Score`, `Curve F_Value`) but different decoys
   (`Curve q_Value` differing by 4.633e-02; FDR 0.003704 vs 0.001852). Verify
   structure and bounds only. **Any test asserting an exact FDR or decoy value is
   invalid by construction.**
7. **`--mad` is deterministic** and leaves `curves.txt` byte-identical to the base
   run. Both are fair assertions.
8. **`--batch` and `--random` are deliberately not exposed** — see
   `reports/coordinator-selection-review.md`. `--random` is unseeded and
   destructively overwrites the configured `input_file`.
9. **The scanner fabricated the paper title** as "Statistical analysis of
   dose-dependent…". The correct citation, the only one that may appear in `USAGE.md`
   or any delivered artifact, is: Bayer FP, Gander M, Kuster B, The M. *CurveCurator:
   a recalibrated F-statistic to assess, classify, and explore significance of
   dose–response curves.* Nature Communications 14:7902 (2023).
   doi:10.1038/s41467-023-43696-z. **Do not copy `scan_metadata.paper`.**

## Limitations to state in `USAGE.md`

- `decryptm_dasatinib` was **excluded on resource grounds** (recorded exclusion, not
  a silent omission — `reports/exclusions/decryptm-dasatinib.json`). Nothing in this
  run exercises the wrapper at ~16 MiB / ~12k-curve scale.
- `--mad` has no external ground truth; it rests on an internal determinism proof.
  `--fdr` rests on structural checks only.
- `-r/--random` is not exercised at all.
- Runtimes measured here reflect heavy CPU contention (load ~47 at worst on 4 CPUs)
  and must **not** be quoted as performance characteristics.
- A `pEC50` from a curve not classified `up`/`down` is not reproducible run to run
  and must not be reported as a measurement.

## Context

Two sibling branches hold a **separate, hand-built** MCP server for the same paper,
useful for comparison but not part of this run:
`claude/sweet-newton-2u7xfq` (PR #2) and, for a different paper,
`claude/paper2agent-franzosa-mcp-vssru8` (PR #1). This run is PR #3.

## Addendum written at the pause

Stage 3B got much further than the earlier progress note suggested. Final tally from
`tests/logs/pytest-cli_wrapper.log`: **27 passed, 0 failed**, with 28 of the 29 test
functions completed. The only test never reached was
`test_wrong_runtime_override_is_rejected` (executable-identity rejection).

`src/tools/cli_wrapper.py` was **not modified** by the verifier — its hash still
matches the implementer's `produced_files` entry — so no repair was attempted or
needed, and nothing in the completed suite contradicts the implementation.

Practical consequence: the re-run of Stage 3B is expected to be quick and to pass.
What is missing is not evidence of correctness but the two **report artifacts** the
gate requires (`reports/verification-cli_wrapper.json`,
`reports/mcp-acceptance-cli_wrapper.json`), plus that one unreached test. The
interrupted attempt is recorded terminally as `cancelled` in
`reports/agent-runs.json`, pointing at
`reports/cancelled/verify-cli_wrapper-attempt-1.json`. Retain that record and append
a new attempt rather than rewriting it.
