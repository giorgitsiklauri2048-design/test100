"""Correctness tests for the binding layer over ``curve_curator``."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import f as f_distribution

from curvecurator_mcp import engine
from curvecurator_mcp.engine import EngineError

DOSES_NM = [0.0316, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0, 316.0]


def simulate(pec50: float, front: float, back: float, slope: float = 1.0, noise: float = 0.0,
             doses=DOSES_NM, seed: int = 0) -> list[float]:
    """Simulate responses from the paper's 4-parameter log-logistic function."""
    x = np.log10(np.asarray(doses) * 1e-9)
    y = (front - back) / (1 + 10 ** (slope * (x + pec50))) + back
    if noise:
        y = y + np.random.default_rng(seed).normal(0, noise, y.size)
    return y.tolist()


# --------------------------------------------------------------------------
# Dose handling and the control point
# --------------------------------------------------------------------------

def test_n_counts_doses_plus_control():
    """The paper counts the control as one of the n data points."""
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2))
    assert fit["n_dose_points"] == 9
    assert fit["n_data_points"] == 10


def test_ctrp_style_16_doses_gives_n_17():
    doses = [0.001 * 2 ** i for i in range(16)]
    fit = engine.fit_curve(doses, simulate(8.5, 1.0, 0.2, doses=doses))
    assert fit["n_data_points"] == 17


def test_zero_dose_rejected_because_control_is_implicit():
    with pytest.raises(EngineError, match="control is added automatically"):
        engine.fit_curve([0.0] + DOSES_NM, [1.0] + simulate(8.5, 1.0, 0.2))


def test_dose_unit_conversion_shifts_pec50_by_three_decades():
    responses = simulate(8.5, 1.0, 0.2)
    nm = engine.fit_curve(DOSES_NM, responses, dose_unit="nM")
    um = engine.fit_curve(DOSES_NM, responses, dose_unit="uM")
    assert um["curve_parameters"]["pEC50"] == pytest.approx(
        nm["curve_parameters"]["pEC50"] - 3.0, abs=1e-6
    )


def test_unknown_dose_unit_rejected():
    with pytest.raises(EngineError, match="Unknown dose_unit"):
        engine.to_log10_molar([1.0], "molar")


def test_mismatched_lengths_rejected():
    with pytest.raises(EngineError, match="same length"):
        engine.fit_curve(DOSES_NM, [1.0, 0.5])


def test_too_few_points_rejected_at_n_4():
    with pytest.raises(EngineError, match="n > 4"):
        engine.fit_curve([1.0, 10.0, 100.0], [1.0, 0.5, 0.2])


def test_missing_responses_are_dropped_and_lower_n():
    responses = simulate(8.5, 1.0, 0.2)
    responses[3] = float("nan")
    fit = engine.fit_curve(DOSES_NM, responses)
    assert fit["n_missing_responses_dropped"] == 1
    assert fit["n_data_points"] == 9
    assert any("lowering n" in c for c in fit["caveats"])


# --------------------------------------------------------------------------
# Curve fitting
# --------------------------------------------------------------------------

def test_recovers_simulated_parameters_without_noise():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2, slope=1.0))
    params = fit["curve_parameters"]
    assert params["pEC50"] == pytest.approx(8.5, abs=0.01)
    assert params["front"] == pytest.approx(1.0, abs=0.01)
    assert params["back"] == pytest.approx(0.2, abs=0.01)
    assert params["slope"] == pytest.approx(1.0, abs=0.02)
    assert fit["goodness_of_fit"]["r_squared"] > 0.999


def test_ec50_is_ten_to_minus_pec50_in_molar():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2))
    assert fit["curve_parameters"]["EC50_molar"] == pytest.approx(
        10 ** -fit["curve_parameters"]["pEC50"]
    )


def test_fold_change_is_log2_of_model_at_lowest_to_highest_dose():
    """Model at the highest dose over model at the lowest dose, not back over front.

    At the extreme doses the curve has not fully reached either plateau, so the
    fold change is slightly compressed relative to log2(back / front). That
    compression is exactly the effect the paper warns about.
    """
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2))
    x_lo, x_hi = math.log10(min(DOSES_NM) * 1e-9), math.log10(max(DOSES_NM) * 1e-9)
    p = fit["curve_parameters"]

    def model(x):
        return (p["front"] - p["back"]) / (1 + 10 ** (p["slope"] * (x + p["pEC50"]))) + p["back"]

    assert fit["curve_fold_change_log2"] == pytest.approx(
        math.log2(model(x_hi) / model(x_lo)), abs=1e-6
    )
    assert abs(fit["curve_fold_change_log2"]) < abs(math.log2(0.2))
    assert "lowest dose" in fit["curve_fold_change_definition"]


def test_control_relative_fold_change_is_a_distinct_definition():
    responses = simulate(8.5, 1.4, 0.2)  # front plateau above the control
    default = engine.fit_curve(DOSES_NM, responses)
    to_control = engine.fit_curve(DOSES_NM, responses, control_fold_change=True)
    assert default["curve_fold_change_log2"] != pytest.approx(
        to_control["curve_fold_change_log2"], abs=1e-6
    )
    assert "control" in to_control["curve_fold_change_definition"]
    assert any("false-positive" in c for c in to_control["caveats"])


def test_fixed_parameters_are_honoured_and_reported():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2), fixed_slope=1.0, fixed_front=1.0)
    assert fit["curve_parameters"]["slope"] == pytest.approx(1.0)
    assert fit["curve_parameters"]["front"] == pytest.approx(1.0)
    assert fit["fixed_parameters"] == {"slope": 1.0, "front": 1.0}


def test_mle_fit_runs_and_agrees_with_ols_on_clean_data():
    responses = simulate(8.5, 1.0, 0.2)
    ols = engine.fit_curve(DOSES_NM, responses, fit_type="OLS")
    mle = engine.fit_curve(DOSES_NM, responses, fit_type="MLE")
    assert mle["fit_type"] == "MLE"
    assert mle["curve_parameters"]["pEC50"] == pytest.approx(
        ols["curve_parameters"]["pEC50"], abs=0.1
    )


def test_invalid_fit_type_rejected():
    with pytest.raises(EngineError, match="fit_type"):
        engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2), fit_type="ridge")


def test_potency_below_assayed_range_is_flagged():
    """The paper names compressed fold change as a false-negative source."""
    fit = engine.fit_curve(DOSES_NM, simulate(12.0, 1.0, 0.2))
    assert fit["potency_within_assayed_range"] is False
    assert any("compressed" in c for c in fit["caveats"])


def test_every_fit_warns_against_reading_potency_off_a_nonsignificant_curve():
    fit = engine.fit_curve(DOSES_NM, [1.0] * 9)
    assert any("non-significant curve" in c for c in fit["caveats"])


# --------------------------------------------------------------------------
# Effective degrees of freedom and the recalibrated F-statistic
# --------------------------------------------------------------------------

def test_effective_dofs_match_the_published_expression():
    for n in range(5, 20):
        dfn, dfd = engine.effective_dofs(n)
        assert dfn == 5
        expected = (0.8 - 1 / ((n - 4) ** 4 / n + 4)) * (n - 2.5)
        assert dfd == pytest.approx(expected)


def test_low_n_correction_is_negligible_above_ten_points():
    """The paper describes the small-n term as irrelevant beyond about n = 10."""
    correction = 1 / ((12 - 4) ** 4 / 12 + 4)
    assert correction < 0.01


def test_linear_dofs_are_the_documented_fallback():
    dfn, dfd = engine.effective_dofs(9, optimized=False)
    assert (dfn, dfd) == (3, 5)  # k-1, n-k for k = 4


def test_dofs_reject_n_at_or_below_parameter_count():
    with pytest.raises(EngineError):
        engine.effective_dofs(4)


def test_recalibrated_f_value_matches_the_published_formula():
    """F = (SSE_M0 - SSE_M1) / SSE_M1 * (n / k), computed independently here."""
    from curve_curator import models

    responses = simulate(8.5, 1.0, 0.2, noise=0.05, seed=3)
    fit = engine.fit_curve(DOSES_NM, responses)

    x = np.append(-np.inf, np.log10(np.asarray(DOSES_NM) * 1e-9))
    y = np.append(1.0, responses)
    m1 = models.LogisticModel(
        pec50=fit["curve_parameters"]["pEC50"],
        slope=fit["curve_parameters"]["slope"],
        front=fit["curve_parameters"]["front"],
        back=fit["curve_parameters"]["back"],
    )
    sse1 = m1.calculate_sum_squared_residuals(x, y)
    sse0 = float(np.var(y) * y.size)
    expected = (sse0 - sse1) / sse1 * (len(y) / 4)
    assert fit["statistics"]["recalibrated_f_value"] == pytest.approx(expected, rel=1e-3)


def test_p_value_uses_the_published_location_shift():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2, noise=0.05, seed=4))
    stats = fit["statistics"]
    assert stats["loc"] == 0.12
    assert stats["scale"] == 1.0
    expected = float(
        f_distribution.sf(
            stats["recalibrated_f_value"], dfn=stats["dfn"], dfd=stats["dfd"], loc=0.12, scale=1.0
        )
    )
    assert stats["p_value"] == pytest.approx(expected, rel=1e-9)


def test_flat_curve_gives_a_small_f_value_and_large_p_value():
    fit = engine.fit_curve(DOSES_NM, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert fit["statistics"]["p_value"] > 0.5


def test_linear_f_statistic_is_selectable_and_differs():
    responses = simulate(8.5, 1.0, 0.2, noise=0.05, seed=5)
    recal = engine.fit_curve(DOSES_NM, responses, optimized_dofs=True)
    linear = engine.fit_curve(DOSES_NM, responses, optimized_dofs=False)
    assert recal["statistics"]["p_value"] != pytest.approx(
        linear["statistics"]["p_value"], rel=1e-6
    )


# --------------------------------------------------------------------------
# s0 and the relevance score
# --------------------------------------------------------------------------

def test_s0_round_trips_to_the_fold_change_asymptote():
    dfn, dfd = engine.effective_dofs(9)
    scored = engine.relevance_score(100.0, -1.0, 9, alpha=0.05, fc_lim=0.45)
    recovered = scored["s0"] * math.sqrt(
        f_distribution.ppf(1 - 0.05, dfn=dfn, dfd=dfd)
    )
    assert recovered == pytest.approx(0.45)


def test_relevance_score_equals_minus_log10_p_when_fc_lim_is_zero():
    """The paper states this identity for s0 = 0."""
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2, noise=0.05, seed=6))
    scored = engine.relevance_score(
        fit["statistics"]["recalibrated_f_value"],
        fit["curve_fold_change_log2"],
        fit["n_data_points"],
        alpha=0.05,
        fc_lim=0.0,
    )
    assert scored["s0"] == 0.0
    assert scored["is_valid_p_value"] is True
    assert scored["relevance_score"] == pytest.approx(
        -math.log10(fit["statistics"]["p_value"]), rel=1e-6
    )


def test_relevance_score_is_not_advertised_as_a_p_value_when_fc_lim_positive():
    scored = engine.relevance_score(100.0, -1.0, 9, fc_lim=0.45)
    assert scored["is_valid_p_value"] is False
    assert "NOT a p-value" in scored["interpretation"]


def test_sam_adjustment_penalises_small_effect_sizes_more():
    big = engine.relevance_score(100.0, -2.0, 9, fc_lim=0.45)
    small = engine.relevance_score(100.0, -0.5, 9, fc_lim=0.45)
    assert big["relevance_score"] > small["relevance_score"]
    assert big["s0"] == pytest.approx(small["s0"])


def test_cutoff_is_minus_log10_alpha():
    scored = engine.relevance_score(100.0, -1.0, 9, alpha=0.01)
    assert scored["relevance_score_cutoff"] == pytest.approx(2.0)


def test_s0_depends_on_n():
    few = engine.relevance_score(100.0, -1.0, 6, fc_lim=0.45)
    many = engine.relevance_score(100.0, -1.0, 17, fc_lim=0.45)
    assert few["s0"] != pytest.approx(many["s0"])


def test_relevance_score_rejects_out_of_range_asymptotes():
    with pytest.raises(EngineError, match="alpha"):
        engine.relevance_score(10.0, 1.0, 9, alpha=0.0)
    with pytest.raises(EngineError, match="fc_lim"):
        engine.relevance_score(10.0, 1.0, 9, fc_lim=-0.1)


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def test_clear_inhibition_is_classified_down():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2, noise=0.02, seed=7))
    result = engine.classify_curve(fit, alpha=0.05, fc_lim=0.45)
    assert result["curve_regulation"] == "down"
    assert result["criteria"]["relevance_score_above_cutoff"] is True
    assert result["criteria"]["abs_fold_change_at_least_fc_lim"] is True


def test_clear_induction_is_classified_up():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 4.0, noise=0.02, seed=8))
    assert engine.classify_curve(fit, fc_lim=0.45)["curve_regulation"] == "up"


def test_flat_low_variance_curve_is_classified_not():
    responses = [1.0, 1.01, 0.99, 1.0, 1.02, 0.98, 1.0, 1.01, 0.99]
    result = engine.classify_curve(engine.fit_curve(DOSES_NM, responses), fc_lim=0.45)
    assert result["curve_regulation"] == "not"
    assert result["criteria"]["null_rmse_within_limit"] is True
    assert "negative set" in result["explanation"]


def test_high_variance_nonresponder_is_unclear_not_not():
    """A noisy flat curve must not be admitted to the negative set."""
    responses = [1.0, 1.4, 0.6, 1.5, 0.5, 1.3, 0.7, 1.45, 0.62]
    result = engine.classify_curve(engine.fit_curve(DOSES_NM, responses), fc_lim=0.45)
    assert result["curve_regulation"] == "unclear"
    assert result["criteria"]["null_rmse_within_limit"] is False
    assert "cannot be proven" in result["explanation"]


def test_significant_but_small_effect_is_withheld_by_the_fold_change_asymptote():
    """The paper's core claim: significance alone must not make a curve relevant.

    The same highly significant curve is called "down" when relevance is purely
    statistical (fc_lim = 0) and is demoted once a fold-change asymptote is set.
    Here it lands in "not" rather than "unclear", because the curve is also flat
    and low-variance enough to be a confident non-responder.
    """
    responses = simulate(8.5, 1.0, 0.82, noise=0.004, seed=9)  # ~0.29 log2 units
    fit = engine.fit_curve(DOSES_NM, responses)
    assert fit["statistics"]["p_value"] < 0.01
    lenient = engine.classify_curve(fit, alpha=0.05, fc_lim=0.0)
    strict = engine.classify_curve(fit, alpha=0.05, fc_lim=0.45)
    assert lenient["curve_regulation"] == "down"
    assert strict["curve_regulation"] == "not"
    assert strict["criteria"]["abs_fold_change_at_least_fc_lim"] is False


def test_pec50_filter_can_withhold_an_out_of_range_potency():
    fit = engine.fit_curve(DOSES_NM, simulate(8.5, 1.0, 0.2, noise=0.02, seed=10))
    inside = engine.classify_curve(fit, fc_lim=0.45, pec50_filter=(7.0, 10.0))
    outside = engine.classify_curve(fit, fc_lim=0.45, pec50_filter=(3.0, 5.0))
    assert inside["curve_regulation"] == "down"
    assert outside["curve_regulation"] == "unclear"
    assert outside["criteria"]["pEC50_within_filter"] is False


def test_not_rmse_limit_default_is_the_pipeline_default():
    fit = engine.fit_curve(DOSES_NM, [1.0] * 9)
    assert engine.classify_curve(fit)["not_rmse_limit"] == 0.1


def test_classification_categories_are_exactly_the_papers_four():
    assert {"up", "down", "not", "unclear"} == {"up", "down", "not", "unclear"}
    responses_by_class = {
        "down": simulate(8.5, 1.0, 0.2, noise=0.02, seed=11),
        "up": simulate(8.5, 1.0, 4.0, noise=0.02, seed=12),
        "not": [1.0, 1.01, 0.99, 1.0, 1.0, 0.99, 1.01, 1.0, 1.0],
        "unclear": [1.0, 1.4, 0.6, 1.5, 0.5, 1.3, 0.7, 1.45, 0.62],
    }
    for expected, responses in responses_by_class.items():
        fit = engine.fit_curve(DOSES_NM, responses)
        assert engine.classify_curve(fit, fc_lim=0.45)["curve_regulation"] == expected


# --------------------------------------------------------------------------
# Decision boundary
# --------------------------------------------------------------------------

def test_boundary_recovers_the_fold_change_asymptotes():
    result = engine.decision_boundary([0.5, 1.0], alpha=0.05, fc_lim=0.45, n_data_points=9)
    neg, pos = result["recovered_fc_asymptotes"]
    assert pos == pytest.approx(0.45)
    assert neg == pytest.approx(-0.45)


def test_boundary_requires_more_significance_at_smaller_effect_size():
    """Cutoffs are -log10(p), so a smaller effect size demands a larger value."""
    result = engine.decision_boundary([0.6, 2.0], alpha=0.05, fc_lim=0.45, n_data_points=9)
    small, large = result["boundary"]
    assert small["minus_log10_p_value_cutoff"] > large["minus_log10_p_value_cutoff"]
    assert result["y_axis"].startswith("-log10(p-value)")


def test_fold_change_inside_the_asymptote_band_is_unreachable():
    """No significance can rescue a curve below the fold-change asymptote."""
    result = engine.decision_boundary([0.05, 1.0], alpha=0.05, fc_lim=0.45, n_data_points=9)
    inside, outside = result["boundary"]
    assert inside["reachable"] is False
    assert inside["minus_log10_p_value_cutoff"] is None
    assert outside["reachable"] is True


def test_boundary_rejects_empty_input():
    with pytest.raises(EngineError, match="At least one fold change"):
        engine.decision_boundary([])


def test_boundary_reports_the_horizontal_equivalent_in_relevance_space():
    result = engine.decision_boundary([1.0], alpha=0.01, fc_lim=0.3)
    assert "2.0000" in result["note"]


# --------------------------------------------------------------------------
# Target-decoy FDR
# --------------------------------------------------------------------------

def _fdr_fixture(n_hits: int = 6, n_flat: int = 24, seed: int = 42):
    rng = np.random.default_rng(seed)
    curves = []
    for i in range(n_hits):
        y = np.asarray(simulate(8.5, 1.0, 0.2)) + rng.normal(0, 0.04, len(DOSES_NM))
        curves.append({"name": f"hit_{i}", "responses": y.tolist()})
    for i in range(n_flat):
        y = 1.0 + rng.normal(0, 0.06, len(DOSES_NM))
        curves.append({"name": f"flat_{i}", "responses": y.tolist()})
    return curves


def test_fdr_recovers_true_responders_and_rejects_flat_curves():
    result = engine.estimate_fdr(_fdr_fixture(), DOSES_NM, fc_lim=0.45, random_seed=1)
    assert result["n_targets"] == 30
    assert result["n_decoys"] == 30
    assert sorted(result["regulated_curves"]) == [f"hit_{i}" for i in range(6)]
    assert result["target_classification_counts"].get("not") == 24


def test_fdr_is_bounded_and_reported_both_globally_and_filtered():
    result = engine.estimate_fdr(_fdr_fixture(), DOSES_NM, fc_lim=0.45, random_seed=2)
    for key in ("global_fdr", "filtered_fdr"):
        assert 0.0 <= result[key] <= 1.0


def test_fdr_is_reproducible_under_a_seed():
    a = engine.estimate_fdr(_fdr_fixture(), DOSES_NM, random_seed=99)
    b = engine.estimate_fdr(_fdr_fixture(), DOSES_NM, random_seed=99)
    assert a["global_fdr"] == b["global_fdr"]


def test_decoy_ratio_scales_the_decoy_count():
    result = engine.estimate_fdr(
        _fdr_fixture(2, 8), DOSES_NM, decoy_ratio=2.0, random_seed=3
    )
    assert result["n_decoys"] == 20
    assert result["target_decoy_ratio"] == pytest.approx(0.5)


def test_fdr_warns_against_tuning_the_boundary_to_a_target():
    result = engine.estimate_fdr(_fdr_fixture(2, 8), DOSES_NM, random_seed=4)
    assert any("recommend against" in c for c in result["caveats"])
    assert any("empirical noise" in c for c in result["caveats"])


def test_fdr_rejects_empty_input_and_bad_ratio():
    with pytest.raises(EngineError, match="At least one curve"):
        engine.estimate_fdr([], DOSES_NM)
    with pytest.raises(EngineError, match="decoy_ratio"):
        engine.estimate_fdr(_fdr_fixture(1, 4), DOSES_NM, decoy_ratio=0.0)


def test_fdr_rejects_curve_without_responses():
    with pytest.raises(EngineError, match="responses"):
        engine.estimate_fdr([{"name": "x"}], DOSES_NM)
