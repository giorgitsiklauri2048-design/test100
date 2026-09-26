"""Build CurveCurator TOML parameter files, including the paper's three presets.

The output is a parameter file for the authors' CLI:

    CurveCurator <params.toml>            # fit, classify, dashboard
    CurveCurator <params.toml> --fdr      # additionally estimate the FDR

The console script is ``CurveCurator`` (declared in the repository's pyproject
as ``CurveCurator = "curve_curator.__main__:main"``); ``curve_curator`` is the
importable package name and is not an executable.
"""

from __future__ import annotations

from typing import Any, Sequence

from .engine import DOSE_UNIT_SCALES, EngineError

#: Asymptotes and preprocessing the paper used for each reprocessed dataset.
PRESETS: dict[str, dict[str, Any]] = {
    "kinobeads": {
        "description": "Kinobeads drug-target binding, as reprocessed in the paper.",
        "alpha": 0.1,
        "fc_lim": 0.5,
        "measurement_type": "LFQ",
        "data_type": "PROTEIN",
        "control_fold_change": False,
        "notes": [
            "278 drugs, 9 data points per curve, restricted to 255 direct Kinobeads binders.",
            "Binders with fewer than two data points per curve or missing in the control were excluded.",
            "Remaining missing values were imputed per experiment with the 0.5% intensity quantile.",
        ],
    },
    "ctrp": {
        "description": "CTRP cell viability screen, mode-of-action settings from the paper.",
        "alpha": 0.05,
        "fc_lim": 0.3,
        "measurement_type": "OTHER",
        "data_type": "OTHER",
        "control_fold_change": True,
        "notes": [
            "n = 17 data points (16 doses plus one control).",
            "control_fold_change = true because several drugs already regulate at the lowest dose.",
            "The screen used several dose ranges; the paper split the input per dose range and "
            "recombined the outputs before estimating one FDR over all curves.",
            "No imputation: missing values were sparse and missing at random.",
        ],
    },
    "decryptm": {
        "description": "decryptM drug-PTM phosphoproteome profiling, settings from the paper.",
        "alpha": 0.05,
        "fc_lim": 0.45,
        "measurement_type": "TMT",
        "data_type": "PEPTIDE",
        "control_fold_change": False,
        "notes": [
            "TMT channels median-centred, missing values imputed, peptides with more than 4 "
            "missing values excluded.",
            "fc_lim = 0.45 is 46% less stringent than the cutoff in the original decryptM "
            "publication; the authors attribute the gain to the hyperbolic decision boundary.",
        ],
    },
}


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def build_toml(
    doses: Sequence[float],
    dose_unit: str = "nM",
    experiments: Sequence[Any] | None = None,
    control_experiment: Sequence[Any] | None = None,
    alpha: float | None = None,
    fc_lim: float | None = None,
    preset: str | None = None,
    input_file: str = "./input.txt",
    output_prefix: str = ".",
    dataset_id: str = "ID1",
    description: str = "",
    condition: str = "",
    treatment_time: str = "",
    measurement_type: str | None = None,
    data_type: str | None = None,
    search_engine: str = "OTHER",
    control_fold_change: bool | None = None,
    normalization: bool = False,
    imputation: bool = False,
    max_missing: int | None = None,
    available_cores: int = 4,
    not_rmse_limit: float = 0.1,
    decoy_ratio: float = 1.0,
    fit_type: str = "OLS",
    fit_speed: str = "standard",
) -> dict[str, Any]:
    """Assemble a CurveCurator TOML parameter file.

    ``doses`` are the non-zero doses. A control dose of 0.0 is prepended, matching
    the pipeline's convention that the control is one of the ``n`` data points.
    """
    if preset is not None and preset not in PRESETS:
        raise EngineError(f"Unknown preset {preset!r}. Available: {sorted(PRESETS)}.")
    if dose_unit not in DOSE_UNIT_SCALES:
        raise EngineError(
            f"Unknown dose_unit {dose_unit!r}. Supported: {sorted(DOSE_UNIT_SCALES)}."
        )
    doses = [float(d) for d in doses]
    if any(d <= 0 for d in doses):
        raise EngineError("Pass only non-zero doses; the control dose 0.0 is added for you.")

    chosen = PRESETS.get(preset, {}) if preset else {}
    alpha = alpha if alpha is not None else chosen.get("alpha", 0.05)
    fc_lim = fc_lim if fc_lim is not None else chosen.get("fc_lim", 0.45)
    measurement_type = measurement_type or chosen.get("measurement_type", "OTHER")
    data_type = data_type or chosen.get("data_type", "OTHER")
    if control_fold_change is None:
        control_fold_change = chosen.get("control_fold_change", False)
    if not 0.0 < alpha <= 1.0:
        raise EngineError("alpha must be in (0, 1].")
    if fc_lim < 0.0:
        raise EngineError("fc_lim must be >= 0.")

    all_doses = [0.0] + doses
    n = len(all_doses)
    if experiments is None:
        experiments = list(range(1, n + 1))
    elif len(experiments) != n:
        raise EngineError(
            f"experiments must have one entry per dose including the control ({n}), "
            f"got {len(experiments)}."
        )
    if control_experiment is None:
        control_experiment = [experiments[0]]
    if max_missing is None:
        max_missing = len(doses)

    # dose_scale is written as a string in scientific notation, as the parser expects.
    dose_scale = f"{DOSE_UNIT_SCALES[dose_unit]:.0e}".replace("e-0", "e-")

    header = [
        "#",
        "# CurveCurator parameter file",
        "# Generated by paper2agent-curvecurator-mcp.",
        "#",
        "# Pipeline: Bayer FP, Gander M, Kuster B, The M. CurveCurator: a recalibrated",
        "# F-statistic to assess, classify, and explore significance of dose-response",
        "# curves. Nat Commun 14:7902 (2023). doi:10.1038/s41467-023-43696-z",
        "#",
        "# Run:  CurveCurator <this file>",
        "#       CurveCurator <this file> --fdr   # adds target-decoy FDR estimation",
        "#",
    ]
    if preset:
        header += ["# Preset: " + chosen["description"], "#"]
        header += [f"#   - {note}" for note in chosen["notes"]] + ["#"]

    lines = header + [
        "",
        "['Meta']",
        f"id = {_fmt(dataset_id)}",
        f"description = {_fmt(description)}",
        f"condition = {_fmt(condition)}",
        f"treatment_time = {_fmt(treatment_time)}",
        "",
        "['Experiment']",
        f"experiments = {_fmt(list(experiments))}",
        f"doses = {_fmt(all_doses)}",
        f"dose_scale = {_fmt(dose_scale)}",
        f"dose_unit = {_fmt('M')}",
        f"control_experiment = {_fmt(list(control_experiment))}",
        f"measurement_type = {_fmt(measurement_type)}",
        f"data_type = {_fmt(data_type)}",
        f"search_engine = {_fmt(search_engine)}",
        "",
        "['Paths']",
        f"input_file = {_fmt(input_file)}",
        f"curves_file = {_fmt(f'{output_prefix}/curves.txt')}",
        f"decoys_file = {_fmt(f'{output_prefix}/decoys.txt')}",
        f"fdr_file = {_fmt(f'{output_prefix}/fdr.txt')}",
        f"dashboard = {_fmt(f'{output_prefix}/dashboard.html')}",
        "",
        "['Processing']",
        f"available_cores = {available_cores}",
        f"max_missing = {max_missing}",
        f"imputation = {_fmt(imputation)}",
        f"normalization = {_fmt(normalization)}",
        "",
        "['Curve Fit']",
        f"type = {_fmt(fit_type)}",
        f"speed = {_fmt(fit_speed)}",
        f"control_fold_change = {_fmt(control_fold_change)}",
        "",
        "['F Statistic']",
        f"alpha = {alpha}    # statistical relevance asymptote",
        f"fc_lim = {fc_lim}    # log2 fold-change asymptote, i.e. biological relevance",
        "optimized_dofs = true",
        f"not_rmse_limit = {not_rmse_limit}",
        f"decoy_ratio = {decoy_ratio}",
        f"mtc_method = {_fmt('sam')}",
        "",
        "['Dashboard']",
        f"backend = {_fmt('webgl')}",
        "",
    ]

    return {
        "toml": "\n".join(lines),
        "n_data_points": n,
        "alpha_asymptote": alpha,
        "fc_lim_asymptote": fc_lim,
        "preset": preset,
        "preset_notes": chosen.get("notes", []),
        "run_commands": [
            "CurveCurator <this file>",
            "CurveCurator <this file> --fdr",
        ],
        "input_file_expectation": (
            "The input file must contain one row per curve with the response columns named "
            "per the search engine or, for generic data, 'Raw <experiment>' columns matching "
            "the experiments list. See the CurveCurator repository for the supported input "
            "formats (MaxQuant, DIA-NN, Proteome Discoverer, MSFragger, or a generic table)."
        ),
        "guidance": (
            "Set the alpha asymptote on statistical grounds (the paper suggests 5%) and the "
            "fold-change asymptote on assay grounds, then accept the FDR that results. The "
            "authors explicitly advise against tuning the asymptotes to hit a target FDR."
        ),
    }
