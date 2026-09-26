"""MCP server exposing the CurveCurator dose-response statistics.

Source: Bayer FP, Gander M, Kuster B, The M. "CurveCurator: a recalibrated
F-statistic to assess, classify, and explore significance of dose-response
curves." Nature Communications 14:7902 (2023).
doi:10.1038/s41467-023-43696-z

All statistics are computed by calling the authors' own ``curve_curator``
package. This server adds no statistical logic of its own.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import engine, reference
from .config_builder import PRESETS, build_toml
from .engine import EngineError

mcp = MCPServer("curvecurator-dose-response")


def _err(exc: Exception) -> dict[str, Any]:
    return {"error": str(exc), "source": reference.citation()}


@mcp.tool()
def fit_dose_response_curve(
    doses: list[float],
    responses: list[float],
    dose_unit: str = "nM",
    fit_type: str = "OLS",
    control_fold_change: bool = False,
    fixed_slope: float | None = None,
    fixed_front: float | None = None,
    fixed_back: float | None = None,
    optimized_dofs: bool = True,
) -> dict[str, Any]:
    """Fit a 4-parameter log-logistic curve and evaluate the recalibrated F-statistic.

    Fits the mean model (M0, response independent of dose) and the log-logistic
    model (M1, parameters pEC50 / slope / front / back), then computes
    F = (SSE_M0 - SSE_M1) / SSE_M1 * (n / k) and its p-value from an F-distribution
    with the paper's effective degrees of freedom. Executed by ``curve_curator``.

    Args:
        doses: Non-zero doses. The control is added automatically at x = -inf with
            ratio 1.0, so do not pass a dose of 0. n = len(doses) + 1.
        responses: Response ratios relative to the control, same order as doses.
            Non-finite values are dropped, which lowers n for this curve.
        dose_unit: One of M, mM, uM, nM, pM, fM.
        fit_type: OLS (L-BFGS-B with Jacobian) or MLE (Nelder-Mead).
        control_fold_change: If true, the curve fold change is the model at the
            highest dose relative to the control instead of relative to the model
            at the lowest dose. Use this when compounds already regulate at the
            lowest dose, as the paper did for CTRP.
        fixed_slope: Fix the Hill slope instead of fitting it.
        fixed_front: Fix the front plateau instead of fitting it.
        fixed_back: Fix the back plateau instead of fitting it.
        optimized_dofs: Use the paper's recalibrated effective degrees of freedom.
            Setting this false falls back to the linear-model dfn = k-1, dfd = n-k,
            which the paper shows yields poorly calibrated p-values for this model.

    Returns:
        Curve parameters with standard errors, curve fold change, goodness of fit,
        the null-model intercept and RMSE, the recalibrated F-value and p-value,
        and caveats. A p-value alone does not make a curve relevant; pass this
        result to classify_dose_response_curve.
    """
    try:
        result = engine.fit_curve(
            doses,
            responses,
            dose_unit=dose_unit,
            fit_type=fit_type,
            control_fold_change=control_fold_change,
            fixed_slope=fixed_slope,
            fixed_front=fixed_front,
            fixed_back=fixed_back,
            optimized_dofs=optimized_dofs,
        )
    except EngineError as exc:
        return _err(exc)
    result["source"] = reference.citation()
    return result


@mcp.tool()
def classify_dose_response_curve(
    doses: list[float],
    responses: list[float],
    alpha: float = 0.05,
    fc_lim: float = 0.45,
    dose_unit: str = "nM",
    control_fold_change: bool = False,
    not_rmse_limit: float = 0.1,
    pec50_min: float | None = None,
    pec50_max: float | None = None,
    fit_type: str = "OLS",
) -> dict[str, Any]:
    """Fit a curve and classify it as up, down, not, or unclear via the relevance score.

    Runs the full single-curve pipeline: fit, recalibrated F-statistic, s0 from the
    two asymptotes, s0-adjusted F-value, relevance score, then the paper's four-way
    classification.

    The decision boundary is a hyperbola with two asymptotes: ``alpha`` for
    statistical relevance and ``fc_lim`` for biological relevance. Fix both on
    their own merits rather than tuning them to reach a target FDR.

    Args:
        doses: Non-zero doses; the control is added automatically.
        responses: Response ratios relative to the control.
        alpha: Alpha asymptote. The paper suggests 0.05. Dataset values it used:
            0.1 for Kinobeads, 0.05 for CTRP mode-of-action and decryptM.
        fc_lim: Absolute log2 fold-change asymptote. Assay-dependent, with no
            universal default. Dataset values: 0.5 Kinobeads, 0.3 CTRP, 0.45 decryptM.
            Setting 0.0 makes the relevance score equal -log10(p-value).
        dose_unit: One of M, mM, uM, nM, pM, fM.
        control_fold_change: Fold change relative to the control instead of the
            lowest dose.
        not_rmse_limit: Maximum null-model RMSE for a curve to be called a
            confident non-responder. Pipeline default 0.1.
        pec50_min: Optional lower bound on pEC50 for up/down calls.
        pec50_max: Optional upper bound on pEC50 for up/down calls.
        fit_type: OLS or MLE.

    Returns:
        The fit, the scoring (s0, s0-adjusted F, relevance score and its cutoff),
        the regulation class, and which criterion decided it. "unclear" is a
        deliberate category for curves that are neither confidently regulated nor
        confidently flat; it is not a failure.
    """
    try:
        fit = engine.fit_curve(
            doses,
            responses,
            dose_unit=dose_unit,
            fit_type=fit_type,
            control_fold_change=control_fold_change,
        )
        pec50_filter = None
        if pec50_min is not None or pec50_max is not None:
            pec50_filter = (
                pec50_min if pec50_min is not None else float("-inf"),
                pec50_max if pec50_max is not None else float("inf"),
            )
        classification = engine.classify_curve(
            fit,
            alpha=alpha,
            fc_lim=fc_lim,
            not_rmse_limit=not_rmse_limit,
            pec50_filter=pec50_filter,
        )
    except EngineError as exc:
        return _err(exc)

    return {
        "fit": fit,
        "classification": classification,
        "reporting_guidance": (
            "Report the pEC50 only for curves classified up or down. Report the relevance "
            "score as a ranking statistic, never as a p-value, unless fc_lim is 0."
        ),
        "source": reference.citation(),
    }


@mcp.tool()
def compute_relevance_score(
    f_value: float,
    curve_fold_change_log2: float,
    n_data_points: int,
    alpha: float = 0.05,
    fc_lim: float = 0.45,
    two_sided: bool = False,
) -> dict[str, Any]:
    """Convert a recalibrated F-value and fold change into s0 and a relevance score.

    Use this when you already have F-values and fold changes, for example from a
    CurveCurator ``curves.txt`` output, and want to rescore them under different
    asymptotes without refitting.

    s0 = |fc_lim| / sqrt(F.ppf(1 - alpha, dfn, dfd)); the SAM adjustment is
    F_adj = 1 / ((1/sqrt(F)) + s0/|fc|)^2; the score is -log10(F.sf(F_adj, dfn, dfd, loc, scale)).

    Args:
        f_value: Recalibrated F-value for the curve.
        curve_fold_change_log2: Curve fold change on a log2 scale.
        n_data_points: n including the control point. Missing values lower n and
            therefore change s0 for that curve.
        alpha: Alpha asymptote.
        fc_lim: Log2 fold-change asymptote.
        two_sided: The F-test is one-sided by default.

    Returns:
        s0, the s0-adjusted F-value, the relevance score, the cutoff -log10(alpha),
        whether the curve clears it, and whether the score may be read as a p-value.
    """
    try:
        result = engine.relevance_score(
            f_value,
            curve_fold_change_log2,
            n_data_points,
            alpha=alpha,
            fc_lim=fc_lim,
            two_sided=two_sided,
        )
    except EngineError as exc:
        return _err(exc)
    result["source"] = reference.citation()
    return result


@mcp.tool()
def map_decision_boundary(
    fold_changes: list[float],
    alpha: float = 0.05,
    fc_lim: float = 0.45,
    n_data_points: int = 9,
    two_sided: bool = False,
) -> dict[str, Any]:
    """Return the hyperbolic decision boundary as (fold change, p-value cutoff) pairs.

    Use this to draw the boundary on a volcano plot of p-value against curve fold
    change, or to see what significance a given effect size must reach.

    Args:
        fold_changes: Log2 fold changes at which to evaluate the boundary.
        alpha: Alpha asymptote.
        fc_lim: Log2 fold-change asymptote.
        n_data_points: n including the control, which sets the effective dofs.
        two_sided: One-sided by default.

    Returns:
        s0, the effective degrees of freedom, the recovered fold-change asymptotes
        as a round-trip check, and the boundary points. In relevance-score space the
        same boundary is a horizontal line at -log10(alpha).
    """
    try:
        result = engine.decision_boundary(
            fold_changes,
            alpha=alpha,
            fc_lim=fc_lim,
            n_data_points=n_data_points,
            two_sided=two_sided,
        )
    except EngineError as exc:
        return _err(exc)
    result["source"] = reference.citation()
    return result


@mcp.tool()
def estimate_target_decoy_fdr(
    curves: list[dict[str, Any]],
    doses: list[float],
    alpha: float = 0.05,
    fc_lim: float = 0.45,
    dose_unit: str = "nM",
    decoy_ratio: float = 1.0,
    random_seed: int | None = None,
) -> dict[str, Any]:
    """Estimate the FDR of a decision boundary by the paper's target-decoy procedure.

    Decoy curves are drawn by ``curve_curator``'s simulator from the empirical noise
    of the curves you supply, then pushed through the identical fit-and-classify
    path. FDR = (decoys above threshold + 1) / (targets above threshold + 1),
    scaled by the target:decoy ratio.

    Args:
        curves: One entry per curve, each ``{"name": str, "responses": [float, ...]}``,
            all sharing the same dose range.
        doses: The shared non-zero doses; the control is added automatically.
        alpha: Alpha asymptote.
        fc_lim: Log2 fold-change asymptote.
        dose_unit: One of M, mM, uM, nM, pM, fM.
        decoy_ratio: Decoys per target. Pipeline default 1.0.
        random_seed: Seed for reproducible decoy simulation.

    Returns:
        Global and boundary-filtered FDR, classification counts, the names of the
        regulated curves, and caveats. The estimate needs enough curves to describe
        the assay's variance; a handful gives an unstable number.
    """
    try:
        result = engine.estimate_fdr(
            curves,
            doses,
            dose_unit=dose_unit,
            alpha=alpha,
            fc_lim=fc_lim,
            decoy_ratio=decoy_ratio,
            random_seed=random_seed,
        )
    except EngineError as exc:
        return _err(exc)
    result["source"] = reference.citation()
    return result


@mcp.tool()
def generate_curvecurator_config(
    doses: list[float],
    dose_unit: str = "nM",
    preset: str | None = None,
    alpha: float | None = None,
    fc_lim: float | None = None,
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
    available_cores: int = 4,
) -> dict[str, Any]:
    """Generate a TOML parameter file for the CurveCurator command-line pipeline.

    Use this to move from single-curve exploration to a full run over a real
    dataset, which is where the target-decoy FDR and the interactive dashboard
    become meaningful.

    Args:
        doses: Non-zero doses; a control dose of 0.0 is prepended for you.
        dose_unit: One of M, mM, uM, nM, pM, fM.
        preset: Optional dataset preset carrying the asymptotes and preprocessing
            the paper used: "kinobeads", "ctrp", or "decryptm".
        alpha: Alpha asymptote; overrides the preset.
        fc_lim: Log2 fold-change asymptote; overrides the preset.
        input_file: Path to the input table, relative to the TOML file.
        output_prefix: Directory for curves, decoys, fdr and dashboard outputs.
        dataset_id: Meta id.
        description: Meta description.
        condition: The tested condition, e.g. the compound name.
        treatment_time: Treatment duration, e.g. "24 h".
        measurement_type: LFQ, TMT, DIA or OTHER; defaults from the preset.
        data_type: PEPTIDE, PROTEIN or OTHER; defaults from the preset.
        search_engine: MAXQUANT, DIANN, PD, MSFRAGGER or OTHER.
        control_fold_change: Fold change relative to the control; defaults from the preset.
        normalization: Median-centre log-normalised values.
        imputation: Impute missing values.
        available_cores: Cores for parallel fitting.

    Returns:
        The TOML text, the resulting n, the asymptotes in force, the preset notes,
        and the commands to run.
    """
    try:
        result = build_toml(
            doses,
            dose_unit=dose_unit,
            preset=preset,
            alpha=alpha,
            fc_lim=fc_lim,
            input_file=input_file,
            output_prefix=output_prefix,
            dataset_id=dataset_id,
            description=description,
            condition=condition,
            treatment_time=treatment_time,
            measurement_type=measurement_type,
            data_type=data_type,
            search_engine=search_engine,
            control_fold_change=control_fold_change,
            normalization=normalization,
            imputation=imputation,
            available_cores=available_cores,
        )
    except EngineError as exc:
        return _err(exc)
    result["available_presets"] = {k: v["description"] for k, v in PRESETS.items()}
    result["source"] = reference.citation()
    return result


@mcp.tool()
def describe_paper_dataset(dataset: str) -> dict[str, Any]:
    """Look up what the paper reports for one of its three reprocessed datasets.

    Args:
        dataset: "kinobeads" (drug-target binding), "ctrp" (cell viability), or
            "decryptm" (drug-PTM phosphoproteomics). Aliases such as "viability",
            "phosphoproteome" or "klaeger" also resolve.

    Returns:
        The reported asymptotes, preprocessing, curve counts, regulation
        proportions and named results, each as printed in the article. Where the
        article is internally inconsistent or where the PMC text extraction lost
        gene symbols, the payload says so instead of resolving it silently.
    """
    record = reference.get_dataset(dataset)
    if record is None:
        return {
            "found": False,
            "requested": dataset,
            "available": reference.dataset_names(),
            "source": reference.citation(),
        }
    return {"found": True, "dataset": record, "source": reference.citation()}


@mcp.resource("curvecurator://paper-summary")
def paper_summary() -> str:
    """Structured summary of the CurveCurator paper and this server's fidelity claims.

    Covers the statistical framework (models, recalibrated F-statistic, effective
    degrees of freedom, relevance score, classification, target-decoy FDR), the
    pipeline defaults, the three reprocessed datasets, the authors' stated
    limitations, and an explicit list of what this server does not reproduce.
    """
    return json.dumps(reference.load_reference(), indent=2)


@mcp.prompt()
def plan_dose_response_analysis(assay_description: str = "", n_curves: str = "") -> str:
    """Workflow for analysing a dose-response dataset with CurveCurator's statistics.

    Args:
        assay_description: The assay, readout and dose range, e.g. "phosphoproteome
            TMT, 9 doses 0.3 nM to 3 uM, hepatocyte model".
        n_curves: Roughly how many curves the dataset holds.
    """
    ref = reference.load_reference()
    defaults = ref["pipeline_defaults"]
    return f"""Plan a CurveCurator analysis for this dataset.

Assay: {assay_description or "(not specified - ask before choosing asymptotes)"}
Approximate number of curves: {n_curves or "(not specified)"}

Work through these steps.

1. Read the resource curvecurator://paper-summary first. It carries the
   statistical framework, the pipeline defaults and the three datasets the paper
   reprocessed, with their asymptotes.

2. Establish n. n counts the doses plus the control, because responses are ratios
   to the control and the control contributes one point at x = -inf with ratio 1.0.
   n must exceed 4. The effective degrees of freedom and therefore s0 depend on n,
   so curves with missing values are scored with their own s0.

3. Choose the two asymptotes deliberately and state the reasoning.
   - alpha (statistical relevance): the paper suggests {defaults['alpha']}.
   - fc_lim (biological relevance, log2): assay-dependent, no universal default.
     Anchor it to a comparable assay in the paper - {ref['datasets']['kinobeads']['fc_lim']}
     for Kinobeads binding, {ref['datasets']['ctrp']['moa_analysis']['fc_lim']} for CTRP viability,
     {ref['datasets']['decryptm']['fc_lim']} for decryptM phosphoproteomics - and to the
     measurement variance of the assay at hand.
   Do NOT pick the asymptotes by tuning them until the FDR hits a target. The
   authors argue against that explicitly: the relevance score is fixed at a given
   s0, so moving the boundary shifts both asymptotes together.

4. Fit and classify. Use classify_dose_response_curve per curve, or
   generate_curvecurator_config and the CurveCurator CLI for a whole dataset. Report
   each curve's class as one of up, down, not, unclear. Treat "unclear" as
   informative: it means the curve is neither confidently regulated nor confidently
   flat, and it exists so high-variance curves stay out of a negative set.

5. Quantify the error rate with estimate_target_decoy_fdr, or the --fdr flag of the
   CLI for a real dataset. Report the boundary-filtered FDR alongside the asymptotes
   that produced it. Say how many curves the decoy variance estimate rests on.

6. Report potency only where it is interpretable.
   - Quote a pEC50 only for a curve classified up or down. A potency estimate from a
     non-significant curve is not a measurement.
   - Never call the relevance score a p-value unless fc_lim is 0. With fc_lim > 0 it
     is a joint ranking of significance and effect size whose absolute value means
     nothing on its own.
   - Check whether the lowest dose sits on the front plateau. If not, the curve fold
     change is compressed and the most potent compounds turn into false negatives;
     say so, and consider control-relative fold change or a wider dose range.
   - If a curve has a large effect size but a poor p-value, consider that the
     response may be shaped by more than one event. The 4-parameter log-logistic
     model describes a single binding event and cannot fit such shapes.

7. Cite the pipeline as {ref['source']['authors']}. {ref['source']['journal']}
   {ref['source']['volume']}:{ref['source']['article_number']} ({ref['source']['year']}),
   doi:{ref['source']['doi']}, and state the curve_curator version you ran.
"""


def main() -> None:
    """Entry point for the stdio server."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
