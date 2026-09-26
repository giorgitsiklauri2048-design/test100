# Coordinator analysis: reference agreement of the base pipeline runs

Independent check by the coordinator, not delegated. It answers the one open
scientific question raised by interim executor data: a 0.206 log-unit `pEC50`
deviation against the shipped reference.

**Verdict: the deviation is confined to non-significant curves. Agreement on
significant curves is at the 1e-06 level or better, and the pipeline's own
classification is reproduced exactly on all 2,381 curves compared.**

Scope: the two **base** runs only (no flags). The `--mad` and `--fdr` runs had not
finished when this was written and are not covered here.

## Method

For each example, the produced curves file was compared against the shipped
reference from the pinned checkout (`71e46f7`).

A first pass joined on the `Name` column and produced a nonsensical
`1170/1169` match count. Cause: `kinobeads_Dasatinib/curves.txt` contains **1170
rows with one duplicated `Name`** (`TMPO`), so an index join cross-expands that
identifier and silently compares mismatched row pairs. The analysis was redone
with **positional alignment**, after first asserting that the `Name` sequence is
identical position-by-position in reference and produced files (it is, for both
examples). All figures below come from the corrected pass.

This is a real property of the data, not a one-off: **a comparison keyed on
`Name` is unsafe for this repository.** Stage 3's verifier must align by row
order or a composite key.

## Results, stratified by the pipeline's own `Curve Regulation` verdict

### kinobeads_dasatinib — 1170 rows

| Regulation | n | max abs ΔpEC50 |
|---|---|---|
| `up` | 109 | 1.21e-11 |
| `down` | 66 | 2.29e-10 |
| `not` | 94 | 3.21e-05 |
| `unclear`/none | 901 | 1.27e-06 |
| **significant (`up`+`down`)** | **175** | **2.29e-10** |

- Curves with abs ΔpEC50 > 0.01: **0**
- `Curve Regulation` exact match: **1170 / 1170**
- Worst abs deviation across all ten scientific columns: `Curve Slope` 4.93e-03;
  every other column ≤ 3.21e-05.

### viability_ctrp_40 — 1211 rows

| Regulation | n | max abs ΔpEC50 |
|---|---|---|
| `up` | 3 | 1.03e-11 |
| `down` | 536 | 1.99e-06 |
| `not` | 491 | 4.65e-05 |
| `unclear`/none | 181 | **2.06e-01** |
| **significant (`up`+`down`)** | **539** | **1.99e-06** |

- Curves with abs ΔpEC50 > 0.01: **1**, and it is **not** significant
- `Curve Regulation` exact match: **1211 / 1211**

The single outlier:

| Name | pEC50 ref | pEC50 new | abs diff | Regulation | R² | F_Value | Relevance Score |
|---|---|---|---|---|---|---|---|
| `GSU_NPC-26` | 2.6042 | 2.3979 | 0.2062 | `unclear`/none | 0.3453 | 2.165 | 0.0346 |

Its relevance score of 0.0346 is far below the 0.05-alpha cutoff of
−log10(0.05) = 1.301, and R² = 0.345 with F = 2.165 describes a poorly determined
fit. Every other column's worst case in this dataset occurs on this same curve.

## Interpretation

On a flat or noisy dose–response, the least-squares objective is nearly flat in
`pEC50`, so the inflection point is weakly identified and two runs of a
non-convex optimiser can settle at materially different `pEC50` values while
agreeing closely on everything that determines the verdict. That is what the
stratification shows: where the objective is well conditioned (significant
curves) agreement reaches 1e-10 to 1e-11, which is tighter than text round-trip
formatting alone would explain and indicates the fits are effectively
bit-reproducible there.

This is an empirical instance of the source paper's own caution that only
relevant curves have interpretable curve parameters, and of the repository
dashboard's warning to "never interpret curve estimates from insignificant
curves".

No tolerance was tuned to reach this conclusion. The raw maximum deviation
(0.206) is reported as observed; the stratification explains where it lives
rather than shrinking it.

## Consequences

1. **Accept** the base-run reference agreement as strong evidence for the
   `cli_wrapper` tool: across both examples, 714 significant curves agree to
   ≤ 2e-06 on `pEC50`, and 2,381 of 2,381 classification calls match exactly.
2. **Stage 3 verifier requirements**, to be passed on explicitly:
   - align comparisons by row order or a composite key, never by `Name` alone;
   - assert exact agreement on `Curve Regulation`, which reproduces perfectly and
     is therefore the sharpest available regression signal;
   - apply any tight numerical tolerance on `pEC50` only to curves classified
     `up` or `down`, and state that restriction rather than applying a loose
     global tolerance that would hide a real regression in a significant curve.
3. **`USAGE.md` limitation to document:** `pEC50` from a curve that is not
   classified `up` or `down` is not reproducible run to run and must not be
   reported as a measurement.
4. Unaffected by this analysis: `--mad` and `--fdr` evidence, still pending, and
   the excluded decryptM example, which means nothing here speaks to behaviour at
   ~16 MiB / ~12k-curve scale.
