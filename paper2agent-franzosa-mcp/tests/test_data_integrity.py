"""Guards on the bundled dataset: correct citation, honest provenance, no invented values.

These tests exist because the most likely failure mode for a paper-derived agent
is not a crash -- it is silently presenting a plausible number the source never
reported, or reproducing a methodology the source never used.
"""

from __future__ import annotations

import pytest

from franzosa_mcp.data_access import find_chemical, known_chemicals, load_data

DATA = load_data()

# Every quantity below is stated in the article text of doi:10.1038/s41540-020-00166-2.
PAPER_REPORTED_COUNTS = {
    ("assay", "transcripts_measured"): 93,
    ("assay", "assays_per_array"): 96,
    ("assay", "chemical_library_size"): 1060,
    ("assay", "endpoints_per_transcript"): 2,
    ("network_model", "reference_chemical_count"): 10,
    ("network_model", "transcripts_responding_to_reference_chemicals"): 45,
    ("network_model", "transcripts_excluded_as_receptor_unrelated"): 13,
    ("network_model", "transcripts_in_final_network"): 32,
    ("network_model", "chemicals_analyzed_in_network"): 1053,
    ("screening_summary", "chemicals_tested"): 1060,
    ("screening_summary", "chemicals_with_any_systematic_relationship"): 1037,
    ("screening_summary", "chemicals_after_omitting_curve_fit_warning_flags"): 718,
}


@pytest.mark.parametrize("path,expected", list(PAPER_REPORTED_COUNTS.items()), ids=str)
def test_paper_reported_counts(path: tuple[str, str], expected: int) -> None:
    section, key = path
    assert DATA[section][key] == expected


def test_citation_is_article_number_seven() -> None:
    source = DATA["source"]
    assert source["volume"] == "7"
    assert source["article_number"] == "7"
    assert source["doi"] == "10.1038/s41540-020-00166-2"
    assert source["pmid"] == "33504769"
    assert source["pmcid"] == "PMC7840683"
    assert "not 12" in source["citation_note"]


def test_excluded_transcript_arithmetic_is_consistent() -> None:
    network = DATA["network_model"]
    assert len(network["excluded_transcripts"]) == network["transcripts_excluded_as_receptor_unrelated"]
    assert (
        network["transcripts_responding_to_reference_chemicals"]
        - network["transcripts_excluded_as_receptor_unrelated"]
        == network["transcripts_in_final_network"]
    )


def test_probe_substitution_counts_balance() -> None:
    subs = DATA["assay"]["probe_substitutions"]
    assert len(subs["replaced_transcripts"]) == len(subs["replacement_transcripts"]) == 4


def test_platform_is_fluidigm_qrtpcr_not_temposeq() -> None:
    platform = DATA["assay"]["transcriptomic_platform"]
    assert "Fluidigm" in platform and "RT-PCR" in platform
    assert "TempO-Seq" not in platform
    assert DATA["assay"]["transcripts_measured"] != 500


def test_pipeline_uses_ac50_not_benchmark_dose() -> None:
    pipeline = DATA["analysis_pipeline"]
    assert pipeline["models_fit"] == ["constant", "hill", "gain-loss"]
    assert pipeline["model_selection"].startswith("Akaike")
    assert "AC50" in pipeline["potency_parameter"]
    assert "1.349" in pipeline["benchmark_dose_note"]
    assert "does NOT perform benchmark dose" in pipeline["benchmark_dose_note"]


def test_hit_criteria_match_the_paper() -> None:
    pipeline = DATA["analysis_pipeline"]
    assert pipeline["transcriptomic_bmad_multiplier"] == 3.0
    assert pipeline["transcriptomic_fold_change_cutoff"] == 1.2
    assert pipeline["cytotoxicity_bmad_multiplier"] == 10.0
    assert "lowest two tested concentrations" in pipeline["bmad_definition"]


def test_exactly_six_receptors_are_modeled() -> None:
    modeled = DATA["receptors"]["modeled"]
    assert set(modeled) == {"AhR", "CAR", "PXR", "FXR", "AR", "PPARA"}
    assert all(meta["modeled_by_bayesian_network"] for meta in modeled.values())


def test_nrf2_is_present_but_never_modeled() -> None:
    nrf2 = DATA["receptors"]["not_modeled_annotation"]["NFE2L2"]
    assert nrf2["on_panel"] is True
    assert nrf2["modeled_by_bayesian_network"] is False
    assert "NFE2L2" not in DATA["receptors"]["modeled"]
    assert "replacement probes" in nrf2["status_note"]


def test_canonical_markers_match_the_reported_sentence() -> None:
    modeled = DATA["receptors"]["modeled"]
    assert modeled["AhR"]["canonical_markers_reported"] == ["CYP1A1", "CYP1A2"]
    assert modeled["CAR"]["canonical_markers_reported"] == ["CYP2B6"]
    assert modeled["PXR"]["canonical_markers_reported"] == ["CYP3A4"]
    assert modeled["FXR"]["canonical_markers_reported"] == ["ABCB11"]
    assert modeled["PPARA"]["canonical_markers_reported"] == ["HMGCS2"]
    assert modeled["AR"]["canonical_markers_reported"] == []


def test_ten_receptor_reference_chemicals_plus_one_metabolic_control() -> None:
    chemicals = DATA["reference_chemicals"]
    activators = [c for c in chemicals if c["activates_receptors"]]
    controls = [c for c in chemicals if not c["activates_receptors"]]
    assert len(activators) == DATA["network_model"]["reference_chemical_count"] == 10
    assert [c["name"] for c in controls] == ["Aflatoxin B1"]


def test_every_receptor_reference_chemical_has_a_reference_activator() -> None:
    covered = {r for c in DATA["reference_chemicals"] for r in c["activates_receptors"]}
    assert covered == set(DATA["receptors"]["modeled"])


def test_reference_chemical_receptor_names_are_valid() -> None:
    valid = set(DATA["receptors"]["modeled"])
    for chemical in DATA["reference_chemicals"]:
        assert set(chemical["activates_receptors"]) <= valid, chemical["name"]


def test_no_chemical_carries_a_fabricated_potency() -> None:
    for chemical in DATA["reference_chemicals"]:
        assert chemical["ac50_uM"] is None, chemical["name"]
        assert chemical["ac50_provenance"] == "not_reported", chemical["name"]
        assert chemical["cytotoxicity_ac50_uM"] is None, chemical["name"]
        assert chemical["cytotoxicity_provenance"] == "not_reported", chemical["name"]


def test_every_casrn_is_flagged_as_external() -> None:
    for chemical in DATA["reference_chemicals"]:
        assert chemical["casrn_provenance"] == "external_identifier", chemical["name"]


def test_synthetic_fixtures_are_labelled_and_never_attributed() -> None:
    fixtures = DATA["synthetic_fixtures"]
    assert "SYNTHETIC" in fixtures["_warning"]
    assert "must NOT be cited" in fixtures["_warning"]
    assert len(fixtures["concentration_series_uM"]) == DATA["assay"]["concentration_response_design"].count("point") * 8
    for case in fixtures["cases"]:
        assert case["provenance"] == "synthetic"
        assert len(case["responses_log2fc"]) == len(fixtures["concentration_series_uM"])
        assert case["expected_winning_model"] in {"cnst", "hill", "gnls"}


def test_synthetic_fixtures_carry_no_chemical_attribution() -> None:
    names = {c["name"].lower() for c in DATA["reference_chemicals"]}
    for case in DATA["synthetic_fixtures"]["cases"]:
        blob = f"{case['id']} {case['description']}".lower()
        assert not any(name in blob for name in names), case["id"]


def test_cyp450_baseline_ratios_are_absent_from_the_dataset() -> None:
    evidence = DATA["metabolic_competence"]["cyp450_evidence"]
    for cyp in ("CYP1A2", "CYP2B6", "CYP3A4"):
        assert evidence[cyp]["baseline_ratio_vs_PHH"] is None
        assert evidence[cyp]["provenance"] == "not_reported"
    assert "does NOT publish a table" in evidence["note"]


def test_metabolic_activity_ratio_is_the_reported_ten_percent() -> None:
    models = DATA["metabolic_competence"]["cell_models"]
    assert models["HepaRG"]["relative_metabolic_activity_vs_human_liver"] == 0.10
    assert models["primary_human_hepatocytes"]["relative_metabolic_activity_vs_human_liver"] == 1.0
    assert models["HepG2"]["relative_metabolic_activity_vs_human_liver"] is None


def test_provenance_policy_covers_every_tag_in_use() -> None:
    policy = set(DATA["provenance_policy"])
    assert policy == {"paper_reported", "external_identifier", "synthetic", "not_reported"}


def test_external_archives_are_referenced_not_bundled() -> None:
    files = DATA["external_data_files"]
    assert "LTEA_Level5_20191119.zip" in files["level_5_curve_fits"]
    assert "15 GB" in files["imagery"]
    assert "does not bundle or download" in files["note"]


def test_lookup_resolves_every_bundled_chemical_by_name_and_cas() -> None:
    for name in known_chemicals():
        assert find_chemical(name) is not None, name
    for chemical in DATA["reference_chemicals"]:
        assert find_chemical(chemical["casrn"])["name"] == chemical["name"]
        for synonym in chemical["synonyms"]:
            assert find_chemical(synonym) is not None, synonym


def test_lookup_rejects_unknown_and_blank_queries() -> None:
    assert find_chemical("bisphenol A") is None
    assert find_chemical("") is None
    assert find_chemical("   ") is None
