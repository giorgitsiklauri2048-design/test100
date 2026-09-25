"""Tests for the tcpl-style concentration-response fitting."""

from __future__ import annotations

import inspect
import math

import pytest

from franzosa_mcp.curve_fit import (
    CurveFitError,
    estimate_bmad,
    fit_concentration_response,
)
from franzosa_mcp.data_access import load_data

FIXTURES = load_data()["synthetic_fixtures"]
CONC = FIXTURES["concentration_series_uM"]


def _case(case_id: str) -> dict:
    for case in FIXTURES["cases"]:
        if case["id"] == case_id:
            return case
    raise AssertionError(f"fixture {case_id} missing")


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda c: c["id"])
def test_synthetic_fixtures_select_expected_model(case: dict) -> None:
    result = fit_concentration_response(CONC, case["responses_log2fc"])
    assert result["winning_model"] == case["expected_winning_model"]
    assert result["hit_call"] is case["expected_hit"]


def test_hill_fit_recovers_ac50_in_tested_range() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_hill_active")["responses_log2fc"])
    assert result["ac50_uM"] is not None
    assert min(CONC) <= result["ac50_uM"] <= max(CONC)
    assert result["direction"] == "up"
    assert result["efficacy_modl_tp_log2fc"] > 0


def test_downregulation_is_detected_and_signed() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_downregulation")["responses_log2fc"])
    assert result["direction"] == "down"
    assert result["efficacy_modl_tp_log2fc"] < 0
    assert result["ac50_uM"] is not None


def test_inactive_series_yields_no_potency() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_inactive")["responses_log2fc"])
    assert result["winning_model"] == "cnst"
    assert result["ac50_uM"] is None
    assert result["efficacy_modl_tp_log2fc"] is None
    assert result["hit_call"] is False


def test_gain_loss_reports_loss_parameters_above_gain() -> None:
    result = fit_concentration_response(
        CONC, _case("synthetic_gnls_cytotoxic_falloff")["responses_log2fc"]
    )
    assert result["winning_model"] == "gnls"
    assert result["loss_log_ac50_la"] > result["log_ac50_modl_ga"]
    assert "cytotoxicity" in result["winning_model_description"]


def test_aic_table_is_complete_and_ordered() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_hill_active")["responses_log2fc"])
    table = result["model_comparison"]
    assert {row["model"] for row in table} == {"cnst", "hill", "gnls"}
    assert [row["aic"] for row in table] == sorted(row["aic"] for row in table)
    assert table[0]["model"] == result["winning_model"]
    assert [row["n_parameters"] for row in table if row["model"] == "gnls"] == [6]


def test_fold_change_cutoff_uses_log2_scale() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_hill_active")["responses_log2fc"])
    criteria = result["hit_criteria"]
    assert criteria["fold_change_cutoff"] == 1.2
    assert criteria["log2_fold_change_cutoff"] == pytest.approx(math.log2(1.2))
    assert criteria["exceeds_fold_change_cutoff"] is True


def test_both_hit_components_are_reported_separately() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_hill_active")["responses_log2fc"])
    criteria = result["hit_criteria"]
    assert set(criteria) >= {
        "exceeds_bmad_threshold",
        "exceeds_fold_change_cutoff",
        "winning_model_is_systematic",
    }
    # The study's rule is a disjunction; both components must remain inspectable
    # so a conjunctive rule can be applied downstream.
    assert result["hit_call"] is (
        criteria["winning_model_is_systematic"]
        and (criteria["exceeds_bmad_threshold"] or criteria["exceeds_fold_change_cutoff"])
    )


def test_supplied_plate_wide_bmad_is_flagged_and_used() -> None:
    responses = _case("synthetic_hill_active")["responses_log2fc"]
    default = fit_concentration_response(CONC, responses)
    assert default["hit_criteria"]["bmad_source"] == "single_curve_estimate"
    assert default["hit_criteria"]["bmad_caveat"] is not None

    supplied = fit_concentration_response(CONC, responses, bmad=0.05)
    assert supplied["hit_criteria"]["bmad_source"] == "supplied_plate_wide"
    assert supplied["hit_criteria"]["bmad"] == 0.05
    assert supplied["hit_criteria"]["bmad_caveat"] is None


def test_ldh_multiplier_is_stricter_than_transcriptomic() -> None:
    # A response just above 3x but below 10x BMAD is a transcriptomic hit only.
    responses = [0.0, 0.0, 0.0, 0.0, 0.10, 0.16, 0.19, 0.20]
    transcriptomic = fit_concentration_response(
        CONC, responses, fold_change_cutoff=1.5, bmad=0.02, bmad_multiplier=3.0
    )
    cytotox = fit_concentration_response(
        CONC, responses, fold_change_cutoff=1.5, bmad=0.02, bmad_multiplier=10.0
    )
    assert transcriptomic["hit_criteria"]["exceeds_bmad_threshold"] is True
    assert cytotox["hit_criteria"]["exceeds_bmad_threshold"] is False


def test_estimate_bmad_uses_two_lowest_concentrations() -> None:
    # Only the two lowest concentrations contribute; the large top-dose values must not.
    assert estimate_bmad([1.0, 2.0, 10.0, 100.0], [0.1, 0.3, 9.0, 9.0]) == pytest.approx(0.1)


def test_no_bmd_or_bmr_value_is_emitted() -> None:
    result = fit_concentration_response(CONC, _case("synthetic_hill_active")["responses_log2fc"])

    # No result field may be a benchmark dose/concentration or benchmark response.
    for field in result:
        assert "bmc" not in field.lower(), field
        assert "bmr" not in field.lower(), field
        assert "benchmark" not in field.lower(), field

    # The API must not accept a benchmark response at all.
    params = inspect.signature(fit_concentration_response).parameters
    assert not any("bmr" in name or "benchmark" in name for name in params)

    # 1.349 appears only in the prose disclaimer that disowns it. (A repr-wide
    # scan would false-positive: a fitted Hill coefficient can legitimately
    # begin 1.349, as gw does for this fixture.)
    disclaimer = result["method"]["bmd_disclaimer"]
    assert "no bmd/bmc is computed" in disclaimer.lower()
    assert "1.349" in disclaimer
    assert "BMDExpress" not in result["method"]["reference"]


@pytest.mark.parametrize(
    "concentrations,responses,message",
    [
        ([1.0, 2.0, 3.0], [0.1, 0.2, 0.3], "at least 4"),
        ([1.0, 2.0, 3.0, 4.0], [0.1, 0.2], "length mismatch"),
        ([0.0, 1.0, 2.0, 3.0], [0.1, 0.2, 0.3, 0.4], "strictly positive"),
        ([-1.0, 1.0, 2.0, 3.0], [0.1, 0.2, 0.3, 0.4], "strictly positive"),
        ([1.0, 2.0, 3.0, float("nan")], [0.1, 0.2, 0.3, 0.4], "finite"),
    ],
)
def test_invalid_input_raises(concentrations, responses, message) -> None:
    with pytest.raises(CurveFitError, match=message):
        fit_concentration_response(concentrations, responses)


def test_fold_change_cutoff_must_exceed_one() -> None:
    with pytest.raises(CurveFitError, match="must be > 1.0"):
        fit_concentration_response(CONC, [0.1] * 8, fold_change_cutoff=0.5)
