import json

report = {
  "execution_id": "viability_ctrp_40",
  "module": "cli_wrapper",
  "status": "success",
  "status_detail": "Base (no-flag) run reproduced with exit 0 and matches the shipped reference curves_40.0.txt to a justified floating-point tolerance on 1206-1210 of 1211 rows per column, with the categorical Curve Regulation call matching exactly on all 1211 rows. A small number of weak/insignificant curves show larger (but still bounded and explained) numeric deviations without changing their classification -- reported plainly below, not smoothed over. --fdr was run twice; it succeeded both times (exit 0) and produced structurally valid, internally consistent decoy/FDR artifacts whose exact values legitimately differ between the two runs because the underlying decoy simulation is unseeded, as documented in the coordinator's pre-verified defect record.",
  "execution_mode": "cli_subprocess",
  "execution_path": "notebooks/viability_ctrp_40/work/base/stdout.log",
  "execution_path_note": "No notebook was used; CurveCurator is a native CLI and was invoked directly as a subprocess three times (base, fdr_run1, fdr_run2), each in its own isolated working directory. execution_path points to the base run's captured stdout as the primary reproduction; fdr_run1/fdr_run2 stdout/log paths are recorded under each run's entry below.",

  "source": {
    "assigned_source_path": "repo/curve_curator/example_datasets/viability_CTRP_40/parameters_40.0.toml",
    "source_url": "https://github.com/kusterlab/curve_curator.git",
    "pinned_commit": "71e46f7222f825f446e9aff3fb5a3bee9473e309",
    "pinned_commit_verified": True,
    "pinned_commit_verification_note": "git log -1 --format='%H %ci %s' inside repo/curve_curator/curve_curator's checkout printed exactly 71e46f7222f825f446e9aff3fb5a3bee9473e309 2025-05-24 12:33:43 +0200 'Update README.md', origin=https://github.com/kusterlab/curve_curator.git, `git status --porcelain` empty (clean tree). `git describe --tags` = rel-0-06-0-1-g71e46f7.",
    "parameters_toml_sha256": "e127f39da561d01dd5cf1cba68f53ca5ccaf0e4090a570ec753bd956a94849af",
    "parameters_toml_sha256_matches_assignment": True,
    "input_dose_responses_tsv_sha256": "03c4b69a046a78552507fba55cf635284781247687e21b0e67ba29029cac9a6b",
    "input_dose_responses_tsv_size_bytes": 158866,
    "example_description": "CTRPv2 cell-viability dose-response subset (40uM top dose), condition='N/A', treatment_time='3 d'; 17 experiments/doses [0, 0.0012 .. 40] uM (dose_scale=1e-6, dose_unit=M), control_experiment=[0], measurement_type=data_type=search_engine='OTHER' (a pre-computed generic ratio table, not a raw search-engine output), control_fold_change=true, interpolation=true, alpha=0.05, fc_lim=0.3, available_cores=5 (as shipped; not edited -- see limitations for contention note), max_missing=4. decoy_ratio is not set in this toml, so the code default of 1.0 applies for the --fdr runs (verified in curve_curator/toml_parser.py set_default_values)."
  },

  "executable_identity": {
    "executable_path": "/home/user/test100/paper2agent-curvecurator/.venv/bin/CurveCurator",
    "resolved_via_readlink": "/home/user/test100/paper2agent-curvecurator/.venv/bin/CurveCurator",
    "reported_version_from_help": "CurveCurator (v0.6.0)",
    "python_backend": "/home/user/test100/paper2agent-curvecurator/.venv/bin/python (Python 3.11.15)",
    "python_module_file": "/home/user/test100/paper2agent-curvecurator/.venv/lib/python3.11/site-packages/curve_curator/__init__.py",
    "python_module_version": "0.6.0",
    "pip_show_summary": "Name: curve_curator, Version: 0.6.0, Author: Florian P. Bayer, License: Apache License, Version 2.0",
    "install_provenance_direct_url_json": {
      "url": "file:///home/user/test100/paper2agent-curvecurator/repo/curve_curator",
      "dir_info": {}
    },
    "install_provenance_note": "dist-info/direct_url.json confirms the installed distribution was built from the pinned local checkout at repo/curve_curator (not PyPI, not an editable/dev install). This matches the pinned commit verified above.",
    "key_runtime_dependency_versions": {
      "bokeh": "3.7.3",
      "numpy": "2.4.6",
      "pandas": "2.3.3",
      "scipy": "1.17.1",
      "statsmodels": "0.14.6",
      "note": "All satisfy repo/curve_curator/pyproject.toml's declared ranges (bokeh>=3.4.0,<3.8.0; numpy>=1.25.0,<3.0; pandas^2.1.0; scipy^1.10.1; statsmodels^0.14.0). The shipped dashboard_40.0.html was rendered with bokeh 3.7.0 (embedded CDN script tag), so this environment's 3.7.3 is a compatible but non-identical patch version -- see dashboard_html_check below."
    }
  },

  "hazard_mitigation": {
    "description": "The shipped parameters_40.0.toml declares curves_file=./curves_40.0.txt, decoys_file=./decoys_40.0.txt, fdr_file=./fdr_40.0.txt, dashboard=./dashboard_40.0.html, all relative to the toml's own directory. Running it in place inside repo/ would have overwritten the shipped ground-truth curves_40.0.txt/dashboard_40.0.html/curveCurator.log.",
    "mitigation_taken": "Copied parameters_40.0.toml + dose_responses_40.0.tsv from repo/curve_curator/example_datasets/viability_CTRP_40/ into three separate isolated run directories under notebooks/viability_ctrp_40/work/ (base/, fdr_run1/, fdr_run2/) before ever invoking the executable. repo/ was never used as a working directory and no CurveCurator invocation targeted a toml under repo/.",
    "repo_untouched_proof": {
      "note": "sha256 of the 5 shipped files in repo/curve_curator/example_datasets/viability_CTRP_40/ was recorded BEFORE the first run, again after the base run, and a final time after both --fdr runs completed. All three snapshots are identical.",
      "hashes": {
        "parameters_40.0.toml": "e127f39da561d01dd5cf1cba68f53ca5ccaf0e4090a570ec753bd956a94849af",
        "dose_responses_40.0.tsv": "03c4b69a046a78552507fba55cf635284781247687e21b0e67ba29029cac9a6b",
        "curves_40.0.txt": "a0217e3b1947600aec5c59ca5e1c41795a78cf753ff9573e74f3207f0901f55c",
        "curveCurator.log": "59342381103205684387b767baf591bb6671decad8d69b07cb4ede26610197d0",
        "dashboard_40.0.html": "744431567b15872b2d64bf1f8b7130149c8f6d01c6d468c1603b7d1f7132c1b4"
      },
      "verified_unmodified": True
    }
  },

  "runs": [
    {
      "run_name": "base",
      "purpose": "Reproduce the shipped example exactly (no flags) and compare against the shipped reference curves_40.0.txt/dashboard_40.0.html/curveCurator.log. Deterministic path: no RNG in quantification.py, models.py, or toolbox.py (independently re-verified by grep before this run).",
      "command": ["/home/user/test100/paper2agent-curvecurator/.venv/bin/CurveCurator", "./parameters_40.0.toml"],
      "working_directory": "/home/user/test100/paper2agent-curvecurator/notebooks/viability_ctrp_40/work/base",
      "exit_status": 0,
      "start_time_utc": "2026-09-26T22:02:43Z",
      "end_time_utc": "2026-09-26T22:18:30Z",
      "wall_clock_runtime_seconds": 948.89,
      "stdout_path": "notebooks/viability_ctrp_40/work/base/stdout.log",
      "stderr_path": "notebooks/viability_ctrp_40/work/base/stderr.log",
      "stderr_note": "stderr contains only a pandas FutureWarning (DataFrame.swapaxes deprecated -> use transpose) and tqdm carriage-return progress-bar spam from 5 parallel worker processes; no tracebacks or ERROR-level lines. Exit status (0) was captured directly from the process, not inferred by grepping stdout/stderr for the word 'error'.",
      "log_path": "notebooks/viability_ctrp_40/work/base/curveCurator.log",
      "log_diagnostics": {
        "curves_removed_missing_gt4": 9,
        "curves_removed_no_control": 0,
        "alpha": 0.05,
        "fc_lim": 0.3,
        "s0": 0.1692
      },
      "log_diagnostics_match_shipped_log": True,
      "note_on_runtime": "Runtime (~15.8 min) was slower than the shipped log's own fitting time (~26 s with 5 dedicated cores; see repo's curveCurator.log timestamps 16:33:40->16:34:06) because up to two sibling executor sessions (kinobeads_dasatinib, decryptm_dasatinib) were fitting curves concurrently on this container's 4 logical CPUs while the shipped toml's available_cores=5 was used unmodified for all three runs (never reduced; no run actually failed for lack of cores, so no edit was made per the assignment's instruction).",
      "outputs": [
        {"path": "notebooks/viability_ctrp_40/work/base/curves_40.0.txt", "sha256": "6d16700e0ccebdf43f9a218b3e23b4e19315ea95191e31cadac4e444c1592b0b", "size_bytes": 736011},
        {"path": "notebooks/viability_ctrp_40/work/base/dashboard_40.0.html", "sha256": "b7c7da7efff86d34b68c9cdcaa21fc17982f08eae667ca82b4c4333846e4e87c", "size_bytes": 663521},
        {"path": "notebooks/viability_ctrp_40/work/base/curveCurator.log", "sha256": "2763c267d42f77120d5b7399214cdaed3b41320b59c4afb7e3783840f623cfde", "size_bytes": 1318}
      ]
    },
    {
      "run_name": "fdr_run1",
      "purpose": "First of two independent --fdr (target-decoy FDR estimation) invocations. --fdr has no shipped ground truth anywhere in the repository (independently re-verified: grep for fdr/decoy across all three shipped example logs, including this one, returns zero hits), and its decoy simulation (curve_curator/data_simulator.py) draws from unseeded scipy.stats....rvs() [lines 42, 48, 123] and np.random.choice [line 116] with no seed exposed by the CLI, toml parser, or user_interface module. This example (smallest input, 1211 curves after filtering) was assigned the --fdr case specifically because the help text warns it doubles runtime.",
      "command": ["/home/user/test100/paper2agent-curvecurator/.venv/bin/CurveCurator", "--fdr", "./parameters_40.0.toml"],
      "working_directory": "/home/user/test100/paper2agent-curvecurator/notebooks/viability_ctrp_40/work/fdr_run1",
      "exit_status": 0,
      "start_time_utc": "2026-09-26T22:18:45Z",
      "end_time_utc": "2026-09-26T22:37:35Z",
      "wall_clock_runtime_seconds": 1132.87,
      "stdout_path": "notebooks/viability_ctrp_40/work/fdr_run1/stdout.log",
      "stderr_path": "notebooks/viability_ctrp_40/work/fdr_run1/stderr.log",
      "log_path": "notebooks/viability_ctrp_40/work/fdr_run1/curveCurator.log",
      "log_warning": "'Less then 10k decoys may result in inaccurate FDR estimations. Consider increasing the decoy_ratio parameter.' -- expected and harmless for this small example (1211 target curves); not an error, does not affect exit status.",
      "log_summary_line": "Estimated FDR for given user threshold is: 0.003704",
      "n_decoys_simulated": 1211,
      "outputs": [
        {"path": "notebooks/viability_ctrp_40/work/fdr_run1/curves_40.0.txt", "sha256": "8a55a006619b60988afa07abb44f6fd2286ba756aa96c9676f8cb24454d0573f", "size_bytes": 767668},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run1/decoys_40.0.txt", "sha256": "fe5f96d8b62132de7a5aeee514147843dec830d4b9cf56139ee0ddb009df9123", "size_bytes": 1249182},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run1/fdr_40.0.txt", "sha256": "7783cc2ee6819486aeacef34ccdd2e8ded54f7451662ede9fba5b4eb2bcebecb", "size_bytes": 44, "content": "Global FDR: 0.003704\nFiltered FDR: 0.003704"},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run1/dashboard_40.0.html", "sha256": "7e0ae94e3735fbdae280d99eaceeb94b25f8877b106c129a5defcf1abf47f3cb", "size_bytes": 663521},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run1/curveCurator.log", "sha256": "a0e22e2bca5115ef2f6ebafa6b43d786bc885d6fcc1e628f869672c3a99c6a50"}
      ]
    },
    {
      "run_name": "fdr_run2",
      "purpose": "Second, independent --fdr invocation on a fresh copy of the identical inputs, to empirically demonstrate and document the expected run-to-run variability of the unseeded decoy simulation (per assignment instructions: this difference must be reported as correct behavior, not silenced or presented as a defect).",
      "command": ["/home/user/test100/paper2agent-curvecurator/.venv/bin/CurveCurator", "--fdr", "./parameters_40.0.toml"],
      "working_directory": "/home/user/test100/paper2agent-curvecurator/notebooks/viability_ctrp_40/work/fdr_run2",
      "exit_status": 0,
      "start_time_utc": "2026-09-26T22:37:45Z",
      "end_time_utc": "2026-09-26T22:47:35Z",
      "wall_clock_runtime_seconds": 591.22,
      "stdout_path": "notebooks/viability_ctrp_40/work/fdr_run2/stdout.log",
      "stderr_path": "notebooks/viability_ctrp_40/work/fdr_run2/stderr.log",
      "log_path": "notebooks/viability_ctrp_40/work/fdr_run2/curveCurator.log",
      "log_summary_line": "Estimated FDR for given user threshold is: 0.001852",
      "n_decoys_simulated": 1211,
      "note_on_runtime": "Faster than fdr_run1 (591s vs 1133s) because CPU contention from sibling executor sessions had eased by this point in the run; both runs used the same unmodified available_cores=5 toml setting.",
      "outputs": [
        {"path": "notebooks/viability_ctrp_40/work/fdr_run2/curves_40.0.txt", "sha256": "6579371309597722ba5614d14d73c351ad10e97b954a0fded5e362cddace794e", "size_bytes": 768097},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run2/decoys_40.0.txt", "sha256": "41b52cba1a2e5fc191a556e9b3f26a0850421f01b7c5f4fc3708d3cef47eba63", "size_bytes": 1248373},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run2/fdr_40.0.txt", "sha256": "5ca8a66162809db2d79e6103e23f01d5158cac714d390d15be52d093e83031cd", "size_bytes": 44, "content": "Global FDR: 0.001852\nFiltered FDR: 0.001852"},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run2/dashboard_40.0.html", "sha256": "180cb48b1edebd4fb8d5f4c3b65d186972aede13ec3be60e03173b71870ee2ad", "size_bytes": 663521},
        {"path": "notebooks/viability_ctrp_40/work/fdr_run2/curveCurator.log", "sha256": "92ad900b9f0a843b70dc1cb6343bd036b47e0627b6a871c12941283fe7165edc"}
      ]
    }
  ],

  "randomness_and_seed_provenance": {
    "seed_exposed_by_cli": False,
    "seed_exposed_by_toml": False,
    "cli_random_flag": "-r/--random exists but drives a separate, destructive H0-simulation mode (data_simulator.sample, which overwrites the configured input data) and was NOT passed in any of the three runs performed here.",
    "rng_usage_scan": {
      "method": "grep for random|seed|np\\.random|scipy\\.stats.*rvs|RandomState across repo/curve_curator/curve_curator/*.py, independently re-confirmed by this executor",
      "findings": [
        "curve_curator/data_simulator.py: simulate_h0_dataset uses DEFAULT_VARIANCE_MODEL.rvs()/stats.norm.rvs() (unseeded); simulate_decoys uses np.random.choice() (line 116, unseeded) and stats.norm.rvs() (line 123, unseeded). This is the code path exercised only by --fdr and -r/--random.",
        "curve_curator/dashboard.py: draw_default_values() calls np.random.seed(8) then pd.Series.sample() -- a FIXED, constant seed used only for an illustrative plotting jitter element, not a source of run-to-run numerical variability and not related to the fitted curve values.",
        "curve_curator/quantification.py, models.py, toolbox.py, quality_control.py: no random/seed usage found -- these are the modules that perform the actual curve fitting exercised by ALL three runs (base, fdr_run1, fdr_run2)."
      ],
      "conclusion": "No seed mechanism exists anywhere in the CLI, toml parser, or user_interface module for --fdr's decoy simulation. This was not just asserted from reading source: it was empirically confirmed by running --fdr twice from fresh copies of identical input and observing that the fitted target-curve values (pEC50, Curve Relevance Score, Curve F_Value SAM Corrected) were bit-identical (max abs diff = 0.0) between fdr_run1 and fdr_run2, while the decoy files and every quantity derived from the target-decoy comparison (Curve q_Value, the FDR file) differed. The --fdr path is therefore irreproducible by exact value; only its structural/statistical validity can be checked, and no exact FDR or decoy value is asserted as 'expected' anywhere in this report."
    }
  },

  "base_run_reference_comparison": {
    "reference_file": "repo/curve_curator/example_datasets/viability_CTRP_40/curves_40.0.txt (sha256 a0217e3b1947600aec5c59ca5e1c41795a78cf753ff9573e74f3207f0901f55c, read-only, verified unmodified throughout)",
    "produced_file": "notebooks/viability_ctrp_40/work/base/curves_40.0.txt (sha256 6d16700e0ccebdf43f9a218b3e23b4e19315ea95191e31cadac4e444c1592b0b)",
    "comparison_method": "pandas.read_csv(sep='\\t') via /home/user/test100/paper2agent-curvecurator/.venv/bin/python; row/column/identifier checks after sorting both frames by 'Name', then per-column max absolute and max relative numeric differences over all 1211 aligned rows, an exact-match count on the categorical 'Curve Regulation' column, and a per-column exceedance count at practical thresholds (1e-4 for most columns, 1e-6 for Curve AUC/Curve R2) to distinguish a systemic problem from isolated outliers. Comparison scripts: notebooks/viability_ctrp_40/compare_base.py and compare_base_detail.py; full machine-readable results: notebooks/viability_ctrp_40/base_comparison_report.json and base_comparison_detail.txt.",
    "row_count_reference": 1211,
    "row_count_produced": 1211,
    "row_count_match": True,
    "columns_identical": True,
    "identifier_column": "Name",
    "identifiers_identical_and_in_same_order": True,
    "identifier_set_equal": True,
    "curve_regulation_categorical": {
      "n_total": 1211,
      "n_exact_match": 1211,
      "n_mismatch": 0,
      "mismatch_breakdown": {}
    },
    "numeric_columns_max_abs_and_rel_diff": {
      "pEC50":                   {"max_abs_diff": 0.20623832542831266,  "max_rel_diff": 0.07919516214681996,   "median_abs_diff": 8.88e-16, "n_rows_exceeding_1e-4": 1},
      "Curve Slope":             {"max_abs_diff": 0.0019632956011959024,"max_rel_diff": 0.0135890431682534,    "median_abs_diff": 1.78e-15, "n_rows_exceeding_1e-4": 3},
      "Curve Front":             {"max_abs_diff": 0.0001646188416708494,"max_rel_diff": 0.0001645574261515574, "median_abs_diff": 2.22e-16, "n_rows_exceeding_1e-4": 1},
      "Curve Back":              {"max_abs_diff": 0.005077141971285615, "max_rel_diff": 0.00393467523592281,   "median_abs_diff": 1.11e-16, "n_rows_exceeding_1e-4": 1},
      "Curve Fold Change":       {"max_abs_diff": 0.0005511887049629849,"max_rel_diff": 0.0030849363783188133, "median_abs_diff": 1.90e-15, "n_rows_exceeding_1e-4": 1},
      "Curve F_Value":           {"max_abs_diff": 0.0003831924002430931,"max_rel_diff": 0.00017699241550030748,"median_abs_diff": 2.75e-14, "n_rows_exceeding_1e-4": 1},
      "Curve P_Value":           {"max_abs_diff": 5.8894873908699186e-05,"max_rel_diff": 0.00038914661856011935,"median_abs_diff": 4.02e-20, "n_rows_exceeding_1e-4": 0},
      "Curve Relevance Score":   {"max_abs_diff": 0.0003494996824862026,"max_rel_diff": 0.010114907687178057,  "median_abs_diff": 6.11e-16, "n_rows_exceeding_1e-4": 1},
      "Curve AUC":               {"max_abs_diff": 1.549881203177783e-05,"max_rel_diff": 1.3896756450628865e-05,"median_abs_diff": 1.11e-16, "n_rows_exceeding_1e-6": 2},
      "Curve R2":                {"max_abs_diff": 4.069607559831212e-05,"max_rel_diff": 0.0001178576240238707, "median_abs_diff": 1.11e-16, "n_rows_exceeding_1e-6": 2}
    },
    "nan_mismatches_per_numeric_column": "0 for all 10 columns on all 1211 rows",
    "outlier_rows_detail": {
      "count": 5,
      "names": ["GSU_NPC-26", "769-P_CIL70", "LS 180_CIL70", "L3.3_NPC-26", "HARA_CIL70"],
      "shared_characteristics": "All 5 rows have Signal Quality=0.0, low R2 (0.08-0.45), high Curve P_Value (>0.05, mostly >0.4), and Curve Regulation of 'not' (4 rows) or NaN/below-quality-filter (GSU_NPC-26) in BOTH the shipped reference and this run -- i.e. every affected curve is a weak/statistically-insignificant fit in both files, and none crosses the up/down significance threshold differently.",
      "worst_case": "GSU_NPC-26: pEC50 ref=2.6041783341003497 vs new=2.397940008672037 (abs diff 0.206, rel diff 7.9%); Curve Slope ref=0.0453 vs new=0.0459 (i.e. an almost perfectly flat curve). Curve Regulation is NaN in both (filtered out by the quality_min/Signal Quality gate before ever reaching the up/down decision), so this large pEC50 shift has zero effect on the reported scientific call for this row.",
      "root_cause_assessment": "Not attributable to text round-trip formatting (no float_format is applied on the to_csv call in curve_curator/__main__.py line 129, so full double precision is written both times) and not attributable to the fitting algorithm being non-deterministic (grep of quantification.py/models.py/toolbox.py confirms no RNG in the fitting path, matching the coordinator's independent pre-run verification). The remaining explanation is that these 5 curves have a near-flat dose-response (Curve Slope close to 0, or pinned at the parameter bound of 10.0) where the nonlinear least-squares (scipy) optimization landscape for pEC50 is nearly flat/poorly identifiable; the iterative optimizer's exact convergence point on such a flat valley is sensitive to floating-point operation ordering, and this environment's numpy/scipy/BLAS versions (numpy 2.4.6, scipy 1.17.1) almost certainly differ from whichever versions generated the shipped reference file (which predates this container). This is reported plainly as an observed, unresolved numerical discrepancy on 5 of 1211 rows (0.4%), all of them already-insignificant curves; no tolerance was widened to hide it and no code was edited to force a match."
    },
    "tolerance_statement": "1206-1210 of 1211 rows (99.6-99.9% depending on column) agree to <1e-4 absolute/relative difference, with a median absolute difference at the ~1e-15 floating-point noise floor across all 10 numeric columns. A minority of 5 rows (0.4%), all weak/insignificant curves with near-flat slopes, show larger deviations up to 0.206 absolute (7.9% relative) in pEC50 -- see outlier_rows_detail above. The categorical Curve Regulation call is 100% identical on all 1211 rows including the 5 outlier rows, so no curve was classified differently as a result of these numeric differences.",
    "verdict": "MOSTLY MATCH WITH A DOCUMENTED, EXPLAINED MINORITY DISAGREEMENT: exact row/column/identifier structure and 100% exact categorical classification agreement; the deterministic fitting core reproduces the shipped reference to floating-point precision on >99.5% of rows, with 5 weak-curve rows (0.4%) showing real, plausibly version-driven numerical divergence in continuous parameter estimates that does not change any scientific classification. This is reported as-is rather than tuned away."
  },

  "fdr_structural_checks": {
    "method": "Because --fdr's decoy simulation is unseeded (see randomness_and_seed_provenance) and no shipped example anywhere in the repository was ever run with --fdr, no ground-truth numeric comparison is possible or attempted. Both fdr_run1 and fdr_run2 were instead checked structurally and statistically, and compared to each other to characterize (not eliminate) their expected variability.",
    "exit_status_both_runs_zero": True,
    "additional_artifacts_produced": {
      "decoys_file": "decoys_40.0.txt -- appears only with --fdr, as declared in the toml's [Paths].decoys_file and defaulted in toml_parser.py to './decoys.txt' when unset. Confirmed 58 columns actually present in the produced file (read from the file itself, not from documentation): Name, Raw 0-16, Ratio 0-16, Signal Quality, pEC50, Curve Slope, Curve Front, Curve Back, Curve Fold Change, Curve AUC, Curve RMSE, Curve R2, pEC50 Error, Curve Slope Error, Curve Front Error, Curve Back Error, Null Model, Null RMSE, Curve F_Value, Curve P_Value, Curve Log P_Value, Curve F_Value SAM Corrected, Curve Relevance Score, Curve Regulation, Decoy, Curve q_Value. (One fewer column than the target curves_40.0.txt because decoys lack an 'N duplicates' aggregation column.)",
      "fdr_file": "fdr_40.0.txt -- appears only with --fdr, as declared in [Paths].fdr_file / defaulted to './fdr.txt'. Actual content (read from the file) is exactly two lines: 'Global FDR: <value>' and 'Filtered FDR: <value>', produced by thresholding.estimate_fdr.",
      "target_curves_file_gains_columns": "The target curves_40.0.txt itself gains 2 columns under --fdr versus the base run (57 -> 59 columns, confirmed by reading both headers): 'Decoy' (bool, all False for target rows) and 'Curve q_Value' (the target-decoy q-value from thresholding.estimate_qvalues, sort keys 'Curve Relevance Score' and 'Curve F_Value SAM Corrected')."
    },
    "decoy_count_vs_decoy_ratio": {
      "configured_decoy_ratio": 1.0,
      "configured_decoy_ratio_source": "not set in parameters_40.0.toml's [F Statistic] section; code default of 1.0 applies per curve_curator/toml_parser.py set_default_values, f_statistic_params['decoy_ratio'] = float(...get('decoy_ratio', 1.0))",
      "n_target_curves_after_filtering": 1211,
      "n_decoys_fdr_run1": 1211,
      "n_decoys_fdr_run2": 1211,
      "consistency_check": "n_decoys == round(decoy_ratio * n_empirical_noise_curves). With decoy_ratio=1.0 and 1211 target curves surviving the missing-value/control filters, n_decoys=1211 in both runs is exactly consistent with the configured ratio."
    },
    "fdr_value_bounds_check": {
      "fdr_run1_global_fdr": 0.003704,
      "fdr_run1_filtered_fdr": 0.003704,
      "fdr_run2_global_fdr": 0.001852,
      "fdr_run2_filtered_fdr": 0.001852,
      "both_in_0_1_range": True,
      "note": "Global and Filtered FDR are identical to each other within each run because, for this alpha=0.05/fc_lim=0.3 SAM threshold, the set of curves passing the user significance threshold (used for 'Filtered') and the overall relevance-score-ranked comparison (used for 'Global') happened to yield the same estimated ratio at this alpha=0.05 log-threshold in both runs; this is a property of thresholding.estimate_fdr's get_fdr() computation on this particular dataset/threshold combination, not a code defect (formula independently re-read in thresholding.py lines 491-519)."
    },
    "cross_run_variability_qvalues_and_decoys": {
      "target_curve_fitting_is_identical_across_runs": "pEC50, Curve Relevance Score, and Curve F_Value SAM Corrected in curves_40.0.txt are BIT-IDENTICAL (max abs diff = 0.0) between fdr_run1 and fdr_run2, confirming the curve-fitting step itself is unaffected by --fdr's randomness and remains deterministic.",
      "decoys_40.0.txt_differs_between_runs": "sha256 fe5f96d8...b23 (run1) vs 41b52cba...eba (run2); a raw line-diff shows nearly every one of the 1211 decoy rows differs (2424 differing lines out of 1212 including header), confirming the decoy simulation actually re-drew random values each run rather than being cached or coincidentally deterministic.",
      "curve_q_value_differs_between_runs": "max |q_value_run1 - q_value_run2| = 0.0463 across the 1211 target curves (elementwise equality: False for essentially all rows), because q-values are computed from the target-vs-(different)-decoy comparison.",
      "fdr_file_differs_between_runs": "Global/Filtered FDR: 0.003704 (run1) vs 0.001852 (run2) -- a 2x difference, plausible at this scale because only a handful of decoys cross the significance threshold in either run (Global FDR ~= few decoys / few thousand candidate comparisons), so small integer differences in the decoy draw produce large relative swings in the estimated ratio.",
      "interpretation": "This variability is the expected, correct behaviour of an unseeded target-decoy simulation, exactly as flagged in the assignment and in the coordinator's pre-verified defect record (data_simulator.py's unseeded scipy.stats....rvs() and np.random.choice calls, no seed exposed anywhere in the CLI). It is documented here as evidence of that non-determinism, not reported as a bug, and not silenced by re-running until two values happened to agree."
    },
    "verdict": "STRUCTURALLY VALID, NOT VALUE-REPRODUCIBLE (by design): both --fdr runs exited 0, produced all four expected additional/modified artifacts (decoys_40.0.txt, fdr_40.0.txt, plus Decoy/Curve q_Value columns on curves_40.0.txt) with the actual columns and decoy count matching the configured decoy_ratio=1.0, and both estimated FDR values lie in [0,1]. No exact FDR or decoy value is or should be asserted as ground truth."
  },

  "dashboard_html_check": {
    "base_run": {
      "reference_file": "repo/curve_curator/example_datasets/viability_CTRP_40/dashboard_40.0.html (sha256 744431567b15872b2d64bf1f8b7130149c8f6d01c6d468c1603b7d1f7132c1b4, 663521 bytes)",
      "produced_file": "notebooks/viability_ctrp_40/work/base/dashboard_40.0.html (sha256 b7c7da7efff86d34b68c9cdcaa21fc17982f08eae667ca82b4c4333846e4e87c, 663521 bytes)",
      "raw_bytes_identical": False,
      "explanation": "Byte identity was not expected. Both files are exactly 663521 bytes. A line-diff shows the differences are: (1) the embedded Bokeh CDN script tags -- shipped file references bokeh(-gl/-widgets/-tables)-3.7.0.min.js, produced file references -3.7.3.min.js (this environment's resolved bokeh version, within the pyproject-pinned range); (2) randomly generated per-render UUID strings for the top-level HTML div id and the embedded application/json script id (e.g. cd68f4a5-... vs e3799156-...); (3) Bokeh internal model-id integers offset by a small constant (e.g. p1422 vs p1424) because the newer Bokeh version instantiates a couple of extra internal objects before building the same visualization tree. draw_default_values() in dashboard.py uses a fixed np.random.seed(8) for its one illustrative jitter element, so that piece is deterministic; the diverging UUIDs/model-ids come from Bokeh's own document-serialization machinery, not from CurveCurator's code.",
      "conclusion": "No scientific/numeric mismatch attributable to dashboard.html; the observed byte differences are fully explained by the bokeh patch-version bump (3.7.0 shipped -> 3.7.3 here) and Bokeh's own per-render random identifiers, consistent with the base run's curves_40.0.txt already having been checked numerically above."
    },
    "fdr_run1_vs_fdr_run2": {
      "raw_bytes_identical": False,
      "explanation": "Expected to differ beyond just UUIDs/model-ids in this case, because the two --fdr runs' underlying data genuinely differs (different decoy draws produce different Curve q_Value values feeding the dashboard's plotted/filterable data), on top of the same Bokeh UUID/model-id non-determinism seen in the base-run comparison above.",
      "sha256_run1": "7e0ae94e3735fbdae280d99eaceeb94b25f8877b106c129a5defcf1abf47f3cb",
      "sha256_run2": "180cb48b1edebd4fb8d5f4c3b65d186972aede13ec3be60e03173b71870ee2ad"
    }
  },

  "figures": {
    "applicable": True,
    "note": "CurveCurator's only visual artifact is the interactive Bokeh dashboard_40.0.html (no static PNG/image figures are produced by this pipeline). A dashboard was produced and hashed for all three runs (base, fdr_run1, fdr_run2) and compared as described in dashboard_html_check above; no static figures were invented to meet an arbitrary count."
  },

  "input_output_inventory": {
    "inputs": [
      {"path": "notebooks/viability_ctrp_40/work/base/parameters_40.0.toml", "sha256": "e127f39da561d01dd5cf1cba68f53ca5ccaf0e4090a570ec753bd956a94849af", "copied_unmodified_from": "repo/curve_curator/example_datasets/viability_CTRP_40/parameters_40.0.toml"},
      {"path": "notebooks/viability_ctrp_40/work/base/dose_responses_40.0.tsv", "sha256": "03c4b69a046a78552507fba55cf635284781247687e21b0e67ba29029cac9a6b", "copied_unmodified_from": "repo/curve_curator/example_datasets/viability_CTRP_40/dose_responses_40.0.tsv"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/parameters_40.0.toml", "sha256": "e127f39da561d01dd5cf1cba68f53ca5ccaf0e4090a570ec753bd956a94849af"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/dose_responses_40.0.tsv", "sha256": "03c4b69a046a78552507fba55cf635284781247687e21b0e67ba29029cac9a6b"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/parameters_40.0.toml", "sha256": "e127f39da561d01dd5cf1cba68f53ca5ccaf0e4090a570ec753bd956a94849af"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/dose_responses_40.0.tsv", "sha256": "03c4b69a046a78552507fba55cf635284781247687e21b0e67ba29029cac9a6b"}
    ],
    "outputs": [
      {"path": "notebooks/viability_ctrp_40/work/base/curves_40.0.txt", "sha256": "6d16700e0ccebdf43f9a218b3e23b4e19315ea95191e31cadac4e444c1592b0b"},
      {"path": "notebooks/viability_ctrp_40/work/base/dashboard_40.0.html", "sha256": "b7c7da7efff86d34b68c9cdcaa21fc17982f08eae667ca82b4c4333846e4e87c"},
      {"path": "notebooks/viability_ctrp_40/work/base/curveCurator.log", "sha256": "2763c267d42f77120d5b7399214cdaed3b41320b59c4afb7e3783840f623cfde"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/curves_40.0.txt", "sha256": "8a55a006619b60988afa07abb44f6fd2286ba756aa96c9676f8cb24454d0573f"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/decoys_40.0.txt", "sha256": "fe5f96d8b62132de7a5aeee514147843dec830d4b9cf56139ee0ddb009df9123"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/fdr_40.0.txt", "sha256": "7783cc2ee6819486aeacef34ccdd2e8ded54f7451662ede9fba5b4eb2bcebecb"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/dashboard_40.0.html", "sha256": "7e0ae94e3735fbdae280d99eaceeb94b25f8877b106c129a5defcf1abf47f3cb"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run1/curveCurator.log", "sha256": "a0e22e2bca5115ef2f6ebafa6b43d786bc885d6fcc1e628f869672c3a99c6a50"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/curves_40.0.txt", "sha256": "6579371309597722ba5614d14d73c351ad10e97b954a0fded5e362cddace794e"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/decoys_40.0.txt", "sha256": "41b52cba1a2e5fc191a556e9b3f26a0850421f01b7c5f4fc3708d3cef47eba63"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/fdr_40.0.txt", "sha256": "5ca8a66162809db2d79e6103e23f01d5158cac714d390d15be52d093e83031cd"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/dashboard_40.0.html", "sha256": "180cb48b1edebd4fb8d5f4c3b65d186972aede13ec3be60e03173b71870ee2ad"},
      {"path": "notebooks/viability_ctrp_40/work/fdr_run2/curveCurator.log", "sha256": "92ad900b9f0a843b70dc1cb6343bd036b47e0627b6a871c12941283fe7165edc"}
    ],
    "evidence_and_scripts": [
      "notebooks/viability_ctrp_40/compare_base.py (comparison driver: pandas/numpy only, does not reimplement any curve-fitting logic)",
      "notebooks/viability_ctrp_40/compare_base_detail.py (per-column exceedance-count and outlier-row detail driver)",
      "notebooks/viability_ctrp_40/base_comparison_report.json (machine-readable summary comparison output)",
      "notebooks/viability_ctrp_40/base_comparison_detail.txt (per-column exceedance counts and outlier-row raw values)",
      "notebooks/viability_ctrp_40/before_hashes.txt / after_hashes.txt / final_hashes.txt (repo/ untouched proof, three snapshots)"
    ]
  },

  "limitations": [
    "5 of 1211 rows (0.4%) in the base run's curves_40.0.txt disagree with the shipped reference beyond a 1e-4 tolerance in one or more continuous parameters (worst case pEC50 abs diff 0.206 on GSU_NPC-26); all 5 are weak/insignificant curves (Curve Regulation 'not' or NaN in both files) with near-flat slopes, most plausibly caused by a nonlinear-optimizer convergence-path difference on an ill-conditioned fit between this environment's numpy 2.4.6/scipy 1.17.1 and whichever versions generated the shipped reference. This was investigated and is reported as-is rather than tuned away; see base_run_reference_comparison.outlier_rows_detail.",
    "--fdr has no shipped ground truth anywhere in the repository (independently re-confirmed: zero fdr/decoy mentions in all three shipped example logs) and its decoy simulation is unseeded with no seed exposed by the CLI/toml/UI, so its exact numeric output (decoys_40.0.txt, fdr_40.0.txt, Curve q_Value) is fundamentally irreproducible by value. This was verified empirically (not just asserted) by running --fdr twice and observing genuinely different decoys/q-values/FDR while the deterministic target-curve fit stayed bit-identical across both runs. No exact FDR or decoy value is asserted as expected anywhere in this report.",
    "This container has 4 logical CPUs and up to two sibling executor sessions (kinobeads_dasatinib, decryptm_dasatinib) ran CurveCurator concurrently during parts of this window, so the wall-clock runtimes reported here (948.89s base, 1132.87s fdr_run1, 591.22s fdr_run2) are inflated by CPU contention relative to a dedicated machine and vary between the two --fdr runs for that reason. The shipped toml's available_cores=5 was used unmodified for all three runs (no run failed for lack of cores, so no edit was made per the assignment's instruction).",
    "dashboard_40.0.html cannot be compared byte-for-byte to the shipped reference or between the two --fdr runs, because Bokeh embeds random per-render UUIDs/model-ids and this environment resolved bokeh 3.7.3 vs the shipped file's 3.7.0 (both within the pyproject-pinned range). This was diagnosed by line-diffing the HTML and identifying exactly which substrings differ (CDN version strings, UUIDs, model-id integers), not asserted without evidence.",
    "The -r/--random (destructive H0 simulation, overwrites input_file) and --batch flags were not exercised, per the coordinator's selection review excluding them from the tool inventory for this route."
  ],

  "attempts": {
    "total_execution_attempts": 3,
    "attempts_detail": [
      {"attempt": 1, "run": "base", "outcome": "success on first attempt, exit 0"},
      {"attempt": 2, "run": "fdr_run1", "outcome": "success on first attempt, exit 0"},
      {"attempt": 3, "run": "fdr_run2", "outcome": "success on first attempt, exit 0"}
    ],
    "note": "No failures or retries were needed, within the 5-attempt limit. A `CurveCurator -h` invocation was used only during initial reconnaissance to confirm supported flags and the version string printed on error; it is not counted as a scientific execution attempt and no scientific conclusions were drawn from it."
  },

  "hard_constraints_observed": [
    "Only notebooks/viability_ctrp_40/** and reports/executed_notebook_viability_ctrp_40.json were written by this executor.",
    "repo/ was never used as a working directory and never written to; verified unmodified by sha256 before, during, and after all three runs.",
    "No package was installed, upgraded, or removed; the pre-provisioned .venv was used as-is.",
    "No git commands that change branches, commit, or push were run (only read-only git log/status/describe for provenance).",
    "reports/executed_notebooks.json (coordinator-owned index) was not written."
  ]
}

with open("/home/user/test100/paper2agent-curvecurator/reports/executed_notebook_viability_ctrp_40.json", "w") as f:
    json.dump(report, f, indent=2)

print("wrote report, top-level keys:", list(report.keys()))
