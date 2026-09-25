"""MCP server exposing the Franzosa et al. (2021) HepaRG toxicogenomic screen.

Source: Franzosa JA, Bonzo JA, Jack J, Baker NC, Kothiya P, Witek RP, Hurban P,
Siferd S, Hester S, Shah I, Ferguson SS, Houck KA, Wambaugh JF.
"High-throughput toxicogenomic screening of chemicals in the environment using
metabolically competent hepatic cell cultures."
npj Systems Biology and Applications 7:7 (2021). doi:10.1038/s41540-020-00166-2
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from .curve_fit import CurveFitError, fit_concentration_response as _fit
from .data_access import find_chemical, is_casrn, known_chemicals, load_data
from .receptors import analyze_pathway_enrichment as _enrich

mcp = MCPServer("franzosa-heparg-toxicogenomics")

_SOURCE_DOI = "10.1038/s41540-020-00166-2"


def _cite() -> dict[str, Any]:
    source = load_data()["source"]
    return {
        "doi": source["doi"],
        "citation": (
            f"{source['authors']}. {source['title']}. "
            f"{source['journal']} {source['volume']}:{source['article_number']} ({source['year']}). "
            f"doi:{source['doi']}"
        ),
    }


@mcp.tool()
def query_chemical_profile(chemical_name_or_cas: str) -> dict[str, Any]:
    """Look up a chemical's reported receptor activation profile in the HepaRG screen.

    Resolves by chemical name, synonym, or CAS RN against the reference chemicals
    the article names in text. Per-chemical AC50 and cytotoxicity values are NOT
    published in the article text -- they are distributed in the external
    LTEA Level 5 curve-fit archive -- so those fields return null with an explicit
    ``not_reported`` provenance rather than a fabricated number.

    Args:
        chemical_name_or_cas: e.g. "rifampicin", "omeprazole", "50-29-3", "WY-14643".

    Returns:
        Receptor activation profile, canonical marker transcript, tested
        concentrations, and provenance for every field.
    """
    if not isinstance(chemical_name_or_cas, str) or not chemical_name_or_cas.strip():
        raise ValueError("chemical_name_or_cas must be a non-empty string")

    record = find_chemical(chemical_name_or_cas)
    data = load_data()

    if record is None:
        return {
            "query": chemical_name_or_cas,
            "query_looks_like_casrn": is_casrn(chemical_name_or_cas),
            "found": False,
            "reason": (
                "Not among the reference chemicals named in the article text. The screen "
                f"covered {data['screening_summary']['chemicals_tested']} ToxCast library "
                "chemicals, but the article text names only the reference set; "
                "per-chemical results for the remainder are in the external "
                "LTEA Level 5 curve-fit archive, which this package does not bundle."
            ),
            "resolvable_chemicals": known_chemicals(),
            "external_data_files": data["external_data_files"],
            "source": _cite(),
        }

    receptors = data["receptors"]["modeled"]
    activation = [
        {
            "receptor": key,
            "full_name": receptors[key]["full_name"],
            "uniprot": receptors[key]["uniprot"],
            "canonical_markers_reported_in_text": receptors[key]["canonical_markers_reported"],
        }
        for key in record["activates_receptors"]
    ]

    concentrations = {
        key: record[key]
        for key in (
            "max_concentration_reference_plate_uM",
            "max_concentration_library_uM",
            "low_concentration_imaged_uM",
            "high_concentration_imaged_uM",
        )
        if key in record
    }

    return {
        "query": chemical_name_or_cas,
        "found": True,
        "name": record["name"],
        "synonyms": record.get("synonyms", []),
        "casrn": record.get("casrn"),
        "casrn_provenance": record.get("casrn_provenance"),
        "role_in_study": record["role"],
        "receptor_activation": activation,
        "canonical_marker_reported": record.get("canonical_marker_reported"),
        "additional_markers_reported": record.get("additional_markers_reported", []),
        "reported_notes": record.get("reported_notes"),
        "tested_concentrations_uM": concentrations or None,
        "cyp3a4_fold_induction": record.get("cyp3a4_fold_induction"),
        "cytotoxicity_pct_of_total_lysis": record.get("cytotoxicity_pct_of_total_lysis"),
        "potency": {
            "ac50_uM": record["ac50_uM"],
            "provenance": record["ac50_provenance"],
            "note": (
                "AC50 (tcpl modl_ga) is the study's potency metric. It is not tabulated "
                "in the article text; retrieve it from LTEA_Level5_20191119.zip or the "
                "EPA CompTox Chemicals Dashboard."
            ),
        },
        "cytotoxicity": {
            "ac50_uM": record["cytotoxicity_ac50_uM"],
            "provenance": record["cytotoxicity_provenance"],
            "assay": data["assay"]["cytotoxicity_assay"],
            "hit_criterion": data["analysis_pipeline"]["cytotoxicity_hit_criterion"],
        },
        "benchmark_dose_note": data["analysis_pipeline"]["benchmark_dose_note"],
        "assay_context": {
            "cell_model": data["assay"]["cell_model"],
            "vehicle_control": data["assay"]["vehicle_control"],
            "design": data["assay"]["concentration_response_design"],
            "platform": data["assay"]["transcriptomic_platform"],
        },
        "source": _cite(),
    }


@mcp.tool()
def fit_concentration_response(
    concentrations: list[float],
    responses: list[float],
    fold_change_cutoff: float = 1.2,
    bmad: float | None = None,
    bmad_multiplier: float = 3.0,
) -> dict[str, Any]:
    """Fit a transcriptomic concentration-response curve the way the study did.

    Fits constant, Hill, and gain-loss models under a Student's t error model,
    selects the winner by AIC, and reports AC50 (tcpl ``modl_ga``) as potency and
    the modelled top (``modl_tp``) as efficacy -- the study's actual pipeline.

    No benchmark concentration (BMC) is produced: the source study performs no
    BMD/BMC modelling and does not use a benchmark response of 1.349 SD. That
    convention belongs to the BMDExpress / NTP approach (Thomas et al.,
    Toxicol Sci 2007; NTP Research Report 5, 2018), which is a different pipeline.

    Args:
        concentrations: Tested concentrations in uM, strictly positive, >= 4 points.
        responses: Matched log2 fold-change values (tcpl rval / delta-delta-Ct vs
            the plate-wise median of the DMSO neutral controls).
        fold_change_cutoff: Linear fold-change hit threshold; the study used 1.2.
        bmad: Plate-wide baseline median absolute deviation. Omit only if unavailable;
            the single-curve fallback is flagged as low confidence in the result.
        bmad_multiplier: 3.0 for transcriptomic endpoints, 10.0 for the LDH endpoint.

    Returns:
        Winning model, AC50, efficacy, both hit-criterion components, and the AIC table.
    """
    try:
        return _fit(
            concentrations=concentrations,
            responses=responses,
            fold_change_cutoff=fold_change_cutoff,
            bmad=bmad,
            bmad_multiplier=bmad_multiplier,
        ) | {"source": _cite()}
    except CurveFitError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def analyze_pathway_enrichment(significant_genes: list[str]) -> list[dict[str, Any]]:
    """Map differentially expressed transcripts onto the study's receptor sets.

    Covers the six receptors modelled by the study's Bayesian network -- AhR, CAR,
    PXR, FXR, AR, and PPARalpha -- plus NFE2L2/Nrf2, which is present on the panel
    as a replacement probe but is explicitly flagged as NOT modelled by the network
    and NOT supported by any oxidative-stress signature in the source study.

    Args:
        significant_genes: HGNC symbols of differentially expressed transcripts.

    Returns:
        One record per receptor with matched markers, hypergeometric p-value,
        BH-adjusted q-value, and the statistical-power caveats that apply.
    """
    return _enrich(significant_genes)


@mcp.tool()
def compare_metabolic_competence(
    cell_type: str = "HepaRG",
    reference: str = "primary_human_hepatocytes",
) -> dict[str, Any]:
    """Compare hepatic metabolic competence between two cell models as the study reports it.

    The article characterises CYP450 competence through reference-activator induction
    and functional evidence. It publishes no table of baseline CYP450 expression
    ratios between HepaRG and primary human hepatocytes, so ratio fields return null
    with ``not_reported`` provenance rather than invented numbers. The one quantitative
    comparison the article does make is overall metabolic activity: HepaRG under the
    study's 0.5% DMSO Zone-2 induction medium was "likely ~10% of human liver and
    suspensions of primary human hepatocytes".

    Args:
        cell_type: "HepaRG", "primary_human_hepatocytes", or "HepG2".
        reference: Comparator model, same vocabulary.

    Returns:
        Side-by-side model characteristics, per-CYP450 evidence, and reported limitations.
    """
    data = load_data()
    models = data["metabolic_competence"]["cell_models"]

    aliases = {
        "heparg": "HepaRG",
        "primary_human_hepatocytes": "primary_human_hepatocytes",
        "primary human hepatocytes": "primary_human_hepatocytes",
        "phh": "primary_human_hepatocytes",
        "hepg2": "HepG2",
    }

    def resolve(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
        key = aliases.get(value.strip().lower())
        if key is None:
            raise ValueError(
                f"unknown {label} {value!r}; supported models: {', '.join(sorted(models))}"
            )
        return key

    test_key = resolve(cell_type, "cell_type")
    ref_key = resolve(reference, "reference")

    test = models[test_key]
    ref = models[ref_key]

    test_activity = test["relative_metabolic_activity_vs_human_liver"]
    ref_activity = ref["relative_metabolic_activity_vs_human_liver"]
    if test_activity is not None and ref_activity:
        ratio: float | None = round(test_activity / ref_activity, 4)
        ratio_note = (
            "Ratio of overall metabolic activity relative to human liver, derived from "
            "the article's approximate statements. It is a whole-culture figure, not a "
            "per-enzyme expression ratio."
        )
    else:
        ratio = None
        ratio_note = (
            f"Not computable: the article reports no quantitative metabolic activity "
            f"figure for {'HepG2' if test_activity is None else ref_key}."
        )

    return {
        "cell_type": test_key,
        "reference": ref_key,
        "comparison": {
            "relative_metabolic_activity_ratio": ratio,
            "ratio_note": ratio_note,
            "cell_type_activity_vs_human_liver": test_activity,
            "reference_activity_vs_human_liver": ref_activity,
        },
        "cell_type_profile": test,
        "reference_profile": ref,
        "cyp450_evidence": data["metabolic_competence"]["cyp450_evidence"],
        "functional_evidence": data["metabolic_competence"]["functional_evidence"],
        "reported_limitations": data["metabolic_competence"]["reported_limitations"],
        "source": _cite(),
    }


@mcp.resource("toxicogenomics://paper-summary")
def paper_summary() -> str:
    """Structured summary of the study design, cell model, exposure parameters, and context."""
    data = load_data()
    return json.dumps(
        {
            "source": data["source"],
            "study_design": {
                "objective": (
                    "Screen the ToxCast chemical library in a metabolically competent "
                    "human hepatic culture and infer molecular initiating events "
                    "(nuclear receptor activation) from concentration-response "
                    "transcriptomics, addressing the limitation that most ToxCast assays "
                    "use cancer cell lines lacking integrated physiological function."
                ),
                "assay": data["assay"],
                "analysis_pipeline": data["analysis_pipeline"],
                "network_model": data["network_model"],
            },
            "receptors": data["receptors"],
            "screening_summary": data["screening_summary"],
            "metabolic_competence": data["metabolic_competence"],
            "hazard_screening_context": {
                "program": "U.S. EPA ToxCast / Tox21 high-throughput screening",
                "purpose": (
                    "Prioritise which of the many untested chemicals in commerce and the "
                    "environment should be tested first for public health risk assessment."
                ),
                "assay_suite": data["assay"]["assay_suite_name"],
                "predecessor": (
                    "The initial ToxCast phase used primary human hepatocytes for "
                    "14 transcripts across 309 chemicals (Rotroff et al.); donor "
                    "variability and finite supply motivated the move to HepaRG."
                ),
                "cross_assay_validation": data["screening_summary"]["ar_cross_assay_validation"],
                "data_access": data["external_data_files"],
            },
            "scope_disclaimers": [
                data["analysis_pipeline"]["benchmark_dose_note"],
                "The transcriptomic platform is a 93-transcript TaqMan qRT-PCR panel on "
                "Fluidigm 96.96 dynamic arrays. This study did NOT use TempO-Seq and did "
                "not use a 500-gene liver panel.",
                data["receptors"]["not_modeled_annotation"]["NFE2L2"]["status_note"],
                data["source"]["citation_note"],
            ],
            "provenance_policy": data["provenance_policy"],
        },
        indent=2,
    )


@mcp.prompt()
def screen_novel_chemical(
    chemical_name: str = "",
    transcript: str = "",
) -> str:
    """Guided workflow for screening custom transcriptomic dose-response data."""
    data = load_data()
    pipeline = data["analysis_pipeline"]
    subject = chemical_name.strip() or "the candidate chemical"
    target = transcript.strip() or "each measured transcript"

    return f"""Screen {subject} against the Franzosa et al. (2021) HepaRG reference frame.

Source: {data['source']['journal']} {data['source']['volume']}:{data['source']['article_number']} ({data['source']['year']}), doi:{data['source']['doi']}

Work through these steps in order. Do not skip step 0, and do not substitute a
remembered value for a tool call at any step.

STEP 0 - Establish the reference frame.
  Read the resource toxicogenomics://paper-summary. Confirm the assay context your
  data must be comparable to before interpreting anything:
    - Cell model: {data['assay']['cell_model']}
    - Vehicle: {data['assay']['vehicle_control']}
    - Platform: {data['assay']['transcriptomic_platform']} ({data['assay']['transcripts_measured']} transcripts)
    - Design: {data['assay']['concentration_response_design']}
  If the input data came from a different cell model, exposure duration, vehicle
  concentration, or transcriptomic platform, say so explicitly and treat every
  downstream potency comparison as cross-platform and semi-quantitative.

STEP 1 - Check whether the chemical is already characterised.
  Call query_chemical_profile("{subject}").
  If found, record its reported receptor activations and use them as the prior
  hypothesis for step 3. If not found, state plainly that the chemical is not among
  the reference set named in the article text and proceed without a prior.

STEP 2 - Fit the concentration-response data.
  For {target}, call fit_concentration_response with:
    - concentrations in uM (strictly positive)
    - responses as log2 fold-change versus the plate-wise median of the DMSO controls
    - bmad set to your PLATE-WIDE baseline median absolute deviation if you have one
  Then report, per transcript:
    - the winning model and why it won (AIC)
    - AC50 in uM, or state that no systematic relationship was found
    - efficacy (modl_tp) in log2 fold-change
    - the hit call, naming which criterion fired: {pipeline['transcriptomic_hit_criterion']}
  If the winning model is gain-loss, flag the high-concentration fall-off: the study
  interprets loss of signal at high concentration as cytotoxicity, not as
  receptor-mediated repression. Say whether an LDH or equivalent cytotoxicity curve
  is available to confirm it; if it is, refit that endpoint with bmad_multiplier=10.0.

STEP 3 - Map hit transcripts to initiating events.
  Pass the hit transcripts to analyze_pathway_enrichment.
  Read the caveats field before you interpret the q-values. The marker sets contain
  only the canonical genes named in the article text, so they are small and
  underpowered, and the study's own inference is a Bayesian posterior over receptor
  activation rather than an enrichment test. Report matched markers and direction
  alongside any q-value, never a q-value alone. If NFE2L2 matches, state that Nrf2
  is not one of the six receptors the study modelled.

STEP 4 - Qualify the metabolic context.
  Call compare_metabolic_competence to establish what the HepaRG frame can and
  cannot resolve. State the ~10% of human liver metabolic activity figure and its
  consequence: potency for chemicals requiring extensive bioactivation may be
  underestimated relative to primary human hepatocytes.

STEP 5 - Report.
  Give a per-transcript table (winning model, AC50 uM, efficacy, hit call, criterion
  fired), then the inferred receptor(s) with the evidence for each, then the
  limitations. Observe these constraints without exception:
    - Report potency as AC50. Do NOT report a BMC or BMD, and do NOT apply a
      benchmark response of 1.349 SD. {pipeline['benchmark_dose_note']}
    - Never present a value with provenance "synthetic" or "not_reported" as a
      measured result of the study.
    - Where the study reports no value, say "not reported in the source article"
      and name where the value would live: {data['external_data_files']['level_5_curve_fits']}.
"""


def main() -> None:
    """Run the server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
