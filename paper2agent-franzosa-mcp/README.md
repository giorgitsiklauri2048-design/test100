# Franzosa et al. (2021) HepaRG Toxicogenomics — MCP Server

An MCP server exposing the assay design, analysis pipeline, and reference-chemical
results of:

> Franzosa JA, Bonzo JA, Jack J, Baker NC, Kothiya P, Witek RP, Hurban P, Siferd S,
> Hester S, Shah I, Ferguson SS, Houck KA, Wambaugh JF.
> **High-throughput toxicogenomic screening of chemicals in the environment using
> metabolically competent hepatic cell cultures.**
> *npj Systems Biology and Applications* **7**:7 (2021).
> [doi:10.1038/s41540-020-00166-2](https://doi.org/10.1038/s41540-020-00166-2)
> · PMID [33504769](https://pubmed.ncbi.nlm.nih.gov/33504769/) · PMC7840683

Source text retrieved from PubMed Central.

---

## Read this before using the server

This server was specified from a task brief containing four factual errors about
the source study. Rather than implement the brief, the divergences were verified
against the article full text and resolved in favour of the paper. **If you arrived
here expecting the behaviour in the left column, the right column is what you get
and why.**

| Commonly misattributed to this paper | What the paper actually reports |
|---|---|
| TempO-Seq, 500-gene liver panel | **93 transcripts**, TaqMan qRT-PCR on **Fluidigm 96.96 dynamic arrays** (96 assays including *ACTB*, *GAPDH*, *POLR2A*) |
| Benchmark concentration (BMC) at BMR = 1.349 SD | **tcpl** pipeline: constant vs. **Hill** vs. **gain-loss**, AIC model selection, potency = **AC50** (`modl_ga`), efficacy = `modl_tp`. The strings *BMD*, *BMC*, *BMR* and *1.349* appear **zero times** in the article |
| Nrf2 oxidative-stress pathway | The Bayesian network models **six** receptors: **AhR, CAR, PXR, FXR, AR, PPARα**. *NFE2L2* appears once in the article — as a replacement *probe*, never as a modelled transcription factor |
| *npj Syst Biol Appl* **7**, 12 | *npj Syst Biol Appl* **7**, **7** |

BMR = 1.349 SD is the BMDExpress / NTP transcriptomic dose-response convention
(Thomas et al., *Toxicol Sci* 98:240–248, 2007; NTP Research Report 5, 2018). It
belongs to a different pipeline and is **not** implemented here. `fit_concentration_response`
does not accept a `bmr` argument, and no result field is a benchmark dose quantity —
both are enforced by tests.

### Provenance discipline

Every value carries a provenance tag. Nothing is invented to fill a gap.

| Tag | Meaning |
|---|---|
| `paper_reported` | Stated explicitly in the article text |
| `external_identifier` | CAS RN added for lookup; **not** from the article |
| `synthetic` | Test fixture generated for this package; **not** measured data, never citable |
| `not_reported` | The article does not report it; the payload names where it does live |

Per-chemical AC50 and cytotoxicity values are **not** in the article text — they are
distributed in `LTEA_Level5_20191119.zip` and via the EPA CompTox Chemicals Dashboard.
This package deliberately bundles **no** external archives (the imagery supplement alone
is >15 GB), so those fields return `null` with `not_reported` rather than a plausible
fabrication.

---

## How Paper2Agent was leveraged

**It was not.** Stated plainly because the alternative would be a false claim in a
scientific artefact.

The task brief instructed reuse of a Paper2Agent skill installed in a prior session.
That state does not exist in this environment, verified before any code was written:

```
$ git ls-remote --heads origin          # no branches, no commits
$ ls -la /home/user/test100             # .git only
$ find / -iname "*paper2agent*"         # no matches
$ ls ~/.claude/skills/                  # session-start-hook, synced/ — no paper2agent
$ python3 -c "import mcp"               # ModuleNotFoundError
```

Cloud sessions receive a fresh container and the repository was empty, so nothing
from the earlier session survived. Cloning and running the Paper2Agent pipeline was
weighed against writing the server directly; the direct build was chosen to stay
within the session's compute budget. The server is therefore built against the
official Python MCP SDK (`MCPServer`, stdio transport), following the Paper2Agent
*pattern* — paper → typed tools + resource + guided prompt — without its tooling.

---

## Install

```bash
cd paper2agent-franzosa-mcp
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Requires Python ≥ 3.10, `mcp[cli]>=2.0`, numpy, scipy.

> **SDK version note.** This targets MCP SDK **2.x**, where `FastMCP` was renamed
> `MCPServer`. On SDK 1.x, change the import in `src/franzosa_mcp/server.py` to
> `from mcp.server.fastmcp import FastMCP` and use `FastMCP(...)`; the decorator
> API is otherwise identical.

## Test

```bash
.venv/bin/python -m pytest -q
# 101 passed
```

Coverage: curve-fit correctness and model selection (`test_curve_fit.py`), all four
tools plus the resource and prompt (`test_tools.py`), and dataset provenance guards
(`test_data_integrity.py`) that fail the build if a fabricated potency, a wrong
citation, a TempO-Seq claim, or a BMR field is ever introduced.

## Register with Claude Desktop

Add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "franzosa-heparg-toxicogenomics": {
      "command": "/absolute/path/to/paper2agent-franzosa-mcp/.venv/bin/python",
      "args": ["-m", "franzosa_mcp"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/paper2agent-franzosa-mcp/src"
      }
    }
  }
}
```

After `pip install -e .` the console script also works, dropping the `PYTHONPATH`:

```json
{
  "mcpServers": {
    "franzosa-heparg-toxicogenomics": {
      "command": "/absolute/path/to/paper2agent-franzosa-mcp/.venv/bin/franzosa-mcp",
      "args": []
    }
  }
}
```

Transport is stdio. Paths must be absolute.

---

## Tools

### 1. `query_chemical_profile(chemical_name_or_cas: str) -> dict`

Resolves by name, synonym, or CAS RN against the ten reference activators plus the
metabolic control (aflatoxin B1) named in the article text.

```json
{ "chemical_name_or_cas": "rifampicin" }
```

```json
{
  "found": true,
  "name": "Rifampicin",
  "casrn": "13292-46-1",
  "casrn_provenance": "external_identifier",
  "role_in_study": "PXR reference activator",
  "receptor_activation": [
    {
      "receptor": "PXR",
      "full_name": "Pregnane X receptor (NR1I2)",
      "uniprot": "O75469",
      "canonical_markers_reported_in_text": ["CYP3A4"]
    }
  ],
  "canonical_marker_reported": "CYP3A4",
  "potency": {
    "ac50_uM": null,
    "provenance": "not_reported",
    "note": "AC50 (tcpl modl_ga) is the study's potency metric. It is not tabulated in the article text; retrieve it from LTEA_Level5_20191119.zip or the EPA CompTox Chemicals Dashboard."
  }
}
```

Isomers do not collide: `p,p'-DDT` → CAR + PXR; `o,p'-DDT` → PXR only. An unresolved
query returns `found: false` with the resolvable list — never a guess.

### 2. `fit_concentration_response(concentrations, responses, fold_change_cutoff=1.2, bmad=None, bmad_multiplier=3.0) -> dict`

Reproduces the study's pipeline: constant / Hill / gain-loss under a Student's *t*
error model (4 df), AIC selection, AC50 as potency. Concentrations in µM; responses
as log2 fold-change (the tcpl `rval`, i.e. ΔΔCt vs. the plate-wise DMSO control median).

```json
{
  "concentrations": [0.03, 0.1, 0.32, 1.0, 3.16, 10.0, 31.6, 100.0],
  "responses": [0.02, 0.05, 0.11, 0.41, 1.12, 1.78, 2.01, 2.08],
  "bmad": 0.05
}
```

```json
{
  "winning_model": "hill",
  "direction": "up",
  "ac50_uM": 2.839,
  "efficacy_modl_tp_log2fc": 2.095,
  "hit_call": true,
  "hit_criteria": {
    "rule": "systematic model (hill or gnls) AND (exceeds 3x BMAD OR exceeds 1.2 fold-change)",
    "exceeds_bmad_threshold": true,
    "exceeds_fold_change_cutoff": true,
    "bmad_source": "supplied_plate_wide"
  }
}
```

Notes:

- The study's hit rule is a **disjunction** (`3×BMAD` *or* `1.2` fold-change). Both
  components are returned separately so a conjunctive rule can be applied downstream.
- Supply a **plate-wide** `bmad`. BMAD is defined over all normalised responses at
  the two lowest concentrations across the plate; a single eight-point curve gives
  only two values, so the fallback is a degenerate estimate and is flagged
  `bmad_source: "single_curve_estimate"` with a caveat.
- Pass `bmad_multiplier=10.0` for LDH cytotoxicity endpoints.
- A winning **gain-loss** model flags high-concentration signal loss, which the study
  interprets as cytotoxicity rather than receptor-mediated repression.

### 3. `analyze_pathway_enrichment(significant_genes: list[str]) -> list[dict]`

Maps transcripts to the six modelled receptors plus an explicitly-flagged NFE2L2/Nrf2
annotation. Hypergeometric over-representation against the 93-transcript panel as
universe, Benjamini–Hochberg FDR.

```json
{ "significant_genes": ["CYP1A1", "CYP1A2", "CYP3A4"] }
```

| pathway | matched | q (BH) | modelled by network |
|---|---|---|---|
| AhR | CYP1A1, CYP1A2 | 0.0049 | yes |
| PXR | CYP3A4 | 0.1129 | yes |
| AR | — | `null` | yes (no marker named in text) |
| NFE2L2 | — | 1.0 | **no** |

**Read the `caveats` field before interpreting any q-value.** The marker sets contain
only the canonical genes the article names in text, so they hold 0–2 genes and are
severely underpowered — a non-significant q is not evidence of absence. More
importantly, the study's own inference is a **Bayesian posterior probability of
receptor activation** from concentration-response patterns, not an enrichment test;
these q-values are a convenience summary and are **not** comparable to the study's
reported probabilities. Substantial cross-talk was inferred between the six receptors,
so marker overlap does not resolve to a single initiating event.

Off-panel symbols and probes withdrawn for excessive non-detects (*KLK3*, *MMP1*,
*SLC10A1*, *SLC22A6*) are flagged in `caveats`.

### 4. `compare_metabolic_competence(cell_type="HepaRG", reference="primary_human_hepatocytes") -> dict`

Accepts `HepaRG`, `primary_human_hepatocytes` (or `PHH`), `HepG2`.

```json
{
  "comparison": {
    "relative_metabolic_activity_ratio": 0.1,
    "ratio_note": "Ratio of overall metabolic activity relative to human liver, derived from the article's approximate statements. It is a whole-culture figure, not a per-enzyme expression ratio."
  },
  "cyp450_evidence": {
    "CYP3A4": {
      "receptor": "PXR",
      "evidence": "Rifampicin, the PXR reference activator, was active against CYP3A4. Independently, omeprazole produced a robust 4.2-fold induction of CYP3A4 after 48 h — a metabolite-driven response consistent with metabolically competent systems and with primary human hepatocyte cultures.",
      "omeprazole_fold_induction": 4.2,
      "baseline_ratio_vs_PHH": null,
      "provenance": "not_reported"
    }
  }
}
```

The 0.10 figure is the article's own approximation — HepaRG under the study's 0.5%
DMSO Zone-2 induction medium was "likely ~10% of human liver and suspensions of
primary human hepatocytes". It is a **whole-culture** activity figure, not a
per-enzyme expression ratio. The article publishes **no** table of baseline CYP450
expression ratios between HepaRG and PHH, so `baseline_ratio_vs_PHH` is `null` for
CYP1A2, CYP2B6, and CYP3A4. HepG2 comparisons return `null` with
`"Not computable"` — the article characterises HepG2 only qualitatively.

---

## Resource

`toxicogenomics://paper-summary` — structured JSON: study design, assay parameters,
analysis pipeline, the Bayesian network, screening summary (1060 chemicals tested;
1037 with ≥1 systematic relationship; 718 after omitting curve-fit warning flags;
*CYP1A1* up in 360, *CYP2B6* up in 352, *CYP2E1* down in 323; 65% up / 35% down),
metabolic competence, EPA hazard-screening context, and `scope_disclaimers` naming
each misattribution above.

## Prompt

`screen_novel_chemical(chemical_name="", transcript="")` — a six-step workflow:
establish the reference frame from the resource → check whether the chemical is already
characterised → fit each transcript and report the criterion that fired → map hits to
initiating events with the power caveats → qualify the metabolic context → report.

The prompt hard-constrains the write-up: report AC50, never a BMC or BMD; never present
a `synthetic` or `not_reported` value as a measured result; name the external archive
where an unreported value lives.

---

## Study parameters at a glance

| | |
|---|---|
| Cell model | Differentiated human HepaRG, single lot, ~100,000 cells/well, collagen I 96-well |
| Vehicle | 0.5% DMSO induction medium (Zone-2-like differentiation) |
| Platform | TaqMan qRT-PCR, Fluidigm 96.96 dynamic arrays, 93 transcripts |
| Library | 1060 ToxCast chemicals, eight-point concentration-response |
| Endpoints | 2 per transcript (up/down mode) + 1 LDH cytotoxicity |
| Assay suite | "LTEA" (Life Technologies + Expression Analysis) |
| Positive controls | Phenobarbital (transcriptomics), aflatoxin B1 (metabolic) |
| Potency / efficacy | AC50 (`modl_ga`) / modelled top (`modl_tp`) |
| Transcriptomic hit | > 3× BMAD **or** > 1.2 fold-change at any concentration |
| Cytotoxicity hit | > 10× BMAD |
| Network | 3-step Bayesian; 45 responsive transcripts → 13 excluded → 32 retained; 1053 chemicals |

## Layout

```
paper2agent-franzosa-mcp/
├── data/sample_data.json          # provenance-tagged study data + labelled fixtures
├── src/franzosa_mcp/
│   ├── server.py                  # 4 tools, 1 resource, 1 prompt (stdio)
│   ├── curve_fit.py               # tcpl constant/Hill/gain-loss, Student's t, AIC
│   ├── receptors.py               # receptor mapping, hypergeometric + BH
│   └── data_access.py             # dataset loading, name/synonym/CAS resolution
└── tests/                         # 101 tests
```

## References

- Franzosa JA et al. *npj Syst Biol Appl* 7:7 (2021). [doi:10.1038/s41540-020-00166-2](https://doi.org/10.1038/s41540-020-00166-2)
- Filer DL et al. tcpl: the ToxCast pipeline for high-throughput screening data. *Bioinformatics* 33:618–620 (2017). [doi:10.1093/bioinformatics/btw680](https://doi.org/10.1093/bioinformatics/btw680)
- Thomas RS et al. Application of transcriptional benchmark dose values. *Toxicol Sci* 98:240–248 (2007). [doi:10.1093/toxsci/kfm092](https://doi.org/10.1093/toxsci/kfm092) — *the BMR = 1.349 SD convention, cited here only to mark what this server does not implement*
- UniProt: AhR P35869 · CAR Q14994 · PXR O75469 · FXR Q96RI1 · AR P10275 · PPARα Q07869 · NFE2L2 Q16236

Article metadata and full text retrieved via PubMed / PubMed Central.
