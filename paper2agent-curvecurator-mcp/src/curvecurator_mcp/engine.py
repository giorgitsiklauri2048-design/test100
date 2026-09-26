"""Thin binding layer over the authors' ``curve_curator`` package.

Nothing in this module reimplements the statistics of

    Bayer FP, Gander M, Kuster B, The M. CurveCurator: a recalibrated F-statistic
    to assess, classify, and explore significance of dose-response curves.
    Nat Commun 14:7902 (2023). doi:10.1038/s41467-023-43696-z

Every fit, F-value, p-value, s0, relevance score, decoy and FDR returned here is
computed by calling ``curve_curator`` itself. This module only marshals inputs
into the conventions the pipeline uses (log10-molar doses, a control point at
x = -inf with ratio 1.0) and marshals outputs back into JSON-safe dictionaries.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.stats import f as f_distribution

from curve_curator import data_simulator, models, thresholding

# Pipeline defaults, read from the authors' TOML parser rather than hard-coded
# guesses. See data/paper_reference.json -> pipeline_defaults.
DEFAULT_ALPHA = 0.05
DEFAULT_FC_LIM = 0.45
DEFAULT_LOC = 0.12
DEFAULT_SCALE = 1.0
DEFAULT_NOT_RMSE_LIMIT = 0.1

#: Multiplicative factors from a dose unit to molar.
DOSE_UNIT_SCALES = {
    "M": 1e0,
    "mM": 1e-3,
    "uM": 1e-6,
    "µM": 1e-6,
    "nM": 1e-9,
    "pM": 1e-12,
    "fM": 1e-15,
}


class EngineError(ValueError):
    """Raised for inputs the CurveCurator pipeline cannot evaluate."""


def _finite(value: Any) -> Any:
    """Convert numpy scalars to JSON-safe Python values, NaN/inf to None."""
    if value is None:
        return None
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def resolve_dose_scale(dose_unit: str) -> float:
    try:
        return DOSE_UNIT_SCALES[dose_unit]
    except KeyError:
        raise EngineError(
            f"Unknown dose_unit {dose_unit!r}. Supported: {sorted(DOSE_UNIT_SCALES)}."
        ) from None


def to_log10_molar(doses: Sequence[float], dose_unit: str) -> np.ndarray:
    """Convert doses in ``dose_unit`` to the log10-molar x-values the model expects."""
    scale = resolve_dose_scale(dose_unit)
    doses = np.asarray(doses, dtype=float)
    if doses.size == 0:
        raise EngineError("At least one dose is required.")
    if np.any(doses <= 0):
        raise EngineError(
            "All doses must be > 0. The control is added automatically at x = -inf "
            "with ratio 1.0, so it must not be passed as a dose of 0."
        )
    return np.log10(doses * scale)


def _prepare(doses: Sequence[float], responses: Sequence[float], dose_unit: str):
    """Mirror ``curve_curator.quantification.fit_model`` input preparation.

    The pipeline masks non-finite responses, then prepends the control point
    (x = -inf, ratio = 1.0). ``n`` therefore counts the finite dose points plus
    the control, which is what the paper means by "n = 17 data points (doses and
    one control)".
    """
    x_data = to_log10_molar(doses, dose_unit)
    y_data = np.asarray(responses, dtype=float)
    if x_data.size != y_data.size:
        raise EngineError(
            f"doses and responses must be the same length, got {x_data.size} and {y_data.size}."
        )

    finite = np.isfinite(y_data)
    n_missing = int((~finite).sum())
    x_data, y_data = x_data[finite], y_data[finite]

    order = np.argsort(x_data)
    x_data, y_data = x_data[order], y_data[order]

    x = np.append(-np.inf, x_data)
    y = np.append(1.0, y_data)
    n = int(x.size)
    if n <= 4:
        raise EngineError(
            f"The recalibrated F-statistic requires n > 4 including the control; got n = {n}. "
            "CurveCurator returns NaN below this."
        )
    return x, y, x_data, n, n_missing


def effective_dofs(n: int, optimized: bool = True) -> tuple[float, float]:
    """Effective degrees of freedom for n data points, from ``LogisticModel.get_dofs``."""
    try:
        dfn, dfd = models.LogisticModel().get_dofs(n, optimized=optimized)
    except ValueError as exc:
        raise EngineError(str(exc)) from None
    return float(dfn), float(dfd)


def fit_curve(
    doses: Sequence[float],
    responses: Sequence[float],
    dose_unit: str = "nM",
    fit_type: str = "OLS",
    control_fold_change: bool = False,
    fixed_slope: float | None = None,
    fixed_front: float | None = None,
    fixed_back: float | None = None,
    optimized_dofs: bool = True,
    loc: float = DEFAULT_LOC,
    scale: float = DEFAULT_SCALE,
) -> dict[str, Any]:
    """Fit the mean model and the log-logistic model, then evaluate the F-statistic.

    Returns curve parameters, the curve fold change, the recalibrated F-value and
    its p-value, plus the null-model quantities the ``not``-classification uses.
    """
    fit_type = fit_type.upper()
    if fit_type not in {"OLS", "MLE"}:
        raise EngineError(f"fit_type must be 'OLS' or 'MLE', got {fit_type!r}.")

    x, y, x_data, n, n_missing = _prepare(doses, responses, dose_unit)

    m0 = models.MeanModel()
    m0.set_initial_guess(intercept=float(np.mean(y[1:])), noise=float(np.std(y)))
    m1 = models.LogisticModel(slope=fixed_slope, front=fixed_front, back=fixed_back)

    if fit_type == "OLS":
        m0.fit_ols(x, y)
        m1.efficiently_fit_ols(x, y, noise=m0.noise)
    else:
        m0.fit_mle(x, y)
        m1.efficiently_fit_mle(x, y, noise=m0.noise)

    params = m1.get_all_parameters()
    f_value, p_value = m1.evaluate(x, y, recalibrated=optimized_dofs)
    # ``evaluate`` hard-codes the published loc; recompute the p-value when the
    # caller overrides loc/scale so the two stay consistent.
    dfn, dfd = effective_dofs(n, optimized=optimized_dofs)
    if optimized_dofs and (loc != DEFAULT_LOC or scale != DEFAULT_SCALE):
        p_value = float(f_distribution.sf(f_value, dfn=dfn, dfd=dfd, loc=loc, scale=scale))

    fold_change = m1.calculate_fold_change(x[1:], to_control=control_fold_change)
    pec50 = params.get("pec50")
    ec50_molar = 10.0 ** (-pec50) if pec50 is not None and math.isfinite(pec50) else None

    try:
        m1.calculate_parameter_error(x, y)
        param_errors = {k: _finite(v) for k, v in m1.fitted_params_error.items()}
    except Exception:  # pragma: no cover - error estimation is best-effort upstream
        param_errors = {}

    dose_min, dose_max = float(np.min(x_data)), float(np.max(x_data))
    front_plateau_covered = bool(pec50 is not None and math.isfinite(pec50) and -pec50 >= dose_min)

    return {
        "n_data_points": n,
        "n_dose_points": int(x_data.size),
        "n_missing_responses_dropped": n_missing,
        "fit_type": fit_type,
        "curve_parameters": {
            "pEC50": _finite(pec50),
            "EC50_molar": _finite(ec50_molar),
            "slope": _finite(params.get("slope")),
            "front": _finite(params.get("front")),
            "back": _finite(params.get("back")),
        },
        "curve_parameter_standard_errors": param_errors,
        "fixed_parameters": {
            k: v
            for k, v in {"slope": fixed_slope, "front": fixed_front, "back": fixed_back}.items()
            if v is not None
        },
        "curve_fold_change_log2": _finite(fold_change),
        "curve_fold_change_definition": (
            "model at highest dose relative to control"
            if control_fold_change
            else "model at highest dose relative to model at lowest dose"
        ),
        "goodness_of_fit": {
            "r_squared": _finite(m1.calculate_r2(x, y)),
            "rmse": _finite(m1.calculate_rmse(x, y)),
            "auc": _finite(m1.calculate_auc(x)),
        },
        "null_model": {
            "intercept": _finite(m0.get_all_parameters().get("intercept")),
            "rmse": _finite(m0.calculate_rmse(x, y)),
        },
        "statistics": {
            "recalibrated_f_value": _finite(f_value),
            "p_value": _finite(p_value),
            "dfn": dfn,
            "dfd": dfd,
            "loc": loc,
            "scale": scale,
            "optimized_dofs": optimized_dofs,
        },
        "dose_range_log10_molar": [dose_min, dose_max],
        "potency_within_assayed_range": front_plateau_covered,
        "caveats": _fit_caveats(p_value, front_plateau_covered, n_missing, control_fold_change),
    }


def _fit_caveats(
    p_value: float | None,
    potency_in_range: bool,
    n_missing: int,
    control_fold_change: bool,
) -> list[str]:
    caveats: list[str] = []
    caveats.append(
        "Only curves that pass the relevance-score boundary have interpretable curve "
        "parameters. Do not report a pEC50 from a non-significant curve."
    )
    if not potency_in_range:
        caveats.append(
            "The fitted EC50 lies below the lowest assayed dose, so the lowest dose is not "
            "on the front plateau. The curve fold change is compressed, which the paper "
            "names as a source of false negatives among the most potent curves. Consider "
            "control_fold_change=true or a wider dose range."
        )
    if n_missing:
        caveats.append(
            f"{n_missing} non-finite response(s) were dropped, lowering n and therefore "
            "changing the effective degrees of freedom and s0 for this curve."
        )
    if control_fold_change:
        caveats.append(
            "Control-relative fold change raises the false-positive rate in unstable assays "
            "relative to the default lowest-to-highest-dose definition."
        )
    return caveats


def relevance_score(
    f_value: float,
    curve_fold_change: float,
    n_data_points: int,
    alpha: float = DEFAULT_ALPHA,
    fc_lim: float = DEFAULT_FC_LIM,
    optimized_dofs: bool = True,
    loc: float = DEFAULT_LOC,
    scale: float = DEFAULT_SCALE,
    two_sided: bool = False,
) -> dict[str, Any]:
    """Compute s0, the s0-adjusted F-value and the relevance score for one curve."""
    if not 0.0 < alpha <= 1.0:
        raise EngineError("alpha must be in (0, 1].")
    if fc_lim < 0.0:
        raise EngineError("fc_lim must be >= 0.")

    dfn, dfd = effective_dofs(n_data_points, optimized=optimized_dofs)
    s0 = float(
        thresholding.get_s0(fc_lim=fc_lim, alpha=alpha, dfn=dfn, dfd=dfd, two_sided=two_sided)
    )
    f_adj = float(thresholding.sam_correction(f_value, curve_fold_change, s0=s0))
    score = float(-np.log10(f_distribution.sf(f_adj, dfn=dfn, dfd=dfd, loc=loc, scale=scale)))
    cutoff = float(-np.log10(alpha))

    return {
        "s0": s0,
        "s0_adjusted_f_value": _finite(f_adj),
        "relevance_score": _finite(score),
        "relevance_score_cutoff": cutoff,
        "above_cutoff": bool(score >= cutoff),
        "dfn": dfn,
        "dfd": dfd,
        "alpha_asymptote": alpha,
        "fc_lim_asymptote": fc_lim,
        "is_valid_p_value": fc_lim == 0.0,
        "interpretation": (
            "With fc_lim = 0 the relevance score equals -log10(p-value)."
            if fc_lim == 0.0
            else "With fc_lim > 0 the relevance score is NOT a p-value. It orders curves by "
            "significance and effect size jointly; its absolute value has no biological or "
            "statistical meaning on its own."
        ),
    }


def classify_curve(
    fit: dict[str, Any],
    alpha: float = DEFAULT_ALPHA,
    fc_lim: float = DEFAULT_FC_LIM,
    not_rmse_limit: float = DEFAULT_NOT_RMSE_LIMIT,
    pec50_filter: tuple[float, float] | None = None,
    optimized_dofs: bool = True,
    loc: float = DEFAULT_LOC,
    scale: float = DEFAULT_SCALE,
    two_sided: bool = False,
) -> dict[str, Any]:
    """Apply the paper's four-way classification to an already-fitted curve.

    Reproduces ``thresholding.define_regulated_curves`` for a single curve,
    including the ``not`` heuristic and the deliberate ``unclear`` category.
    """
    fold_change = fit["curve_fold_change_log2"]
    f_value = fit["statistics"]["recalibrated_f_value"]
    n = fit["n_data_points"]
    pec50 = fit["curve_parameters"]["pEC50"]
    null_intercept = fit["null_model"]["intercept"]
    null_rmse = fit["null_model"]["rmse"]

    if fold_change is None or f_value is None:
        raise EngineError("The fit did not converge to finite values; cannot classify.")

    scored = relevance_score(
        f_value,
        fold_change,
        n,
        alpha=alpha,
        fc_lim=fc_lim,
        optimized_dofs=optimized_dofs,
        loc=loc,
        scale=scale,
        two_sided=two_sided,
    )

    significant = scored["above_cutoff"]
    effect_passes = abs(fold_change) >= fc_lim
    lo, hi = pec50_filter if pec50_filter is not None else (-math.inf, math.inf)
    pec50_passes = pec50 is not None and lo <= pec50 <= hi

    # ``not`` heuristic: null intercept within +/- fc_lim/2 on a log2 scale and a
    # low-variance null model.
    half = abs(fc_lim) / 2
    intercept_log2 = (
        math.log2(null_intercept) if null_intercept is not None and null_intercept > 0 else None
    )
    intercept_flat = intercept_log2 is not None and -half <= intercept_log2 <= half
    low_variance = null_rmse is not None and null_rmse <= not_rmse_limit
    clearly_not = intercept_flat and low_variance

    if significant and effect_passes and pec50_passes:
        regulation = "up" if fold_change > 0 else "down"
    elif not significant and clearly_not:
        regulation = "not"
    else:
        regulation = "unclear"

    reasons = {
        "relevance_score_above_cutoff": significant,
        "abs_fold_change_at_least_fc_lim": bool(effect_passes),
        "pEC50_within_filter": bool(pec50_passes),
        "null_intercept_within_half_fc_lim": bool(intercept_flat),
        "null_rmse_within_limit": bool(low_variance),
    }
    explanation = {
        "up": "Significant, effect size at or above the fold-change asymptote, positive direction.",
        "down": "Significant, effect size at or above the fold-change asymptote, negative direction.",
        "not": "Not significant, and the null model is both centred on the control and low-variance, "
        "so this is a confident non-responder suitable for a negative set.",
        "unclear": "Neither confidently regulated nor confidently flat. The paper introduces this "
        "category on purpose: absence of an effect cannot be proven, so high-variance curves are "
        "withheld from the negative set rather than being called non-responders.",
    }[regulation]

    return {
        "curve_regulation": regulation,
        "explanation": explanation,
        "criteria": reasons,
        "scoring": scored,
        "not_rmse_limit": not_rmse_limit,
        "pEC50_filter": [
            None if lo == -math.inf else lo,
            None if hi == math.inf else hi,
        ],
    }


def decision_boundary(
    fold_changes: Sequence[float],
    alpha: float = DEFAULT_ALPHA,
    fc_lim: float = DEFAULT_FC_LIM,
    n_data_points: int = 9,
    optimized_dofs: bool = True,
    two_sided: bool = False,
    loc: float = 0.0,
) -> dict[str, Any]:
    """Map fold changes onto the hyperbolic decision boundary.

    Returns ``-log10(p)`` thresholds, i.e. the y-axis of a volcano plot, not raw
    p-values. The authors' function is named ``map_fc_to_pvalue_cutoff`` and its
    docstring says "p-value cutoffs", but it returns ``-logsf * log10(e)``.

    ``loc`` defaults to 0.0 to match how the authors draw this boundary in their
    dashboard, which differs from the 0.12 location shift used for curve p-values.
    """
    dfn, dfd = effective_dofs(n_data_points, optimized=optimized_dofs)
    s0 = float(
        thresholding.get_s0(fc_lim=fc_lim, alpha=alpha, dfn=dfn, dfd=dfd, two_sided=two_sided)
    )
    if len(np.asarray(fold_changes, dtype=float)) == 0:
        raise EngineError("At least one fold change is required.")
    series = pd.Series(np.asarray(fold_changes, dtype=float))
    cutoffs = thresholding.map_fc_to_pvalue_cutoff(
        series, alpha=alpha, s0=s0, dfn=dfn, dfd=dfd, loc=loc, two_sided=two_sided
    )
    neg_lim, pos_lim = thresholding.get_fclim(
        s0, alpha, dfn=dfn, dfd=dfd, two_sided=two_sided
    )
    return {
        "s0": s0,
        "dfn": dfn,
        "dfd": dfd,
        "alpha_asymptote": alpha,
        "fc_lim_asymptote": fc_lim,
        "recovered_fc_asymptotes": [_finite(neg_lim), _finite(pos_lim)],
        "boundary": [
            {
                "curve_fold_change_log2": _finite(fc),
                "minus_log10_p_value_cutoff": _finite(cut),
                "reachable": bool(math.isfinite(cut)),
            }
            for fc, cut in zip(series.tolist(), np.asarray(cutoffs, dtype=float).tolist())
        ],
        "y_axis": "-log10(p-value); larger means a more stringent requirement",
        "note": (
            "In relevance-score space this hyperbola becomes a horizontal line at "
            f"-log10(alpha) = {-math.log10(alpha):.4f}. A fold change inside the asymptote "
            "band has an infinite cutoff, reported as a null with reachable=false: no amount "
            "of statistical significance can make such a curve relevant."
        ),
    }


def estimate_fdr(
    curves: Iterable[dict[str, Any]],
    doses: Sequence[float],
    dose_unit: str = "nM",
    alpha: float = DEFAULT_ALPHA,
    fc_lim: float = DEFAULT_FC_LIM,
    decoy_ratio: float = 1.0,
    not_rmse_limit: float = DEFAULT_NOT_RMSE_LIMIT,
    random_seed: int | None = None,
) -> dict[str, Any]:
    """Target-decoy FDR for a set of curves sharing one dose range.

    Decoys are drawn by ``curve_curator.data_simulator`` from the empirical noise
    of the supplied curves, then pushed through the identical fit-and-classify
    path, exactly as the ``--fdr`` route of the pipeline does.
    """
    curves = list(curves)
    if not curves:
        raise EngineError("At least one curve is required.")
    if decoy_ratio <= 0:
        raise EngineError("decoy_ratio must be > 0.")
    if random_seed is not None:
        np.random.seed(random_seed)

    target_rows = []
    noise: list[float] = []
    for curve in curves:
        responses = curve.get("responses")
        if responses is None:
            raise EngineError("Each curve needs a 'responses' list.")
        fit = fit_curve(doses, responses, dose_unit=dose_unit)
        cls = classify_curve(fit, alpha=alpha, fc_lim=fc_lim, not_rmse_limit=not_rmse_limit)
        target_rows.append(
            {
                "name": curve.get("name", f"curve_{len(target_rows)}"),
                "relevance_score": cls["scoring"]["relevance_score"],
                "curve_regulation": cls["curve_regulation"],
            }
        )
        noise.append(fit["goodness_of_fit"]["rmse"])

    n_decoys = max(1, int(round(len(curves) * decoy_ratio)))
    cols = [f"Ratio {i}" for i in range(len(doses))]
    decoy_frame = data_simulator.simulate_decoys(n_decoys, cols, np.asarray(noise, dtype=float))

    decoy_rows = []
    for idx, (_, row) in enumerate(decoy_frame[cols].iterrows()):
        fit = fit_curve(doses, row.tolist(), dose_unit=dose_unit)
        cls = classify_curve(fit, alpha=alpha, fc_lim=fc_lim, not_rmse_limit=not_rmse_limit)
        decoy_rows.append(
            {
                "name": f"decoy_{idx}",
                "relevance_score": cls["scoring"]["relevance_score"],
                "curve_regulation": cls["curve_regulation"],
            }
        )

    target_df = pd.DataFrame(target_rows)
    decoy_df = pd.DataFrame(decoy_rows)
    cutoff = float(-np.log10(alpha))
    ratio = len(target_df) / len(decoy_df)

    fdr_global = float(
        thresholding.get_fdr(target_df, decoy_df, "relevance_score", cutoff, ratio)
    )
    regulated = {"up", "down"}
    fdr_filtered = float(
        thresholding.get_fdr(
            target_df[target_df["curve_regulation"].isin(regulated)],
            decoy_df[decoy_df["curve_regulation"].isin(regulated)],
            "relevance_score",
            cutoff,
            ratio,
        )
    )

    counts = target_df["curve_regulation"].value_counts().to_dict()
    return {
        "n_targets": int(len(target_df)),
        "n_decoys": int(len(decoy_df)),
        "target_decoy_ratio": ratio,
        "alpha_asymptote": alpha,
        "fc_lim_asymptote": fc_lim,
        "relevance_score_cutoff": cutoff,
        "global_fdr": fdr_global,
        "filtered_fdr": fdr_filtered,
        "target_classification_counts": {k: int(v) for k, v in counts.items()},
        "regulated_curves": [
            r["name"] for r in target_rows if r["curve_regulation"] in regulated
        ],
        "caveats": [
            "Decoys are sampled from the empirical noise of the curves you supplied, so this "
            "FDR is only meaningful for a set large enough to describe that assay's variance. "
            "A handful of curves gives an unstable estimate.",
            "The authors recommend against moving the boundary to reach a target FDR. Fix the "
            "alpha and fold-change asymptotes on statistical and biological grounds, then "
            "accept the FDR that follows.",
            "Decoy simulation is stochastic. Pass random_seed for a reproducible estimate.",
        ],
    }
