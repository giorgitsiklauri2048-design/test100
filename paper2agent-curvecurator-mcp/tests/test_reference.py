"""Guards on the curated paper reference data.

These tests exist to fail the build if a citation drifts, a fabricated value is
introduced, or a claim about what the article reports stops matching the article.
"""

from __future__ import annotations

import json

import pytest

from curvecurator_mcp import reference

ALLOWED_PROVENANCE = {
    "paper_reported",
    "verified_against_source",
    "implementation_detail",
    "internal_discrepancy",
}


@pytest.fixture(scope="module")
def ref() -> dict:
    return reference.load_reference()


# --------------------------------------------------------------------------
# Citation
# --------------------------------------------------------------------------

def test_citation_matches_the_published_record(ref):
    source = ref["source"]
    assert source["doi"] == "10.1038/s41467-023-43696-z"
    assert source["pmid"] == "38036588"
    assert source["pmcid"] == "PMC10689459"
    assert source["journal"] == "Nature Communications"
    assert source["volume"] == "14"
    assert source["article_number"] == "7902"
    assert source["year"] == 2023


def test_all_four_authors_are_credited(ref):
    for surname in ("Bayer", "Gander", "Kuster", "The"):
        assert surname in ref["source"]["authors"]


def test_citation_helper_renders_a_complete_reference():
    cite = reference.citation()
    assert "10.1038/s41467-023-43696-z" in cite["citation"]
    assert "14:7902" in cite["citation"]
    assert "2023" in cite["citation"]


def test_manuscript_software_version_is_recorded(ref):
    assert ref["source"]["software_version_in_manuscript"] == "0.2.1"


# --------------------------------------------------------------------------
# The statistics this server must not get wrong
# --------------------------------------------------------------------------

def test_effective_dof_constants_are_recorded(ref):
    dofs = ref["statistical_framework"]["effective_degrees_of_freedom"]
    assert dofs["dfn"] == 5
    assert dofs["loc_default"] == 0.12
    assert dofs["scale_default"] == 1.0
    assert "(n - 2.5)" in dofs["dfd_expression"]


def test_f_statistic_scaling_factor_is_n_over_k_not_the_linear_form(ref):
    f_stat = ref["statistical_framework"]["recalibrated_f_statistic"]
    assert "(n / k)" in f_stat["expression"]
    assert "dfd / dfn" not in f_stat["expression"]


def test_relevance_score_is_documented_as_not_a_p_value(ref):
    score = ref["statistical_framework"]["relevance_score"]
    assert "NOT a valid p-value" in score["not_a_p_value"]
    assert "-log10(p-value)" in score["s0_zero_case"]


def test_four_classification_categories_are_recorded(ref):
    categories = ref["statistical_framework"]["classification"]["categories"]
    assert set(categories) == {"up", "down", "not", "unclear"}


def test_fdr_guidance_warns_against_tuning_to_a_target(ref):
    guidance = ref["statistical_framework"]["fdr"]["guidance"]
    assert "recommend against" in guidance


def test_control_point_convention_is_recorded(ref):
    control = ref["statistical_framework"]["control_point"]
    assert control["x"] == "-inf"
    assert control["y"] == 1.0


def test_h0_simulation_scale_matches_the_article(ref):
    assert ref["statistical_framework"]["h0_simulation"]["n_curves_per_n"] == 5_000_000


# --------------------------------------------------------------------------
# Pipeline defaults
# --------------------------------------------------------------------------

def test_pipeline_defaults_match_the_authors_parser(ref):
    defaults = ref["pipeline_defaults"]
    assert defaults["alpha"] == 0.05
    assert defaults["fc_lim"] == 0.45
    assert defaults["loc"] == 0.12
    assert defaults["not_rmse_limit"] == 0.1
    assert defaults["mtc_method"] == "sam"
    assert defaults["two_sided"] is False
    assert defaults["optimized_dofs"] is True


def test_engine_defaults_agree_with_the_recorded_pipeline_defaults(ref):
    from curvecurator_mcp import engine

    defaults = ref["pipeline_defaults"]
    assert engine.DEFAULT_ALPHA == defaults["alpha"]
    assert engine.DEFAULT_FC_LIM == defaults["fc_lim"]
    assert engine.DEFAULT_LOC == defaults["loc"]
    assert engine.DEFAULT_NOT_RMSE_LIMIT == defaults["not_rmse_limit"]


# --------------------------------------------------------------------------
# Datasets
# --------------------------------------------------------------------------

def test_three_datasets_are_present(ref):
    assert set(ref["datasets"]) == {"kinobeads", "ctrp", "decryptm"}


def test_dataset_asymptotes_match_the_article(ref):
    assert ref["datasets"]["kinobeads"]["alpha"] == 0.1
    assert ref["datasets"]["kinobeads"]["fc_lim"] == 0.5
    assert ref["datasets"]["ctrp"]["moa_analysis"]["alpha"] == 0.05
    assert ref["datasets"]["ctrp"]["moa_analysis"]["fc_lim"] == 0.3
    assert ref["datasets"]["decryptm"]["alpha"] == 0.05
    assert ref["datasets"]["decryptm"]["fc_lim"] == 0.45


def test_kinobeads_reported_counts(ref):
    kb = ref["datasets"]["kinobeads"]
    assert kb["n_curves"] == 54223
    assert kb["pct_down_regulated"] == 9
    assert kb["concordance_with_manual_annotation_pct"] == 97
    assert kb["n_kinases_assayed"] == 247
    assert kb["afatinib_significant_interactions"] == 9
    assert "PXD005336" in kb["repository"]


def test_ctrp_internal_discrepancy_is_flagged_not_silently_resolved(ref):
    """Methods say 373,324 combinations; Results say 379,324 curves."""
    ctrp = ref["datasets"]["ctrp"]
    assert "373,324" in ctrp["matrix_methods"]
    assert ctrp["n_curves_results_section"] == 379324
    assert "373,324" in ctrp["internal_discrepancy"]
    assert "379,324" in ctrp["internal_discrepancy"]
    assert ctrp["internal_discrepancy_provenance"] == "internal_discrepancy"


def test_ctrp_decision_boundaries_match_the_article(ref):
    boundaries = {
        b["boundary"]: (b["alpha"], b["fc_lim"], b["reported_fdr_pct"])
        for b in ref["datasets"]["ctrp"]["decision_boundaries_analysis"]
    }
    assert boundaries["A"] == (0.01, 0.0, 1.4)
    assert boundaries["B"] == (0.1, 0.0, 11.8)
    assert boundaries["C"] == (0.01, 0.3, 0.005)
    assert boundaries["D"] == (0.1, 0.21, 0.1)


def test_ctrp_boundaries_show_fold_change_asymptote_lowers_fdr(ref):
    """C beats A and D beats B at equal alpha, which is the paper's argument."""
    boundaries = {
        b["boundary"]: b for b in ref["datasets"]["ctrp"]["decision_boundaries_analysis"]
    }
    assert boundaries["C"]["reported_fdr_pct"] < boundaries["A"]["reported_fdr_pct"]
    assert boundaries["D"]["reported_fdr_pct"] < boundaries["B"]["reported_fdr_pct"]


def test_decryptm_a431_counts(ref):
    a431 = ref["datasets"]["decryptm"]["a431_afatinib"]
    assert a431["n_curves"] == 19596
    assert (a431["pct_down"], a431["pct_up"], a431["pct_not"]) == (5, 1, 46)


def test_decryptm_records_pride_identifier(ref):
    assert "PXD037285" in ref["datasets"]["decryptm"]["repository"]


def test_dataset_lookup_resolves_aliases():
    assert reference.get_dataset("viability")["label"].startswith("CTRP")
    assert reference.get_dataset("phosphoproteome")["label"].startswith("decryptM")
    assert reference.get_dataset("Klaeger")["label"].startswith("Kinobeads")
    assert reference.get_dataset("KINOBEADS") is not None


def test_dataset_lookup_returns_none_rather_than_guessing():
    assert reference.get_dataset("pesticide screen") is None


def test_dataset_names_are_sorted():
    assert reference.dataset_names() == ["ctrp", "decryptm", "kinobeads"]


# --------------------------------------------------------------------------
# Honesty guards
# --------------------------------------------------------------------------

def test_no_gene_symbols_are_invented_for_the_moa_figures(ref):
    """The PMC text extraction dropped these symbols; they must not be guessed."""
    note = ref["datasets"]["decryptm"]["afatinib_moa_synthesis"]["site_identity_note"]
    assert "not reproduced here" in note
    assert "Fig. 4" in note
    blob = json.dumps(ref)
    for guessable in ("CRKL", "SHC1", "MAPK1", "MAPK14", "MAP2K1", "pY207", "pY627"):
        assert guessable not in blob


def test_equations_are_sourced_from_code_not_transcribed(ref):
    dofs = ref["statistical_framework"]["effective_degrees_of_freedom"]
    assert "taken from the authors' code" in dofs["note"]
    assert "rendered as images" in ref["not_reproduced_here"]["numbered_equations"]


def test_implementation_binding_names_the_verified_functions(ref):
    binding = ref["implementation_binding"]
    verified = " ".join(binding["verified_identical_between_0_2_1_and_0_6_0"])
    assert "get_dofs" in verified
    assert "get_s0" in verified
    assert "sam_correction" in verified
    assert "relevance score" in verified
    assert binding["manuscript_version"] == "0.2.1"
    assert "diffed" in binding["verification_method"]


def test_changed_functions_are_excluded_from_fidelity_claims(ref):
    changed = " ".join(
        ref["implementation_binding"]["changed_after_0_2_1_not_used_for_manuscript_fidelity_claims"]
    )
    assert "R2" in changed


def test_raw_datasets_are_not_claimed_to_be_bundled(ref):
    assert "are not bundled" in ref["not_reproduced_here"]["raw_datasets"]
    assert "PXD005336" in ref["not_reproduced_here"]["raw_datasets"]


def test_stated_limitations_cover_the_single_binding_event_assumption(ref):
    text = " ".join(item["limitation"] for item in ref["stated_limitations"])
    assert "single drug-target binding event" in text
    assert "front plateau" in text


def test_every_provenance_tag_is_from_the_allowed_vocabulary(ref):
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "provenance" or key.endswith("_provenance"):
                    assert value in ALLOWED_PROVENANCE, f"{key} = {value}"
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(ref)


def test_no_benchmark_dose_vocabulary_leaks_in(ref):
    """CurveCurator reports pEC50 and a relevance score, not BMD/BMC/BMR quantities."""
    blob = json.dumps(ref).upper()
    for term in ("BMDEXPRESS", "BENCHMARK DOSE", "BENCHMARK CONCENTRATION", "1.349"):
        assert term not in blob


# --------------------------------------------------------------------------
# Supporting citations, verified against PubMed records
# --------------------------------------------------------------------------

def test_kinobeads_original_study_uses_the_published_title(ref):
    """PMID 29191878: the title says "drugs"; the CurveCurator text says "inhibitors"."""
    kb = ref["datasets"]["kinobeads"]
    assert "clinical kinase drugs" in kb["original_study"]
    assert "10.1126/science.aan4368" in kb["original_study"]
    assert "inhibitors" in kb["original_study_note"]


def test_decryptm_original_study_citation_is_complete(ref):
    """PMID 36926954."""
    study = ref["datasets"]["decryptm"]["original_study"]
    assert "10.1126/science.ade3925" in study
    assert "380:93-101" in study


def test_sam_origin_cites_tusher_with_a_doi(ref):
    """PMID 11309499."""
    origin = ref["statistical_framework"]["relevance_score"]["origin"]
    assert "Tusher" in origin
    assert "10.1073/pnas.091062498" in origin
    assert "98:5116-5121" in origin


def test_reference_data_has_a_single_source_of_truth():
    """The JSON lives only inside the package, so no second copy can drift."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    copies = sorted(p.relative_to(root).as_posix() for p in root.rglob("paper_reference.json"))
    assert copies == ["src/curvecurator_mcp/data/paper_reference.json"]
