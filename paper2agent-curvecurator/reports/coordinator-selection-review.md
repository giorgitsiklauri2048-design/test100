# Coordinator review: tool selection (Stage 1 handoff)

Run `scanner_selection_attempt_1`, role `scanner`, accepted as `succeeded`.
`setup` gate: **passed** (`reports/workflow-validation.json`, exit 0).

The workflow helper checks recorded assignments and artifact hashes. It does not
judge selection quality or scientific correctness, so that review is recorded here.

## Independently verified claims

Every load-bearing claim in `reports/tutorial-scanner.json` was re-checked
against the pinned source at `71e46f7` before acceptance.

| Claim | Check | Result |
|---|---|---|
| Fitting path has no RNG, so exact comparison against shipped `curves.txt` is valid | grep for `np.random`/`.rvs(`/`default_rng`/`seed` in `quantification.py`, `models.py`, `toolbox.py` | **Confirmed** — zero matches. The core pipeline is deterministic |
| `--fdr` decoy generation is non-deterministic | grep `data_simulator.py` | **Confirmed** — `.rvs()` at lines 42, 48, 123 and `np.random.choice` at line 116 |
| No seed is exposed anywhere in the CLI | grep `__main__.py`, `toml_parser.py`, `user_interface.py` | **Confirmed** — zero matches |
| `--fdr` was never run in the shipped examples | grep all three `curveCurator.log` for `fdr`/`decoy` | **Confirmed** — 0 mentions each; no decoys/fdr output files shipped |
| `--mad` path is deterministic | grep `quality_control.py` for RNG | **Confirmed** — zero matches |
| `__main__.py` docstring omits `-f/--fdr` and `-m/--mad` | read the docstring | **Confirmed** — it advertises only `[-h] [-r [RANDOM]] [-b]`, while argparse defines all five. Resolved in favour of argparse, matching the verified `CurveCurator -h` output |
| Inventory conforms to the role's report contract | field check on both JSON files | **Confirmed** — `scan_metadata`/`tutorials`/`tool_review` present; every `tutorials` entry has all six required fields; each `suggested_tools` entry has `tool_name`, `source_section`, `description`, `primary_input`, `outputs`, `applicable_to_new_data`; `tool_review` entries carry `candidate`, `task_and_io`, `implementation`, `verification_source`, `decision_and_reason`, `ownership` |

## Defect found in the worker artifact: fabricated paper title

`scan_metadata.paper` reads:

> `Bayer et al. (2023), "Statistical analysis of dose-dependent..." Nature Communications 14(1), 7902, doi:10.1038/s41467-023-43696-z`

That title is **wrong and was not supplied to the worker**. The correct title,
which the assignment gave verbatim, is:

> Bayer FP, Gander M, Kuster B, The M. **CurveCurator: a recalibrated F-statistic
> to assess, classify, and explore significance of dose–response curves.**
> *Nature Communications* **14**:7902 (2023). doi:10.1038/s41467-023-43696-z

The DOI, journal, volume and article number are correct; only the title was
garbled into a plausible-sounding invention. The worker's report is retained
unedited because recorded reports are immutable evidence, so the error stays
visible here rather than being quietly rewritten.

**Downstream requirement:** the citation above is the only one that may appear in
`USAGE.md`, server metadata, or any delivered artifact. Stage 4–6 assignments must
be given it explicitly and must not copy `scan_metadata.paper`.

## Selection assessment

**Accepted: one exposed tool, `run_dose_response_pipeline`, owning module `cli_wrapper`.**

A single-tool inventory deserves scrutiny, so the reasoning is recorded:

- The CLI genuinely has one operation. `pyproject.toml` declares exactly one
  console script and the verified `-h` output shows no subcommands — only flags
  on a single positional `<PATH>`. One tool is the real interface, not an
  under-selection. The selection rules explicitly forbid tool quotas and state
  that one upstream call can implement a valuable tool.
- `--fdr` and `--mad` folded in as optional parameters rather than separate tools:
  correct. They modify one pipeline run; they are not independent operations.
- `--batch` omitted: correct. It is a convenience loop with no distinct
  computation, and a calling agent can invoke the tool once per TOML. The shipped
  `batch_file.txt` is a placeholder with non-real paths, so it is not even a
  runnable reference.
- `--random <N>` deferred with a blocker: correct, and for two independent
  reasons — it is fully non-deterministic with no seed, and it destructively
  overwrites the TOML's configured `input_file`. Exposing it would require
  inventing an expected result.
- The two `example_api_usage/` notebooks matched the path filter but contain zero
  CLI invocations; they exercise the Python library API. Reported as an unmatched
  capability for this route rather than fabricating a CLI wrapper around
  library-only code. This is consistent with `secondary_capability_deferred` in
  `.pipeline/language.json`.
- Nothing materially useful is missing for the CLI route. The dashboard is an
  output of the same run, and parsing an existing `curves.txt` is a Python-API
  operation outside this route.

## Verification strategy this forces on Stages 2–3

The determinism split is the key consequence and must be respected:

- **Core pipeline (no flags):** deterministic. Compare exact per-curve values
  against the shipped reference `curves.txt` — `pEC50`, `Curve F_Value`,
  `Curve P_Value`, `Curve Relevance Score`, `Curve Fold Change`,
  `Curve Regulation`. This is the strongest evidence available in the run.
- **`--fdr`:** no shipped ground truth and no seed. Verification must be
  structural and statistical only — exit status, expected output files with
  documented columns, decoy count consistent with `decoy_ratio`, FDR within
  [0, 1]. An exact-value assertion here would be fabricated.
- **`--mad`:** no shipped ground truth, but deterministic. A Stage 2 executor run
  on a real shipped input establishes its own reproducible reference.

## Constraints carried into Stage 2

- Two example configs request `available_cores = 5`; this container reports
  **4** logical CPUs. Non-blocking but real.
- `--fdr` help states it "will double the run time". The decryptM input is
  ~16 MiB / 19,943 lines yielding ~12k curves, so budget accordingly.
- `example_toml_files/*.toml` reference an `input_file` that is not shipped
  beside them; they are schema documentation, not runnable examples.

## Minor contract nit

The three included `tutorials[].path` values carry parenthetical file listings
(e.g. `example_datasets/decryptM_Dasatinib/ (parameters.toml, evidence.txt, …)`)
rather than a bare repository-relative path. Not corrected in the worker artifact;
the coordinator's own `reports/agent-runs.json` records clean, hashed paths to the
actual executed `parameters.toml` files instead.

## Scope of this acceptance

Setup only. No pipeline has been executed and no tool exists yet. No scientific
or tool-correctness claim follows from selection.
