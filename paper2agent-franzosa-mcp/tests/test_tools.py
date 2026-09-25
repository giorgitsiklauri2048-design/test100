"""Tests for the four MCP tools, the resource, and the prompt."""

from __future__ import annotations

import asyncio
import json

import pytest

from franzosa_mcp import server
from franzosa_mcp.server import (
    analyze_pathway_enrichment,
    compare_metabolic_competence,
    mcp,
    paper_summary,
    query_chemical_profile,
    screen_novel_chemical,
)

SOURCE_DOI = "10.1038/s41540-020-00166-2"


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

def test_all_four_tools_are_registered() -> None:
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert names == {
        "query_chemical_profile",
        "fit_concentration_response",
        "analyze_pathway_enrichment",
        "compare_metabolic_competence",
    }


def test_resource_and_prompt_are_registered() -> None:
    uris = {str(resource.uri) for resource in asyncio.run(mcp.list_resources())}
    assert "toxicogenomics://paper-summary" in uris
    prompts = {prompt.name for prompt in asyncio.run(mcp.list_prompts())}
    assert "screen_novel_chemical" in prompts


def test_tools_expose_argument_schemas() -> None:
    schemas = {tool.name: tool.input_schema for tool in asyncio.run(mcp.list_tools())}
    assert "chemical_name_or_cas" in schemas["query_chemical_profile"]["properties"]
    assert "concentrations" in schemas["fit_concentration_response"]["properties"]
    assert "significant_genes" in schemas["analyze_pathway_enrichment"]["properties"]
    assert "cell_type" in schemas["compare_metabolic_competence"]["properties"]


# --------------------------------------------------------------------------
# query_chemical_profile
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query,expected_name,expected_receptor",
    [
        ("rifampicin", "Rifampicin", "PXR"),
        ("rifampin", "Rifampicin", "PXR"),
        ("omeprazole", "Omeprazole", "AhR"),
        ("73590-58-6", "Omeprazole", "AhR"),
        ("WY-14643", "Pirinixic acid", "PPARA"),
        ("CHENODEOXYCHOLIC ACID", "Chenodeoxycholic acid", "FXR"),
        ("17-methyltestosterone", "17-Methyltestosterone", "AR"),
    ],
)
def test_chemical_lookup_resolves_by_name_synonym_and_cas(
    query: str, expected_name: str, expected_receptor: str
) -> None:
    result = query_chemical_profile(query)
    assert result["found"] is True
    assert result["name"] == expected_name
    assert expected_receptor in {r["receptor"] for r in result["receptor_activation"]}
    assert result["source"]["doi"] == SOURCE_DOI


def test_ddt_isomers_do_not_collide() -> None:
    para = query_chemical_profile("p,p'-DDT")
    ortho = query_chemical_profile("o,p'-DDT")
    assert para["name"] == "p,p'-DDT"
    assert ortho["name"] == "o,p'-DDT"
    assert para["casrn"] != ortho["casrn"]
    # The two isomers have genuinely different reported receptor profiles.
    assert {r["receptor"] for r in para["receptor_activation"]} == {"CAR", "PXR"}
    assert {r["receptor"] for r in ortho["receptor_activation"]} == {"PXR"}


def test_unknown_chemical_reports_not_found_without_inventing_data() -> None:
    result = query_chemical_profile("chlorpyrifos")
    assert result["found"] is False
    assert "resolvable_chemicals" in result
    assert "LTEA_Level5" in result["external_data_files"]["level_5_curve_fits"]
    assert "potency" not in result


def test_potency_is_null_with_not_reported_provenance() -> None:
    result = query_chemical_profile("rifampicin")
    assert result["potency"]["ac50_uM"] is None
    assert result["potency"]["provenance"] == "not_reported"
    assert result["cytotoxicity"]["ac50_uM"] is None
    assert result["cytotoxicity"]["provenance"] == "not_reported"


def test_casrn_is_flagged_as_external_identifier() -> None:
    result = query_chemical_profile("methoxychlor")
    assert result["casrn"] == "72-43-5"
    assert result["casrn_provenance"] == "external_identifier"


def test_paper_reported_quantities_are_preserved() -> None:
    omeprazole = query_chemical_profile("omeprazole")
    assert omeprazole["cyp3a4_fold_induction"] == 4.2

    phenobarbital = query_chemical_profile("phenobarbital")
    assert phenobarbital["tested_concentrations_uM"]["max_concentration_reference_plate_uM"] == 500
    assert phenobarbital["tested_concentrations_uM"]["max_concentration_library_uM"] == 100

    aflatoxin = query_chemical_profile("aflatoxin B1")
    assert aflatoxin["cytotoxicity_pct_of_total_lysis"] == 12
    assert aflatoxin["receptor_activation"] == []


@pytest.mark.parametrize("bad", ["", "   "])
def test_blank_chemical_query_raises(bad: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        query_chemical_profile(bad)


# --------------------------------------------------------------------------
# analyze_pathway_enrichment
# --------------------------------------------------------------------------

def test_enrichment_matches_canonical_markers_to_receptors() -> None:
    results = analyze_pathway_enrichment(["CYP1A1", "CYP1A2", "CYP3A4"])
    by_id = {r["pathway_id"]: r for r in results}
    assert by_id["AhR"]["matched_genes"] == ["CYP1A1", "CYP1A2"]
    assert by_id["AhR"]["n_matched"] == 2
    assert by_id["PXR"]["matched_genes"] == ["CYP3A4"]
    assert by_id["CAR"]["n_matched"] == 0


def test_all_six_modeled_receptors_plus_nrf2_are_returned() -> None:
    results = analyze_pathway_enrichment(["CYP2B6"])
    ids = {r["pathway_id"] for r in results}
    assert ids == {"AhR", "CAR", "PXR", "FXR", "AR", "PPARA", "NFE2L2"}

    modeled = {r["pathway_id"] for r in results if r["modeled_by_bayesian_network"]}
    assert modeled == {"AhR", "CAR", "PXR", "FXR", "AR", "PPARA"}


def test_nrf2_is_flagged_as_outside_the_modeled_network() -> None:
    nrf2 = next(r for r in analyze_pathway_enrichment(["NFE2L2"]) if r["pathway_id"] == "NFE2L2")
    assert nrf2["modeled_by_bayesian_network"] is False
    assert nrf2["n_matched"] == 1
    assert "NOT one of the six receptors" in nrf2["status_note"]


def test_enrichment_is_bh_corrected_and_sorted() -> None:
    results = analyze_pathway_enrichment(["CYP1A1", "CYP1A2"])
    qs = [r["q_value_bh"] for r in results if r["q_value_bh"] is not None]
    assert qs == sorted(qs)
    for record in results:
        if record["p_value"] is not None:
            assert record["p_value"] <= record["q_value_bh"] + 1e-12
            assert 0.0 <= record["q_value_bh"] <= 1.0


def test_universe_is_the_93_transcript_panel() -> None:
    record = analyze_pathway_enrichment(["CYP3A4"])[0]
    assert record["universe"]["size"] == 93
    assert "93-transcript" in record["universe"]["description"]


def test_ar_has_no_marker_and_no_p_value() -> None:
    ar = next(r for r in analyze_pathway_enrichment(["CYP3A4"]) if r["pathway_id"] == "AR")
    assert ar["marker_genes_reported_in_text"] == []
    assert ar["p_value"] is None
    assert ar["q_value_bh"] is None
    assert ar["significant_at_q_0_05"] is False


def test_caveats_are_always_attached() -> None:
    for record in analyze_pathway_enrichment(["CYP3A4"]):
        assert record["caveats"]
        assert any("Bayesian posterior" in c for c in record["caveats"])
        assert record["source_doi"] == SOURCE_DOI


def test_offpanel_and_replaced_probes_are_flagged() -> None:
    results = analyze_pathway_enrichment(["ALB", "KLK3"])
    caveats = " ".join(results[0]["caveats"])
    assert "ALB" in caveats and "could not be verified" in caveats
    assert "KLK3" in caveats and "non-detects" in caveats


def test_gene_symbols_are_normalized_and_deduplicated() -> None:
    results = analyze_pathway_enrichment([" cyp3a4 ", "CYP3A4", "Cyp3a4"])
    pxr = next(r for r in results if r["pathway_id"] == "PXR")
    assert pxr["matched_genes"] == ["CYP3A4"]
    assert pxr["universe"]["query_size"] == 1


def test_empty_gene_list_is_handled() -> None:
    results = analyze_pathway_enrichment([])
    assert len(results) == 7
    assert all(r["n_matched"] == 0 for r in results)
    assert all(r["p_value"] is None for r in results)


@pytest.mark.parametrize("bad", ["CYP3A4", 42, None])
def test_non_list_gene_input_raises(bad) -> None:
    with pytest.raises(TypeError):
        analyze_pathway_enrichment(bad)


def test_non_string_gene_symbol_raises() -> None:
    with pytest.raises(TypeError, match="must be strings"):
        analyze_pathway_enrichment(["CYP3A4", 7])


# --------------------------------------------------------------------------
# compare_metabolic_competence
# --------------------------------------------------------------------------

def test_default_comparison_reports_the_ten_percent_figure() -> None:
    result = compare_metabolic_competence()
    assert result["cell_type"] == "HepaRG"
    assert result["reference"] == "primary_human_hepatocytes"
    assert result["comparison"]["relative_metabolic_activity_ratio"] == pytest.approx(0.10)
    assert "whole-culture" in result["comparison"]["ratio_note"]


def test_cyp450_baseline_ratios_are_not_invented() -> None:
    evidence = compare_metabolic_competence()["cyp450_evidence"]
    for cyp in ("CYP1A2", "CYP2B6", "CYP3A4"):
        assert evidence[cyp]["baseline_ratio_vs_PHH"] is None
        assert evidence[cyp]["provenance"] == "not_reported"
        assert evidence[cyp]["evidence"]
    assert evidence["CYP3A4"]["omeprazole_fold_induction"] == 4.2
    assert evidence["CYP2B6"]["screening_hit_count_up"] == 352


def test_cyp450_receptor_assignments_match_the_paper() -> None:
    evidence = compare_metabolic_competence()["cyp450_evidence"]
    assert evidence["CYP1A2"]["receptor"] == "AhR"
    assert evidence["CYP2B6"]["receptor"] == "CAR"
    assert evidence["CYP3A4"]["receptor"] == "PXR"


def test_hepg2_comparison_is_not_computable() -> None:
    result = compare_metabolic_competence(cell_type="HepG2")
    assert result["comparison"]["relative_metabolic_activity_ratio"] is None
    assert "Not computable" in result["comparison"]["ratio_note"]
    assert result["cell_type_profile"]["xenobiotic_receptor_repertoire"].startswith("incomplete")


def test_model_aliases_resolve() -> None:
    assert compare_metabolic_competence("heparg", "phh")["reference"] == "primary_human_hepatocytes"
    assert compare_metabolic_competence("HepaRG", "primary human hepatocytes")["reference"] == (
        "primary_human_hepatocytes"
    )


def test_limitations_are_reported() -> None:
    result = compare_metabolic_competence()
    assert any("Gerets" in item for item in result["reported_limitations"])
    assert any("~10% of human liver" in item for item in result["reported_limitations"])
    assert len(result["functional_evidence"]) >= 4


@pytest.mark.parametrize("field", ["cell_type", "reference"])
def test_unknown_cell_model_raises(field: str) -> None:
    with pytest.raises(ValueError, match="unknown"):
        compare_metabolic_competence(**{field: "Caco-2"})


# --------------------------------------------------------------------------
# Resource and prompt
# --------------------------------------------------------------------------

def test_paper_summary_is_valid_json_with_correct_citation() -> None:
    summary = json.loads(paper_summary())
    assert summary["source"]["doi"] == SOURCE_DOI
    assert summary["source"]["article_number"] == "7"
    assert summary["source"]["pmid"] == "33504769"


def test_paper_summary_covers_the_required_sections() -> None:
    summary = json.loads(paper_summary())
    assert set(summary) >= {
        "source",
        "study_design",
        "receptors",
        "screening_summary",
        "metabolic_competence",
        "hazard_screening_context",
        "scope_disclaimers",
    }
    assay = summary["study_design"]["assay"]
    assert assay["transcripts_measured"] == 93
    assert assay["chemical_library_size"] == 1060
    assert "Fluidigm" in assay["transcriptomic_platform"]
    assert summary["hazard_screening_context"]["program"].startswith("U.S. EPA ToxCast")


def test_paper_summary_disclaims_the_common_misattributions() -> None:
    disclaimers = " ".join(json.loads(paper_summary())["scope_disclaimers"])
    assert "TempO-Seq" in disclaimers and "did NOT use" in disclaimers
    assert "500-gene" in disclaimers
    assert "1.349" in disclaimers
    assert "article number is 7, not 12" in disclaimers


def test_prompt_steers_to_ac50_and_bans_bmc() -> None:
    text = screen_novel_chemical(chemical_name="malathion", transcript="CYP3A4")
    assert "malathion" in text and "CYP3A4" in text
    assert "Report potency as AC50" in text
    assert "Do NOT report a BMC or BMD" in text
    assert "benchmark response of 1.349 SD" in text
    for step in ("STEP 0", "STEP 1", "STEP 2", "STEP 3", "STEP 4", "STEP 5"):
        assert step in text


def test_prompt_names_every_tool_and_the_resource() -> None:
    text = screen_novel_chemical()
    for tool in (
        "query_chemical_profile",
        "fit_concentration_response",
        "analyze_pathway_enrichment",
        "compare_metabolic_competence",
    ):
        assert tool in text
    assert "toxicogenomics://paper-summary" in text
    assert "the candidate chemical" in text


def test_prompt_warns_about_gain_loss_cytotoxicity() -> None:
    text = screen_novel_chemical()
    assert "cytotoxicity, not as" in text
    assert "bmad_multiplier=10.0" in text


def test_server_exposes_stdio_entrypoint() -> None:
    assert callable(server.main)
    assert mcp.name == "franzosa-heparg-toxicogenomics"
