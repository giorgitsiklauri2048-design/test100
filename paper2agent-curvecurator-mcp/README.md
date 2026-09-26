# CurveCurator — MCP Server

An MCP server exposing the dose–response statistics of:

> Bayer FP, Gander M, Kuster B, The M.
> **CurveCurator: a recalibrated F-statistic to assess, classify, and explore
> significance of dose–response curves.**
> *Nature Communications* **14**:7902 (2023).
> [doi:10.1038/s41467-023-43696-z](https://doi.org/10.1038/s41467-023-43696-z)
> · PMID [38036588](https://pubmed.ncbi.nlm.nih.gov/38036588/) · PMC10689459

Article metadata and full text retrieved via PubMed / PubMed Central.

---

## The one design decision that matters

**This server does not reimplement the paper's statistics. It calls the authors'
own `curve_curator` package as a library.**

The paper's recalibrated F-statistic, effective degrees of freedom, s0 and
relevance score are defined in numbered equations (1–10) that are rendered as
images in the article. A text-only reading of the paper cannot recover their
coefficients, and inventing them would produce a plausible-looking server that
returns wrong numbers. So the statistics were sourced from the authors'
implementation instead — which is what the article points readers to, and whose
own docstrings cite *"equations 6, 7, 8 Bayer et al. 2023"*.

Every F-value, p-value, s0, relevance score, regulation class, decoy and FDR this
server returns is computed inside `curve_curator`. `src/curvecurator_mcp/engine.py`
only marshals units and shapes. Two tests enforce that: `test_engine_imports_the_authors_modules`
and `test_engine_does_not_hard_code_the_dof_polynomial`.

### Version fidelity

The manuscript used **v0.2.1**; this server pins **>=0.6.0,<0.7.0**. Before relying
on the current release, the manuscript-relevant code paths were diffed between the
v0.2.1 wheel from PyPI and the v0.6.0 source. These six were **byte-identical**:

| Code path | Role |
|---|---|
| `LogisticModel.get_dofs` | effective degrees of freedom (`dfn = 5`, `dfd = (0.8 − 1/((n−4)⁴/n + 4))·(n − 2.5)`) |
| recalibrated F expression | `F = (SSE_M0 − SSE_M1)/SSE_M1 · (n/k)` |
| F-distribution `loc` default | `0.12` |
| `thresholding.get_s0` | `s0 = \|fc_lim\| / √F.ppf(1−α, dfn, dfd)` |
| `thresholding.sam_correction` | `F_adj = 1/((1/√F) + s0/\|fc\|)²` |
| relevance score conversion | `−log10(F.sf(F_adj, dfn, dfd, loc, scale))` |

What *did* change after 0.2.1 (an R² fix in 0.5.0, RMSE as an output column,
clipping, `max_imputation`, dashboard rewrites) is recorded in
`src/curvecurator_mcp/data/paper_reference.json` and is explicitly **excluded** from the fidelity claim
above. Don't quote this server's R² as a manuscript-version number.

## How Paper2Agent was leveraged

**It was not**, and not because it was unavailable.

Paper2Agent ([jmiao24/Paper2Agent](https://github.com/jmiao24/Paper2Agent), MIT)
is a multi-agent system that converts a paper's code repository into a tested MCP
server. It was not installed in this environment, and the build proceeded by hand
without attempting to install it — an oversight, not a constraint. The repository
clones without issue here and installs with two commands, so the pipeline could
have been run and was not.

What this means for the artefact: the server follows the Paper2Agent *pattern*
— paper → typed tools + resource + guided prompt, every tool bound to existing
repository code — built directly on the official Python MCP SDK. It is **not** a
Paper2Agent output and must not be described as one. It has not been through that
pipeline's automated tool extraction, independent verification or ZIP delivery
contract.

Transport is *not* a difference: Paper2Agent's default conversion also produces a
stdio server, and its own `scripts/verify_mcp_server.py` validates one over stdio.
The `claude mcp add --transport http` registration in its top-level README applies
to its hosted demo Spaces, which are an opt-in remote-deployment extension.

The resource and prompt here also line up with what that pipeline calls optional
extensions — a resource supplying "input schemas, package-method documentation,
reference-data metadata" under stable URIs with source attribution, and a prompt
specifying "required inputs, tool order, dependent outputs, and interpretation
limits". Convergent, but arrived at independently.

A Paper2Agent run on `kusterlab/curve_curator` would plausibly yield tools this
server lacks, in particular executing the full pipeline over a real input file to
produce `curves.txt` and `dashboard.html`; this server stops at generating the TOML
and hands off to the CLI. The repository ships three complete worked examples
(`decryptM_Dasatinib`, `kinobeads_Dasatinib`, `viability_CTRP_40`) with inputs,
parameters and expected outputs, which makes it a strong candidate for that
pipeline's validation stage.

This is a standalone server. A companion server for a different paper
(Franzosa et al. 2021, HepaRG toxicogenomics) is developed independently on its own
branch and pull request; the two share no code and are registered separately. They
differ in one way worth noting: Franzosa's pipeline (tcpl) had to be reimplemented
from the article text, so that package carries the provenance burden of a
reimplementation. Here the authors ship the reference implementation, so the honest
move was to depend on it.

---

## Install

```bash
cd paper2agent-curvecurator-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Requires Python ≥ 3.11 (`curve_curator` moved to `tomllib` in v0.4.0),
`mcp[cli]>=2.0`, `curve_curator>=0.6.0,<0.7.0`, numpy, pandas, scipy.

> **SDK note.** Targets MCP SDK **2.x**, where `FastMCP` was renamed `MCPServer`.
> On SDK 1.x, change the import in `src/curvecurator_mcp/server.py` to
> `from mcp.server.fastmcp import FastMCP`; the decorator API is otherwise identical.

## Test

```bash
.venv/bin/python -m pytest -q
# 145 passed
```

- `test_engine.py` — fitting, dose handling, the control point, dofs, F-statistic, s0, all four classifications, boundary, FDR.
- `test_fidelity.py` — every statistic is checked against a direct `curve_curator` call, and the four-way classification is cross-checked against the authors' own vectorised `define_regulated_curves` over a grid of α and `fc_lim`.
- `test_tools.py` — the seven tools, the resource, the prompt, and TOML generation (parsed back with `tomllib`).
- `test_reference.py` — citation, reported dataset values, provenance vocabulary, and honesty guards.

## Register with Claude Desktop

```json
{
  "mcpServers": {
    "curvecurator-dose-response": {
      "command": "/absolute/path/to/paper2agent-curvecurator-mcp/.venv/bin/curvecurator-mcp",
      "args": []
    }
  }
}
```

macOS `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows
`%APPDATA%\Claude\`. Transport is stdio; paths must be absolute.

---

## Conventions you need to know before calling anything

**Doses are non-zero and the control is implicit.** Responses are ratios to the
control, so the pipeline contributes one control point at `x = −∞` with ratio 1.0.
`n` = number of finite dose points **+ 1**. Passing a dose of `0.0` is an error, not
a control. This is what the paper means by *"n = 17 data points (doses and one
control)"* for CTRP and *"9 data points"* for Kinobeads.

**n must exceed 4**, and it drives the effective degrees of freedom and therefore
`s0` — so a curve with missing values is scored against its own `s0`.

**pEC50 = −log10(EC50 in M)**; x-values are log10-molar.

---

## Tools

### 1. `fit_dose_response_curve(doses, responses, dose_unit="nM", …)`

Fits the mean model (M0) and the 4-parameter log-logistic model (M1), then
evaluates `F = (SSE_M0 − SSE_M1)/SSE_M1 · (n/k)`.

```json
{
  "doses": [0.0316, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0, 316.0],
  "responses": [1.0, 0.98, 0.95, 0.80, 0.55, 0.30, 0.18, 0.14, 0.13]
}
```

```json
{
  "n_data_points": 10,
  "curve_parameters": {"pEC50": 8.528, "EC50_molar": 2.963e-09, "slope": 1.145,
                       "front": 1.003, "back": 0.125},
  "curve_fold_change_log2": -2.945,
  "goodness_of_fit": {"r_squared": 0.9999, "rmse": 0.0043, "auc": 0.558},
  "null_model": {"intercept": 0.603, "rmse": 0.364},
  "statistics": {"recalibrated_f_value": 18057.0, "p_value": 2.43e-12,
                 "dfn": 5.0, "dfd": 5.944, "loc": 0.12, "optimized_dofs": true},
  "potency_within_assayed_range": true
}
```

`optimized_dofs=false` selects the linear-model `dfn = k−1, dfd = n−k` fallback,
which the paper shows is poorly calibrated here — it is exposed only so the
difference can be demonstrated.

### 2. `classify_dose_response_curve(doses, responses, alpha=0.05, fc_lim=0.45, …)`

The full single-curve pipeline: fit → recalibrated F → `s0` → s0-adjusted F →
relevance score → four-way classification.

```json
{
  "classification": {
    "curve_regulation": "down",
    "criteria": {"relevance_score_above_cutoff": true,
                 "abs_fold_change_at_least_fc_lim": true,
                 "pEC50_within_filter": true,
                 "null_intercept_within_half_fc_lim": false,
                 "null_rmse_within_limit": false},
    "scoring": {"s0": 0.214, "s0_adjusted_f_value": 170.2,
                "relevance_score": 5.492, "relevance_score_cutoff": 1.301,
                "is_valid_p_value": false}
  }
}
```

The four categories are the paper's: `up`, `down`, `not`, `unclear`.
**`unclear` is a result, not a failure** — it is the paper's deliberate holding pen
for curves that are neither confidently regulated nor confidently flat, so that
high-variance curves stay out of a negative training set. `not` requires *both* a
null-model intercept within ±`fc_lim`/2 of 1.0 (log2) *and* a null RMSE ≤
`not_rmse_limit` (default 0.1).

### 3. `compute_relevance_score(f_value, curve_fold_change_log2, n_data_points, …)`

Rescore existing F-values and fold changes — e.g. a CurveCurator `curves.txt`
column — under different asymptotes without refitting.

With `fc_lim=0` the relevance score is exactly `−log10(p)` and `is_valid_p_value`
is `true`. With `fc_lim>0` it is **not a p-value**: the fold-change asymptote
suppresses false positives at fixed α, so the number orders curves by significance
*and* effect size and means nothing on its own. Every payload says which case
you're in.

### 4. `map_decision_boundary(fold_changes, alpha=0.05, fc_lim=0.45, n_data_points=9)`

The hyperbolic boundary, for drawing on a volcano plot.

| curve fold change (log2) | `minus_log10_p_value_cutoff` | reachable |
|---|---|---|
| 0.05 | `null` | **false** |
| 0.6 | 4.105 | true |
| 2.0 | 1.757 | true |

A fold change inside the asymptote band is **unreachable**: no amount of
significance can make such a curve relevant. In relevance-score space this same
boundary is a horizontal line at `−log10(α)`.

> The authors' function is named `map_fc_to_pvalue_cutoff` and its docstring says
> it returns "p-value cutoffs", but it returns `−logsf · log10(e)`, i.e. −log10(p).
> This server names the field accordingly. It also mirrors the authors' dashboard in
> calling that function with `loc = 0`, which differs from the `loc = 0.12` used for
> curve p-values.

### 5. `estimate_target_decoy_fdr(curves, doses, alpha=0.05, fc_lim=0.45, …)`

Decoys are drawn by `curve_curator`'s simulator from the **empirical noise of the
curves you supply**, then pushed through the identical fit-and-classify path.
`FDR = (decoys above threshold + 1) / (targets above threshold + 1)`, scaled by the
target:decoy ratio.

Returns global and boundary-filtered FDR, classification counts, and the names of
the regulated curves. Pass `random_seed` for reproducibility. The estimate needs
enough curves to describe the assay's variance — a handful gives an unstable number,
and the `+1` pseudocount floors it.

### 6. `generate_curvecurator_config(doses, preset=…, …)`

Emits a valid TOML parameter file for the real CLI, which is where the dashboard and
a dataset-wide FDR actually live:

```bash
CurveCurator params.toml          # fit, classify, dashboard
CurveCurator params.toml --fdr    # + target-decoy FDR
```

Presets carry the asymptotes and preprocessing the paper used:

| preset | α | `fc_lim` | notes |
|---|---|---|---|
| `kinobeads` | 0.10 | 0.50 | LFQ protein, 9 points, direct binders only |
| `ctrp` | 0.05 | 0.30 | `control_fold_change = true` — several drugs already regulate at the lowest dose |
| `decryptm` | 0.05 | 0.45 | TMT peptide; 46% less stringent than the original decryptM cutoff |

A control dose of `0.0` is prepended for you, and `mtc_method = 'sam'` is set so
FDR estimation is available at all.

### 7. `describe_paper_dataset(dataset)`

What the article reports for `kinobeads`, `ctrp` or `decryptm` (aliases such as
`viability`, `phosphoproteome`, `klaeger` resolve). An unresolved name returns the
available list rather than a guess.

## Resource

`curvecurator://paper-summary` — structured JSON: the statistical framework, the
implementation-binding and version-fidelity record, pipeline defaults, all three
reprocessed datasets, the authors' four stated limitations, and an explicit
`not_reproduced_here` section.

## Prompt

`plan_dose_response_analysis(assay_description, n_curves)` — a seven-step workflow
that forces the reporting discipline the paper argues for: establish `n` including
the control; choose both asymptotes **on their own merits, never by tuning to a
target FDR**; classify into the four categories; quote a pEC50 only for curves
called `up` or `down`; never call the relevance score a p-value unless `fc_lim = 0`;
check that the lowest dose sits on the front plateau; and read a large-effect /
poor-p-value curve as a possible multi-event response the 4-parameter model cannot
describe.

---

## Where this server is deliberately silent

| Thing | Why |
|---|---|
| Gene symbols in the Afatinib / Dasatinib MoA figures | The PMC plain-text extraction dropped them. They are **not** guessed. See Fig. 4 of the article. |
| CTRP curve count | Methods say **373,324** drug–cell line combinations; Results say **379,324** curves. Both are reproduced as printed and flagged `internal_discrepancy`; the article does not reconcile them. |
| Equations 1–10 verbatim | Rendered as images. Coefficients come from the authors' code, not transcription. |
| Raw data | None of the three datasets is bundled — PRIDE `PXD005336`, `PXD037285`, and PharmacoGx for CTRP. |
| Supplementary notes | The article defers asymptote guidance to supplementary notes not available as text; the dataset presets are given as concrete anchors instead. |

Provenance tags in `src/curvecurator_mcp/data/paper_reference.json`: `paper_reported`,
`verified_against_source`, `implementation_detail`, `internal_discrepancy`. A test
fails the build if any other tag appears.

## Note for dose–response proteomics

The `decryptm` preset is the closest analogue for TMT phosphoproteome or
proteome-wide compound-response profiling: same measurement type, same data type,
same order of curve count. Two of the paper's cautions bite hardest in that setting.
First, if a compound is more potent than the assayed range the lowest dose is not on
the front plateau, fold changes compress, and the most potent responses are lost as
false negatives — `potency_within_assayed_range` flags this per curve. Second, the
4-parameter log-logistic model encodes a **single** binding event; a response driven
by several events tends to come out with a large effect size and a poor p-value
rather than a clean fit, so that combination is a modelling signal, not noise.

The asymptotes are assay-specific. Anchoring `fc_lim` to a preset is a starting
point, not a transfer of validity — it should be set against the measurement
variance of the assay actually run.

## Layout

```
paper2agent-curvecurator-mcp/
├── src/curvecurator_mcp/
│   ├── data/paper_reference.json  # curated, provenance-tagged paper record
│   ├── server.py                  # 7 tools, 1 resource, 1 prompt (stdio)
│   ├── engine.py                  # binding layer over curve_curator
│   ├── config_builder.py          # TOML generation + the paper's three presets
│   └── reference.py               # reference loading and dataset resolution
└── tests/                         # 145 tests
```

## References

- Bayer FP, Gander M, Kuster B, The M. CurveCurator: a recalibrated F-statistic to assess, classify, and explore significance of dose–response curves. *Nat Commun* 14:7902 (2023). [doi:10.1038/s41467-023-43696-z](https://doi.org/10.1038/s41467-023-43696-z)
- `curve_curator` source and example datasets: <https://github.com/kusterlab/curve_curator>
- Tusher VG, Tibshirani R, Chu G. Significance analysis of microarrays applied to the ionizing radiation response. *PNAS* **98**:5116–5121 (2001). [doi:10.1073/pnas.091062498](https://doi.org/10.1073/pnas.091062498) — the s0 fudge-factor principle the relevance score adapts
- Klaeger S et al. The target landscape of clinical kinase drugs. *Science* **358**:eaan4368 (2017). [doi:10.1126/science.aan4368](https://doi.org/10.1126/science.aan4368) — Kinobeads dataset, PRIDE PXD005336. The CurveCurator article paraphrases this title as "…clinical kinase inhibitors".
- Zecha J et al. Decrypting drug actions and protein modifications by dose- and time-resolved proteomics. *Science* **380**:93–101 (2023). [doi:10.1126/science.ade3925](https://doi.org/10.1126/science.ade3925) — decryptM dataset, PRIDE PXD037285

Supporting citations verified against PubMed records (PMIDs 11309499, 29191878, 36926954).
