"""Tests for the MCP tools, the resource, the prompt, and the config builder."""

from __future__ import annotations

import json
import math
import tomllib

import numpy as np
import pytest

from curvecurator_mcp import server
from curvecurator_mcp.config_builder import PRESETS, build_toml
from curvecurator_mcp.engine import EngineError

DOSES_NM = [0.0316, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0, 316.0]


def inhibition(pec50=8.5, front=1.0, back=0.2, slope=1.0):
    x = np.log10(np.asarray(DOSES_NM) * 1e-9)
    return ((front - back) / (1 + 10 ** (slope * (x + pec50))) + back).tolist()


# --------------------------------------------------------------------------
# Every tool cites the paper
# --------------------------------------------------------------------------

def test_every_tool_result_carries_the_citation():
    results = [
        server.fit_dose_response_curve(DOSES_NM, inhibition()),
        server.classify_dose_response_curve(DOSES_NM, inhibition()),
        server.compute_relevance_score(100.0, -1.5, 9),
        server.map_decision_boundary([1.0]),
        server.generate_curvecurator_config([1.0, 10.0, 100.0]),
        server.describe_paper_dataset("ctrp"),
    ]
    for result in results:
        assert result["source"]["doi"] == "10.1038/s41467-023-43696-z"


def test_error_payloads_also_carry_the_citation():
    result = server.fit_dose_response_curve([1.0, 2.0], [1.0, 0.5])
    assert "error" in result
    assert result["source"]["doi"] == "10.1038/s41467-023-43696-z"


# --------------------------------------------------------------------------
# fit_dose_response_curve
# --------------------------------------------------------------------------

def test_fit_tool_returns_the_expected_shape():
    result = server.fit_dose_response_curve(DOSES_NM, inhibition())
    for key in (
        "n_data_points",
        "curve_parameters",
        "curve_fold_change_log2",
        "goodness_of_fit",
        "null_model",
        "statistics",
        "caveats",
    ):
        assert key in result
    assert result["curve_parameters"]["pEC50"] == pytest.approx(8.5, abs=0.01)


def test_fit_tool_is_json_serialisable():
    json.dumps(server.fit_dose_response_curve(DOSES_NM, inhibition()))


def test_fit_tool_reports_no_nan_or_infinity():
    blob = json.dumps(server.fit_dose_response_curve(DOSES_NM, inhibition()))
    assert "NaN" not in blob
    assert "Infinity" not in blob


# --------------------------------------------------------------------------
# classify_dose_response_curve
# --------------------------------------------------------------------------

def test_classify_tool_returns_fit_and_classification():
    result = server.classify_dose_response_curve(DOSES_NM, inhibition(), fc_lim=0.45)
    assert result["classification"]["curve_regulation"] == "down"
    assert result["fit"]["curve_parameters"]["pEC50"] == pytest.approx(8.5, abs=0.01)
    assert "relevance_score" in result["classification"]["scoring"]


def test_classify_tool_reporting_guidance_restricts_potency_claims():
    result = server.classify_dose_response_curve(DOSES_NM, inhibition())
    guidance = result["reporting_guidance"]
    assert "up or down" in guidance
    assert "never as a p-value" in guidance


def test_classify_tool_honours_pec50_bounds():
    inside = server.classify_dose_response_curve(
        DOSES_NM, inhibition(), fc_lim=0.45, pec50_min=7.0, pec50_max=10.0
    )
    outside = server.classify_dose_response_curve(
        DOSES_NM, inhibition(), fc_lim=0.45, pec50_min=3.0, pec50_max=5.0
    )
    assert inside["classification"]["curve_regulation"] == "down"
    assert outside["classification"]["curve_regulation"] != "down"


def test_classify_tool_rejects_invalid_alpha():
    assert "error" in server.classify_dose_response_curve(DOSES_NM, inhibition(), alpha=1.5)


# --------------------------------------------------------------------------
# compute_relevance_score
# --------------------------------------------------------------------------

def test_relevance_tool_rescoring_without_refitting():
    fit = server.fit_dose_response_curve(DOSES_NM, inhibition())
    strict = server.compute_relevance_score(
        fit["statistics"]["recalibrated_f_value"],
        fit["curve_fold_change_log2"],
        fit["n_data_points"],
        fc_lim=0.9,
    )
    lenient = server.compute_relevance_score(
        fit["statistics"]["recalibrated_f_value"],
        fit["curve_fold_change_log2"],
        fit["n_data_points"],
        fc_lim=0.1,
    )
    assert strict["s0"] > lenient["s0"]
    assert strict["relevance_score"] < lenient["relevance_score"]


def test_relevance_tool_flags_when_the_score_is_a_p_value():
    assert server.compute_relevance_score(100.0, -1.0, 9, fc_lim=0.0)["is_valid_p_value"] is True
    assert server.compute_relevance_score(100.0, -1.0, 9, fc_lim=0.45)["is_valid_p_value"] is False


# --------------------------------------------------------------------------
# map_decision_boundary
# --------------------------------------------------------------------------

def test_boundary_tool_returns_one_entry_per_fold_change():
    result = server.map_decision_boundary([0.1, 0.5, 1.0, 2.0], alpha=0.05, fc_lim=0.45)
    assert len(result["boundary"]) == 4


def test_boundary_tool_round_trips_the_asymptote():
    result = server.map_decision_boundary([1.0], alpha=0.05, fc_lim=0.3, n_data_points=17)
    assert result["recovered_fc_asymptotes"][1] == pytest.approx(0.3)


# --------------------------------------------------------------------------
# estimate_target_decoy_fdr
# --------------------------------------------------------------------------

def test_fdr_tool_end_to_end():
    rng = np.random.default_rng(11)
    curves = [
        {"name": f"hit_{i}", "responses": (np.asarray(inhibition()) + rng.normal(0, 0.03, 9)).tolist()}
        for i in range(5)
    ] + [
        {"name": f"flat_{i}", "responses": (1.0 + rng.normal(0, 0.05, 9)).tolist()}
        for i in range(15)
    ]
    result = server.estimate_target_decoy_fdr(curves, DOSES_NM, fc_lim=0.45, random_seed=5)
    assert result["n_targets"] == 20
    assert 0.0 <= result["filtered_fdr"] <= 1.0
    assert all(name.startswith("hit_") for name in result["regulated_curves"])


def test_fdr_tool_reports_an_error_for_empty_input():
    assert "error" in server.estimate_target_decoy_fdr([], DOSES_NM)


# --------------------------------------------------------------------------
# describe_paper_dataset
# --------------------------------------------------------------------------

def test_describe_dataset_resolves_all_three():
    for name in ("kinobeads", "ctrp", "decryptm"):
        assert server.describe_paper_dataset(name)["found"] is True


def test_describe_dataset_lists_alternatives_rather_than_guessing():
    result = server.describe_paper_dataset("hepatocyte pesticide screen")
    assert result["found"] is False
    assert result["available"] == ["ctrp", "decryptm", "kinobeads"]


# --------------------------------------------------------------------------
# generate_curvecurator_config
# --------------------------------------------------------------------------

def test_generated_toml_is_valid_toml():
    result = server.generate_curvecurator_config([0.03, 0.3, 3.0, 30.0, 300.0, 3000.0])
    config = tomllib.loads(result["toml"])
    assert set(config) >= {
        "Meta",
        "Experiment",
        "Paths",
        "Processing",
        "Curve Fit",
        "F Statistic",
    }


def test_generated_toml_prepends_the_control_dose():
    result = server.generate_curvecurator_config([1.0, 10.0, 100.0, 1000.0, 10000.0])
    config = tomllib.loads(result["toml"])
    assert config["Experiment"]["doses"][0] == 0.0
    assert result["n_data_points"] == 6
    assert len(config["Experiment"]["experiments"]) == 6


def test_generated_toml_rejects_an_explicit_zero_dose():
    result = server.generate_curvecurator_config([0.0, 1.0, 10.0])
    assert "error" in result


@pytest.mark.parametrize(
    "preset,alpha,fc_lim",
    [("kinobeads", 0.1, 0.5), ("ctrp", 0.05, 0.3), ("decryptm", 0.05, 0.45)],
)
def test_presets_carry_the_papers_asymptotes(preset, alpha, fc_lim):
    result = server.generate_curvecurator_config([1.0, 10.0, 100.0], preset=preset)
    config = tomllib.loads(result["toml"])
    assert config["F Statistic"]["alpha"] == alpha
    assert config["F Statistic"]["fc_lim"] == fc_lim


def test_ctrp_preset_uses_control_relative_fold_change():
    """The paper switched to control-relative fold change for CTRP."""
    config = tomllib.loads(
        server.generate_curvecurator_config([1.0, 10.0, 100.0], preset="ctrp")["toml"]
    )
    assert config["Curve Fit"]["control_fold_change"] is True


def test_decryptm_preset_declares_tmt_peptide_data():
    config = tomllib.loads(
        server.generate_curvecurator_config([1.0, 10.0, 100.0], preset="decryptm")["toml"]
    )
    assert config["Experiment"]["measurement_type"] == "TMT"
    assert config["Experiment"]["data_type"] == "PEPTIDE"


def test_explicit_asymptotes_override_the_preset():
    config = tomllib.loads(
        server.generate_curvecurator_config(
            [1.0, 10.0, 100.0], preset="decryptm", alpha=0.01, fc_lim=1.0
        )["toml"]
    )
    assert config["F Statistic"]["alpha"] == 0.01
    assert config["F Statistic"]["fc_lim"] == 1.0


def test_unknown_preset_is_rejected_with_the_available_list():
    result = server.generate_curvecurator_config([1.0, 10.0], preset="hepatotoxicity")
    assert "error" in result
    assert "kinobeads" in result["error"]


@pytest.mark.parametrize(
    "unit,scale", [("M", "1e+00"), ("mM", "1e-3"), ("uM", "1e-6"), ("nM", "1e-9"), ("pM", "1e-12")]
)
def test_dose_scale_is_written_for_each_unit(unit, scale):
    config = tomllib.loads(
        server.generate_curvecurator_config([1.0, 10.0, 100.0], dose_unit=unit)["toml"]
    )
    assert config["Experiment"]["dose_scale"] == scale


def test_toml_uses_the_sam_route_so_fdr_estimation_is_available():
    config = tomllib.loads(server.generate_curvecurator_config([1.0, 10.0, 100.0])["toml"])
    assert config["F Statistic"]["mtc_method"] == "sam"
    assert config["F Statistic"]["optimized_dofs"] is True


def test_toml_header_cites_the_paper_and_gives_the_run_commands():
    result = server.generate_curvecurator_config([1.0, 10.0, 100.0])
    assert "10.1038/s41467-023-43696-z" in result["toml"]
    assert any("--fdr" in cmd for cmd in result["run_commands"])


def test_preset_notes_are_surfaced():
    result = server.generate_curvecurator_config([1.0, 10.0], preset="decryptm")
    assert any("46%" in note for note in result["preset_notes"])


def test_experiments_length_must_match_doses_plus_control():
    with pytest.raises(EngineError, match="one entry per dose"):
        build_toml([1.0, 10.0], experiments=[1, 2])


def test_every_preset_is_documented():
    for name, preset in PRESETS.items():
        assert preset["description"]
        assert preset["notes"]
        assert 0.0 < preset["alpha"] <= 1.0
        assert preset["fc_lim"] >= 0.0


# --------------------------------------------------------------------------
# Resource and prompt
# --------------------------------------------------------------------------

def test_resource_is_valid_json_with_the_expected_sections():
    payload = json.loads(server.paper_summary())
    assert set(payload) >= {
        "source",
        "implementation_binding",
        "statistical_framework",
        "pipeline_defaults",
        "datasets",
        "stated_limitations",
        "not_reproduced_here",
    }


def test_prompt_enforces_the_papers_reporting_discipline():
    text = server.plan_dose_response_analysis("TMT phosphoproteome, 9 doses", "19000")
    assert "TMT phosphoproteome, 9 doses" in text
    assert "curvecurator://paper-summary" in text
    assert "Do NOT pick the asymptotes by tuning them" in text
    assert "Never call the relevance score a p-value" in text
    assert "unclear" in text
    assert "10.1038/s41467-023-43696-z" in text


def test_prompt_states_the_dataset_anchors_for_the_fold_change_asymptote():
    text = server.plan_dose_response_analysis()
    assert "0.5" in text and "0.3" in text and "0.45" in text


def test_prompt_handles_missing_arguments():
    text = server.plan_dose_response_analysis()
    assert "not specified" in text
