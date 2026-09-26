"""Fidelity tests: the server must delegate to the authors' code, not shadow it.

If ``curve_curator`` changes a constant or a formula, these tests are the ones
that should notice.
"""

from __future__ import annotations

import importlib.metadata as metadata
import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import f as f_distribution

from curve_curator import models, thresholding
from curvecurator_mcp import engine, reference

DOSES_NM = [0.0316, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0, 316.0]


def inhibition(pec50=8.5, front=1.0, back=0.2, slope=1.0, noise=0.0, seed=0):
    x = np.log10(np.asarray(DOSES_NM) * 1e-9)
    y = (front - back) / (1 + 10 ** (slope * (x + pec50))) + back
    if noise:
        y = y + np.random.default_rng(seed).normal(0, noise, y.size)
    return y.tolist()


# --------------------------------------------------------------------------
# The dependency is present and pinned to the range the README claims
# --------------------------------------------------------------------------

def test_curve_curator_is_installed_in_the_supported_range():
    version = metadata.version("curve_curator")
    major, minor = (int(part) for part in version.split(".")[:2])
    assert (major, minor) >= (0, 6), f"curve_curator {version} is below the pinned floor"


def test_recorded_pin_matches_the_reference_data():
    binding = reference.load_reference()["implementation_binding"]
    assert binding["package"] == "curve_curator"
    assert binding["pinned_version"] == ">=0.6.0,<0.7.0"


# --------------------------------------------------------------------------
# Degrees of freedom come from the authors' model, not a local copy
# --------------------------------------------------------------------------

def test_effective_dofs_are_the_authors_values():
    for n in (5, 6, 7, 8, 9, 10, 17, 25):
        assert engine.effective_dofs(n) == tuple(
            float(v) for v in models.LogisticModel().get_dofs(n, optimized=True)
        )


def test_linear_dofs_are_the_authors_values():
    for n in (6, 9, 17):
        assert engine.effective_dofs(n, optimized=False) == tuple(
            float(v) for v in models.LogisticModel().get_dofs(n, optimized=False)
        )


# --------------------------------------------------------------------------
# F-value and p-value come from LogisticModel.evaluate
# --------------------------------------------------------------------------

def test_f_value_and_p_value_match_a_direct_evaluate_call():
    """Reproduce the engine's path with bare curve_curator calls and compare."""
    responses = inhibition(noise=0.04, seed=1)
    fit = engine.fit_curve(DOSES_NM, responses)

    x = np.append(-np.inf, np.log10(np.asarray(DOSES_NM) * 1e-9))
    y = np.append(1.0, responses)
    m0 = models.MeanModel()
    m0.set_initial_guess(intercept=float(np.mean(y[1:])), noise=float(np.std(y)))
    m0.fit_ols(x, y)
    m1 = models.LogisticModel()
    m1.efficiently_fit_ols(x, y, noise=m0.noise)

    f_value, p_value = m1.evaluate(x, y)
    assert fit["statistics"]["recalibrated_f_value"] == pytest.approx(f_value, rel=1e-6)
    assert fit["statistics"]["p_value"] == pytest.approx(p_value, rel=1e-6)
    assert fit["null_model"]["rmse"] == pytest.approx(m0.calculate_rmse(x, y), rel=1e-9)


def test_pec50_is_never_fixed_so_the_f_statistic_stays_defined():
    """The recalibrated F scales by n/k, so a fully fixed model would divide by zero.

    The engine exposes only slope, front and back as fixable, leaving k >= 1.
    """
    fit = engine.fit_curve(
        DOSES_NM, inhibition(noise=0.02, seed=6), fixed_slope=1.0, fixed_front=1.0, fixed_back=0.2
    )
    assert fit["statistics"]["recalibrated_f_value"] is not None
    assert fit["curve_parameters"]["pEC50"] is not None
    assert models.LogisticModel(slope=1.0, front=1.0, back=0.2).n_parameter() == 1


# --------------------------------------------------------------------------
# s0 and the relevance score come from thresholding
# --------------------------------------------------------------------------

def test_s0_is_the_authors_get_s0():
    for n, alpha, fc_lim in [(9, 0.05, 0.45), (17, 0.01, 0.3), (6, 0.1, 0.5)]:
        dfn, dfd = engine.effective_dofs(n)
        expected = float(thresholding.get_s0(fc_lim=fc_lim, alpha=alpha, dfn=dfn, dfd=dfd))
        assert engine.relevance_score(50.0, -1.0, n, alpha=alpha, fc_lim=fc_lim)["s0"] == (
            pytest.approx(expected)
        )


def test_s0_adjusted_f_is_the_authors_sam_correction():
    scored = engine.relevance_score(50.0, -1.2, 9, alpha=0.05, fc_lim=0.45)
    expected = float(thresholding.sam_correction(50.0, -1.2, s0=scored["s0"]))
    assert scored["s0_adjusted_f_value"] == pytest.approx(expected)


def test_sam_correction_matches_its_documented_closed_form():
    """F_adj = 1 / ((1/sqrt(F)) + s0/|fc|)^2, per the authors' eq. 4 comment."""
    f_value, fold_change, s0 = 50.0, -1.2, 0.2021
    expected = 1 / ((1 / math.sqrt(f_value)) + (s0 / abs(fold_change))) ** 2
    assert float(thresholding.sam_correction(f_value, fold_change, s0)) == pytest.approx(expected)


def test_relevance_score_uses_the_published_location_shift():
    scored = engine.relevance_score(50.0, -1.2, 9, alpha=0.05, fc_lim=0.45)
    dfn, dfd = engine.effective_dofs(9)
    expected = -math.log10(
        float(
            f_distribution.sf(
                scored["s0_adjusted_f_value"], dfn=dfn, dfd=dfd, loc=0.12, scale=1.0
            )
        )
    )
    assert scored["relevance_score"] == pytest.approx(expected, rel=1e-9)


# --------------------------------------------------------------------------
# Classification matches the authors' vectorised classifier
# --------------------------------------------------------------------------

def _authors_classification(fit, scoring, alpha, fc_lim, not_rmse_limit):
    """Run ``thresholding.define_regulated_curves`` on a one-row frame."""
    frame = pd.DataFrame(
        {
            "Curve Relevance Score": [scoring["relevance_score"]],
            "Curve Fold Change": [fit["curve_fold_change_log2"]],
            "pEC50": [fit["curve_parameters"]["pEC50"]],
            "Null RMSE": [fit["null_model"]["rmse"]],
            "Null Model": [fit["null_model"]["intercept"]],
            "Signal Quality": [np.inf],
        }
    )
    out = thresholding.define_regulated_curves(
        frame,
        cut_col="Curve Relevance Score",
        cut_value=-np.log10(alpha),
        fc_lim=fc_lim,
        not_rmse_limit=not_rmse_limit,
        not_cut_limit=np.inf,
        quality_min=-np.inf,
        pEC50_range=(-np.inf, np.inf),
    )
    value = out["Curve Regulation"].iloc[0]
    return "unclear" if pd.isna(value) else value


@pytest.mark.parametrize(
    "responses,expected",
    [
        (inhibition(noise=0.02, seed=2), "down"),
        (inhibition(back=4.0, noise=0.02, seed=3), "up"),
        ([1.0, 1.01, 0.99, 1.0, 1.02, 0.98, 1.0, 1.01, 0.99], "not"),
        ([1.0, 1.4, 0.6, 1.5, 0.5, 1.3, 0.7, 1.45, 0.62], "unclear"),
        (inhibition(back=0.82, noise=0.004, seed=4), "not"),
    ],
)
def test_classification_agrees_with_the_authors_classifier(responses, expected):
    alpha, fc_lim, not_rmse_limit = 0.05, 0.45, 0.1
    fit = engine.fit_curve(DOSES_NM, responses)
    mine = engine.classify_curve(
        fit, alpha=alpha, fc_lim=fc_lim, not_rmse_limit=not_rmse_limit
    )
    theirs = _authors_classification(
        fit, mine["scoring"], alpha, fc_lim, not_rmse_limit
    )
    assert mine["curve_regulation"] == theirs == expected


def test_classification_agrees_across_a_grid_of_asymptotes():
    responses = inhibition(back=0.6, noise=0.03, seed=5)
    fit = engine.fit_curve(DOSES_NM, responses)
    for alpha in (0.01, 0.05, 0.1):
        for fc_lim in (0.0, 0.2, 0.45, 0.9):
            mine = engine.classify_curve(fit, alpha=alpha, fc_lim=fc_lim)
            theirs = _authors_classification(fit, mine["scoring"], alpha, fc_lim, 0.1)
            assert mine["curve_regulation"] == theirs, (alpha, fc_lim)


# --------------------------------------------------------------------------
# FDR comes from the authors' get_fdr and simulator
# --------------------------------------------------------------------------

def test_fdr_expression_is_the_authors_pseudocounted_ratio():
    target = pd.DataFrame({"score": [5.0, 4.0, 3.0]})
    decoy = pd.DataFrame({"score": [2.0, 1.0, 0.5]})
    expected = (0 + 1) / (3 + 1)
    assert float(thresholding.get_fdr(target, decoy, "score", 2.5, 1.0)) == pytest.approx(expected)


def test_decoys_are_drawn_by_the_authors_simulator():
    from curve_curator import data_simulator

    assert hasattr(data_simulator, "simulate_decoys")
    variance_model = data_simulator.DEFAULT_VARIANCE_MODEL
    # Recorded in the reference data as an implementation detail, not a paper value.
    recorded = reference.load_reference()["statistical_framework"]["h0_simulation"][
        "default_variance_model_in_code"
    ]
    assert "dfn=11" in recorded and "dfd=11" in recorded
    assert variance_model.kwds["dfn"] == 11
    assert variance_model.kwds["dfd"] == 11
    assert variance_model.kwds["loc"] == pytest.approx(0.035)
    assert variance_model.kwds["scale"] == pytest.approx(0.066)


# --------------------------------------------------------------------------
# No local reimplementation of the statistics
# --------------------------------------------------------------------------

def test_engine_imports_the_authors_modules():
    import inspect

    source = inspect.getsource(engine)
    assert "from curve_curator import data_simulator, models, thresholding" in source


def test_engine_does_not_hard_code_the_dof_polynomial():
    """The dfd expression must be read from the authors' model, never copied in."""
    import inspect

    source = inspect.getsource(engine)
    assert "n - 2.5" not in source
    assert "(n-4)**4" not in source


# --------------------------------------------------------------------------
# The CLI command we tell users to run must be the one that actually exists
# --------------------------------------------------------------------------

def test_emitted_cli_command_is_the_packages_real_console_script():
    """The executable is ``CurveCurator``; ``curve_curator`` is only the module.

    The repository declares ``CurveCurator = "curve_curator.__main__:main"``, so
    telling a user to run ``curve_curator <toml>`` yields "command not found".
    """
    from importlib.metadata import entry_points

    from curvecurator_mcp.config_builder import build_toml

    declared = {
        ep.name
        for ep in entry_points(group="console_scripts")
        if (ep.value or "").startswith("curve_curator")
    }
    assert declared == {"CurveCurator"}, f"unexpected console scripts: {declared}"

    result = build_toml([1.0, 10.0, 100.0])
    for command in result["run_commands"]:
        assert command.split()[0] in declared, command
    assert "CurveCurator <this file>" in result["toml"]
    assert "curve_curator <" not in result["toml"]
