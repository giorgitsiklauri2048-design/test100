# Coordinator acceptance: Stage 2 (source execution)

`execution` gate **passed** (exit 0). Active tutorials: `kinobeads_dasatinib`,
`viability_ctrp_40`. Active module: `cli_wrapper`. One recorded exclusion:
`decryptm_dasatinib`.

| Assignment | Status | Runs |
|---|---|---|
| `kinobeads_dasatinib` | succeeded | base (791.87 s), `--mad` ×2 (623.43 s, 504.63 s), all exit 0 |
| `viability_ctrp_40` | succeeded | base (948.89 s), `--fdr` ×2 (1132.87 s, 591.22 s), all exit 0 |
| `decryptm_dasatinib` | cancelled | excluded on resource grounds; no curves file produced |

Runtimes are inflated by CPU contention and are not characteristic of the tool.

## The determinism split, now proven rather than inferred

Stage 1 predicted this split from source inspection alone (no RNG in
`quantification.py`/`models.py`/`toolbox.py`/`quality_control.py`; unseeded draws
at four sites in `data_simulator.py`; no seed exposed anywhere in the CLI). The two
`--fdr` runs on identical input form a natural experiment that confirms it exactly:

| Quantity | Across the two `--fdr` runs |
|---|---|
| `pEC50` | max abs diff **0.000e+00** |
| `Curve Relevance Score` | max abs diff **0.000e+00** |
| `Curve F_Value` | max abs diff **0.000e+00** |
| `Curve q_Value` (decoy-dependent) | max abs diff **4.633e-02** |
| Reported FDR | **0.003704** vs **0.001852** (~2×) |

Target-curve fitting is bit-identical; only the decoy-dependent quantities move.
This is the clearest possible demonstration that the deterministic core and the
unseeded FDR estimate must be verified by different means.

`--mad` determinism was likewise proven empirically, not assumed: two independent
runs produced `mad.txt` with identical sha256
(`ff895789d262d7a344c6ff2832a2215fc9b28ddc403877ca12c7dd0ad4ec7a36`). The executor
additionally found that `--mad` leaves `curves.txt` byte-identical to the base run,
so the flag adds the noisy-channel analysis without touching curve fitting.

## `--fdr` structural checks (no ground truth exists, none asserted)

- Artifacts appear as the TOML `[Paths]` defaults dictate: `decoys_40.0.txt`
  (58 columns) and `fdr_40.0.txt`.
- Decoy count **1211** in both runs against **1211** target curves, exactly
  consistent with the code-default `decoy_ratio = 1.0` (unset in the TOML).
- Both reported FDR values lie in [0, 1].
- No exact FDR or decoy value is asserted as expected anywhere. The between-run
  difference is recorded as correct behaviour of an unseeded simulation.

## Reference agreement

Covered in detail in `reports/coordinator-reference-agreement-analysis.md`.
Headline: across both examples, **714 curves classified `up`/`down` agree to
≤ 2e-06 on `pEC50`**, and **`Curve Regulation` matches exactly on all 2,381
curves** (1170/1170 and 1211/1211).

One discrepancy between the executor's count and the coordinator's own
measurement, recorded rather than reconciled by adopting either number: the
viability executor reported "5 of 1211 rows exceed 1e-4", while the coordinator's
independent any-column pass counts **3** rows above 1e-4, 2 above 1e-3 and 1 above
1e-2. The difference is presumably a counting convention (per-column occurrences
versus per-row maxima, or absolute versus relative). It is immaterial to the
conclusion, because **zero** significant curves exceed any of those thresholds on
either count, but the coordinator's figures are the ones used downstream.

A plausible cause the executor identified for the residual drift, worth carrying
forward: this environment runs numpy 2.4.6 / scipy 1.17.1, while the shipped
reference files were generated with older versions (the shipped dashboards embed
Bokeh 3.7.0 against 3.7.3 here). Non-associative floating-point summation in a
non-convex least-squares fit is sufficient to move a weakly-identified inflection
point without changing any classification.

## Reference integrity

The overwrite hazard never materialised. The authoritative check is that the pinned
checkout is itself a git repository:
`git -C repo/curve_curator status --porcelain --untracked-files=all` returns
completely empty with HEAD at `71e46f7222f825f446e9aff3fb5a3bee9473e309`. No
tracked file modified, no stray file added, by any of the three executors. All
three independently captured before/after hashes of the shipped files as well.

## Requirements carried into Stage 3

1. Align output comparisons by row order or a composite key, **never by `Name`
   alone** — `kinobeads_Dasatinib/curves.txt` has 1170 rows with a duplicated
   `Name` (`TMPO`), which silently cross-expands an index join.
2. Assert **exact** agreement on `Curve Regulation`; it reproduces perfectly and is
   the sharpest regression signal available.
3. Apply tight `pEC50` tolerances **only** to curves classified `up`/`down`, and
   state that restriction rather than using a loose global tolerance that would
   mask a real regression in a significant curve.
4. For `--fdr`, assert structure and bounds only. Any test asserting an exact FDR
   or decoy value is invalid by construction.
5. The verifier must be a **fresh agent**, distinct from the implementer.

## Honest limitations of Stage 2 evidence

- Nothing here exercises the wrapper at the excluded scale (~16 MiB input,
  ~12k curves). Inputs covered are 8.2 MiB and 155 KiB.
- `--mad` and `--fdr` have no external ground truth. `--mad` rests on an internal
  determinism proof; `--fdr` on structural checks only.
- `-r/--random` was deferred at Stage 1 and is not exercised at all.
- Runtimes measured here reflect heavy CPU contention and must not be quoted as
  performance characteristics in `USAGE.md`.
