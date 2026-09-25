"""Concentration-response curve fitting reproducing the ToxCast pipeline (tcpl).

Franzosa et al. (2021), npj Syst Biol Appl 7:7, doi:10.1038/s41540-020-00166-2
fit each chemical-transcript pair with three models -- constant, Hill, and
gain-loss -- select the winner by AIC, and report ``modl_ga`` (the 50% activity
concentration, AC50) as potency and ``modl_tp`` (modelled top) as efficacy.

Model forms and the Student's t error model follow tcpl as described by
Filer et al., Bioinformatics 33:618-620 (2017), doi:10.1093/bioinformatics/btw680.

This module deliberately implements NO benchmark dose/concentration (BMD/BMC)
estimation. The source study does not perform BMD modelling and does not use a
benchmark response of 1.349 SD; that convention belongs to the BMDExpress / NTP
transcriptomic dose-response approach (Thomas et al., Toxicol Sci 98:240-248,
2007; NTP Research Report 5, 2018) and is a different pipeline.
"""

from __future__ import annotations

import math
from typing import Any, Literal, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.stats import t as student_t

# tcpl fits with a Student's t error distribution with 4 degrees of freedom.
T_DF = 4

# Hill coefficient bounds used by tcpl's constrained optimisation.
GW_BOUNDS = (0.3, 8.0)
LW_BOUNDS = (0.3, 18.0)

Direction = Literal["up", "down"]


class CurveFitError(ValueError):
    """Raised when the supplied concentration-response series cannot be fit."""


def _loglik(residuals: np.ndarray, log_sigma: float) -> float:
    """Student's t log-likelihood, as used for tcpl model comparison."""
    sigma = math.exp(log_sigma)
    if not math.isfinite(sigma) or sigma <= 0:
        return -np.inf
    return float(np.sum(student_t.logpdf(residuals / sigma, df=T_DF) - log_sigma))


def _hill(x: np.ndarray, tp: float, ga: float, gw: float) -> np.ndarray:
    """Monotonic Hill function on log10 concentration; ga is log10(AC50)."""
    return tp / (1.0 + np.power(10.0, (ga - x) * gw))


def _gnls(x: np.ndarray, tp: float, ga: float, gw: float, la: float, lw: float) -> np.ndarray:
    """Gain-loss: the non-monotonic product of two Hill functions with a shared top."""
    gain = 1.0 + np.power(10.0, (ga - x) * gw)
    loss = 1.0 + np.power(10.0, (x - la) * lw)
    return tp / (gain * loss)


def _aic(loglik: float, k: int) -> float:
    return 2.0 * k - 2.0 * loglik


def _fit_constant(y: np.ndarray) -> dict[str, Any]:
    """Constant model: response is flat at zero, one free parameter (the error term)."""

    def nll(p: np.ndarray) -> float:
        val = _loglik(y, float(p[0]))
        return -val if math.isfinite(val) else 1e12

    start = math.log(max(float(np.std(y)), 1e-3))
    res = minimize(nll, x0=[start], method="Nelder-Mead",
                   options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-8})
    ll = -float(res.fun)
    return {"model": "cnst", "params": {"er": float(res.x[0])}, "loglik": ll, "aic": _aic(ll, 1)}


def _fit_hill(x: np.ndarray, y: np.ndarray) -> dict[str, Any] | None:
    top_max = 1.2 * float(np.max(np.abs(y))) or 1.0
    bounds = [
        (1e-6, top_max),
        (float(np.min(x)) - 1.0, float(np.max(x)) + 0.5),
        GW_BOUNDS,
        (math.log(1e-4), math.log(1e3)),
    ]

    def nll(p: np.ndarray) -> float:
        tp, ga, gw, er = p
        if not (GW_BOUNDS[0] <= gw <= GW_BOUNDS[1]):
            return 1e12
        with np.errstate(over="ignore"):
            pred = _hill(x, tp, ga, gw)
        if not np.all(np.isfinite(pred)):
            return 1e12
        val = _loglik(y - pred, float(er))
        return -val if math.isfinite(val) else 1e12

    best = None
    for ga0 in (float(np.median(x)), float(np.min(x)), float(np.max(x)) - 0.5):
        for gw0 in (1.0, 3.0):
            x0 = [max(float(np.max(y)), 1e-3), ga0, gw0,
                  math.log(max(float(np.std(y)), 1e-3))]
            res = minimize(nll, x0=x0, method="L-BFGS-B", bounds=bounds)
            if res.success or math.isfinite(res.fun):
                if best is None or res.fun < best.fun:
                    best = res
    if best is None or not math.isfinite(best.fun) or best.fun >= 1e11:
        return None
    tp, ga, gw, er = (float(v) for v in best.x)
    ll = -float(best.fun)
    return {
        "model": "hill",
        "params": {"tp": tp, "ga": ga, "gw": gw, "er": er},
        "loglik": ll,
        "aic": _aic(ll, 4),
    }


def _fit_gnls(x: np.ndarray, y: np.ndarray) -> dict[str, Any] | None:
    top_max = 1.2 * float(np.max(np.abs(y))) or 1.0
    bounds = [
        (1e-6, top_max),
        (float(np.min(x)) - 1.0, float(np.max(x)) + 0.5),
        GW_BOUNDS,
        (float(np.min(x)), float(np.max(x)) + 2.0),
        LW_BOUNDS,
        (math.log(1e-4), math.log(1e3)),
    ]

    def nll(p: np.ndarray) -> float:
        tp, ga, gw, la, lw, er = p
        if la <= ga:
            return 1e12
        with np.errstate(over="ignore"):
            pred = _gnls(x, tp, ga, gw, la, lw)
        if not np.all(np.isfinite(pred)):
            return 1e12
        val = _loglik(y - pred, float(er))
        return -val if math.isfinite(val) else 1e12

    best = None
    span = float(np.max(x)) - float(np.min(x))
    for ga0 in (float(np.min(x)) + span * 0.25, float(np.median(x))):
        for la0 in (float(np.max(x)) - span * 0.15, float(np.max(x)) + 0.5):
            if la0 <= ga0:
                continue
            x0 = [max(float(np.max(y)), 1e-3), ga0, 1.5, la0, 3.0,
                  math.log(max(float(np.std(y)), 1e-3))]
            res = minimize(nll, x0=x0, method="L-BFGS-B", bounds=bounds)
            if math.isfinite(res.fun) and (best is None or res.fun < best.fun):
                best = res
    if best is None or not math.isfinite(best.fun) or best.fun >= 1e11:
        return None
    tp, ga, gw, la, lw, er = (float(v) for v in best.x)
    ll = -float(best.fun)
    return {
        "model": "gnls",
        "params": {"tp": tp, "ga": ga, "gw": gw, "la": la, "lw": lw, "er": er},
        "loglik": ll,
        "aic": _aic(ll, 6),
    }


def estimate_bmad(concentrations: Sequence[float], responses: Sequence[float]) -> float:
    """BMAD from a single curve: median absolute deviation of the two lowest concentrations.

    The study defines BMAD as "the median average deviation of all normalized
    response values at the lowest two tested concentrations" -- computed plate-wide
    across every well at those concentrations. A single eight-point curve supplies
    only two such values, so this is a degenerate, low-confidence approximation.
    Supply a plate-wide ``bmad`` to ``fit_concentration_response`` whenever one is
    available; the returned payload flags which of the two was used.
    """
    conc = np.asarray(concentrations, dtype=float)
    resp = np.asarray(responses, dtype=float)
    order = np.argsort(conc)
    lowest = np.unique(conc[order])[:2]
    vals = resp[np.isin(conc, lowest)]
    if vals.size == 0:
        return 0.0
    return float(np.median(np.abs(vals - np.median(vals))))


def fit_concentration_response(
    concentrations: Sequence[float],
    responses: Sequence[float],
    fold_change_cutoff: float = 1.2,
    bmad: float | None = None,
    bmad_multiplier: float = 3.0,
) -> dict[str, Any]:
    """Fit constant / Hill / gain-loss models and select the winner by AIC.

    Args:
        concentrations: Tested concentrations in micromolar (uM), strictly positive.
            The study used an eight-point concentration-response design.
        responses: Matched response values as log2 fold-change (the tcpl ``rval``,
            i.e. the delta-delta-Ct relative to the plate-wise median of the DMSO
            neutral control wells).
        fold_change_cutoff: Linear fold-change hit threshold; the study used 1.2.
        bmad: Plate-wide baseline median absolute deviation. If omitted, a
            low-confidence single-curve estimate is used and flagged as such.
        bmad_multiplier: 3.0 for the transcriptomic endpoints; the study used 10.0
            for the LDH cytotoxicity endpoint.

    Returns:
        Winning model, AC50 (``modl_ga``, uM), efficacy (``modl_tp``, log2 FC),
        both hit-criterion components, and the full per-model AIC table.
    """
    conc = np.asarray(concentrations, dtype=float)
    resp = np.asarray(responses, dtype=float)

    if conc.ndim != 1 or resp.ndim != 1:
        raise CurveFitError("concentrations and responses must each be a flat sequence")
    if conc.size != resp.size:
        raise CurveFitError(
            f"length mismatch: {conc.size} concentrations vs {resp.size} responses"
        )
    if conc.size < 4:
        raise CurveFitError(
            f"at least 4 concentration points are required to compare a 4-parameter "
            f"Hill model against the constant model; got {conc.size}"
        )
    if not np.all(np.isfinite(conc)) or not np.all(np.isfinite(resp)):
        raise CurveFitError("concentrations and responses must all be finite")
    if np.any(conc <= 0):
        raise CurveFitError("concentrations must be strictly positive (log10 scale is used)")
    if fold_change_cutoff <= 1.0:
        raise CurveFitError("fold_change_cutoff must be > 1.0 (it is a linear fold-change)")

    # Each transcript is fit separately in up- and downregulation mode; pick the
    # mode from the larger absolute excursion and fit on the folded response.
    peak = resp[int(np.argmax(np.abs(resp)))]
    direction: Direction = "down" if peak < 0 else "up"
    sign = -1.0 if direction == "down" else 1.0
    y = resp * sign
    x = np.log10(conc)

    fits = [_fit_constant(y)]
    for candidate in (_fit_hill(x, y), _fit_gnls(x, y)):
        if candidate is not None:
            fits.append(candidate)

    winner = min(fits, key=lambda f: f["aic"])

    used_bmad = estimate_bmad(concentrations, responses) if bmad is None else float(bmad)
    bmad_source = "single_curve_estimate" if bmad is None else "supplied_plate_wide"

    log2_cutoff = math.log2(fold_change_cutoff)
    max_abs = float(np.max(np.abs(resp)))
    exceeds_fc = bool(max_abs > log2_cutoff)
    exceeds_bmad = bool(used_bmad > 0 and max_abs > bmad_multiplier * used_bmad)
    systematic = winner["model"] in ("hill", "gnls")

    # The study calls a hit by "exceeding either three times the BMAD ... or a
    # 1.2-fold-change cut-off at any concentration" -- a disjunction. Both
    # components are returned separately so a conjunctive rule can be applied.
    hit = bool(systematic and (exceeds_bmad or exceeds_fc))

    ac50 = None
    efficacy = None
    if systematic:
        ac50 = float(10.0 ** winner["params"]["ga"])
        efficacy = float(sign * winner["params"]["tp"])

    return {
        "winning_model": winner["model"],
        "winning_model_description": {
            "cnst": "Constant -- no systematic concentration-response.",
            "hill": "Monotonic Hill function.",
            "gnls": "Gain-loss: product of two Hill functions with a shared top. "
                    "Loss of signal at high concentration is interpreted by the study "
                    "as cytotoxicity rather than as receptor-mediated repression.",
        }[winner["model"]],
        "direction": direction,
        "ac50_uM": ac50,
        "log_ac50_modl_ga": winner["params"].get("ga"),
        "efficacy_modl_tp_log2fc": efficacy,
        "hill_coefficient_gw": winner["params"].get("gw"),
        "loss_log_ac50_la": winner["params"].get("la"),
        "loss_coefficient_lw": winner["params"].get("lw"),
        "hit_call": hit,
        "hit_criteria": {
            "rule": "systematic model (hill or gnls) AND (exceeds 3x BMAD OR exceeds 1.2 fold-change)",
            "winning_model_is_systematic": systematic,
            "exceeds_bmad_threshold": exceeds_bmad,
            "bmad_multiplier": bmad_multiplier,
            "bmad": used_bmad,
            "bmad_source": bmad_source,
            "bmad_caveat": (
                "Single-curve BMAD is a degenerate approximation of the study's "
                "plate-wide definition; supply a plate-wide value for a defensible hit call."
                if bmad_source == "single_curve_estimate" else None
            ),
            "exceeds_fold_change_cutoff": exceeds_fc,
            "fold_change_cutoff": fold_change_cutoff,
            "log2_fold_change_cutoff": log2_cutoff,
            "max_absolute_response_log2fc": max_abs,
        },
        "model_comparison": [
            {
                "model": f["model"],
                "aic": f["aic"],
                "loglik": f["loglik"],
                "n_parameters": {"cnst": 1, "hill": 4, "gnls": 6}[f["model"]],
                "params": f["params"],
            }
            for f in sorted(fits, key=lambda f: f["aic"])
        ],
        "units": {
            "concentrations": "uM",
            "responses": "log2 fold-change (tcpl rval / delta-delta-Ct vs DMSO control median)",
            "ac50_uM": "uM",
        },
        "method": {
            "models": ["constant", "hill", "gain-loss"],
            "error_model": f"Student's t, {T_DF} degrees of freedom",
            "selection": "lowest AIC",
            "reference": "tcpl pipeline as applied in Franzosa et al. 2021, "
                         "doi:10.1038/s41540-020-00166-2; model forms per Filer et al. 2017, "
                         "doi:10.1093/bioinformatics/btw680",
            "bmd_disclaimer": "No BMD/BMC is computed. The source study performs no "
                              "benchmark dose modelling and does not use a BMR of 1.349 SD.",
        },
    }
