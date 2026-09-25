"""Receptor / pathway mapping over the study's targeted hepatic transcript panel.

The study infers molecular initiating events with a three-step Bayesian network
over 32 transcripts and six receptors, yielding a posterior probability of
receptor activation per chemical. That is not an enrichment statistic, and this
module does not claim to reproduce it. What it does is map a supplied transcript
list onto the receptor marker sets the article names in text, and attach a
hypergeometric over-representation test against the 93-transcript panel as the
universe -- with the power caveats made explicit in the payload.
"""

from __future__ import annotations

from typing import Any

from scipy.stats import hypergeom

from .data_access import load_data

# Transcripts whose panel membership is verifiable from the article text.
# The full 93-transcript panel is given only in the article's Supplementary Tables.
_VERIFIED_PANEL_MEMBERS: frozenset[str] = frozenset(
    {
        # Canonical receptor markers named in text
        "CYP1A1", "CYP1A2", "CYP2B6", "CYP3A4", "ABCB11", "HMGCS2",
        # Other transcripts named in text
        "CYP2E1", "CYP24A1",
        # Replacement probes introduced after the first reference plate
        "MIR122", "NFE2L2", "PDK4", "XBP1",
        # Transcripts excluded from the network as receptor-unrelated
        "ACOX1", "APOA5", "BCL2", "CAT", "EGR1", "EZR", "FASN",
        "HSPA1A", "MMP10", "MYC", "PPP2R4", "SDHB",
        # Housekeeping genes
        "ACTB", "GAPDH", "POLR2A",
    }
)

# Transcripts whose original probes were dropped after the first reference plate.
_REPLACED_PROBES: frozenset[str] = frozenset({"KLK3", "MMP1", "SLC10A1", "SLC22A6"})


def _benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR adjustment (step-up), preserving input order."""
    n = len(pvalues)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvalues[i])
    adjusted = [0.0] * n
    running = 1.0
    for rank, idx in enumerate(reversed(order), start=1):
        position = n - rank + 1
        running = min(running, pvalues[idx] * n / position)
        adjusted[idx] = running
    return adjusted


def _gene_sets() -> list[dict[str, Any]]:
    receptors = load_data()["receptors"]
    sets: list[dict[str, Any]] = []
    for key, meta in receptors["modeled"].items():
        sets.append(
            {
                "pathway_id": key,
                "pathway_name": meta["full_name"],
                "uniprot": meta["uniprot"],
                "marker_genes": list(meta["canonical_markers_reported"]),
                "modeled_by_bayesian_network": True,
                "status_note": None,
            }
        )
    for key, meta in receptors.get("not_modeled_annotation", {}).items():
        sets.append(
            {
                "pathway_id": key,
                "pathway_name": meta["full_name"],
                "uniprot": meta["uniprot"],
                "marker_genes": list(meta["annotation_markers"]),
                "modeled_by_bayesian_network": False,
                "status_note": meta["status_note"],
            }
        )
    return sets


def analyze_pathway_enrichment(significant_genes: list[str]) -> list[dict[str, Any]]:
    """Map transcripts to the study's receptor sets with an over-representation test.

    Args:
        significant_genes: HGNC symbols of differentially expressed transcripts.

    Returns:
        One record per receptor/pathway, ordered by BH-adjusted p-value then by
        the number of matched markers, each carrying its provenance and caveats.
    """
    if not isinstance(significant_genes, list):
        raise TypeError("significant_genes must be a list of HGNC gene symbols")

    cleaned: list[str] = []
    seen: set[str] = set()
    for gene in significant_genes:
        if not isinstance(gene, str):
            raise TypeError(f"gene symbols must be strings; got {type(gene).__name__}")
        symbol = gene.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            cleaned.append(symbol)

    data = load_data()
    universe_size = int(data["assay"]["transcripts_measured"])
    query_size = len(cleaned)

    on_panel = [g for g in cleaned if g in _VERIFIED_PANEL_MEMBERS]
    replaced = [g for g in cleaned if g in _REPLACED_PROBES]
    unverifiable = [
        g for g in cleaned
        if g not in _VERIFIED_PANEL_MEMBERS and g not in _REPLACED_PROBES
    ]

    records: list[dict[str, Any]] = []
    pvalues: list[float] = []

    for gene_set in _gene_sets():
        markers = gene_set["marker_genes"]
        matched = [g for g in cleaned if g in markers]
        set_size = len(markers)

        if set_size == 0 or query_size == 0:
            pvalue = None
        else:
            # P(X >= matched) under the hypergeometric null, universe = 93-transcript panel.
            pvalue = float(
                hypergeom.sf(len(matched) - 1, universe_size, set_size, query_size)
            )
        pvalues.append(1.0 if pvalue is None else pvalue)

        records.append(
            {
                "pathway_id": gene_set["pathway_id"],
                "pathway_name": gene_set["pathway_name"],
                "uniprot": gene_set["uniprot"],
                "modeled_by_bayesian_network": gene_set["modeled_by_bayesian_network"],
                "marker_genes_reported_in_text": markers,
                "matched_genes": matched,
                "n_matched": len(matched),
                "n_markers_in_set": set_size,
                "p_value": pvalue,
                "status_note": gene_set["status_note"],
            }
        )

    for record, q in zip(records, _benjamini_hochberg(pvalues)):
        record["q_value_bh"] = None if record["p_value"] is None else q
        record["significant_at_q_0_05"] = bool(
            record["p_value"] is not None and q < 0.05
        )

    records.sort(
        key=lambda r: (
            1.0 if r["q_value_bh"] is None else r["q_value_bh"],
            -r["n_matched"],
            r["pathway_id"],
        )
    )

    caveats = [
        "Marker sets contain ONLY the canonical response genes the article names in "
        "its text (CYP1A1/CYP1A2 for AhR, CYP2B6 for CAR, CYP3A4 for PXR, ABCB11 for "
        "FXR, HMGCS2 for PPARalpha). The full 32-transcript network and the full "
        "93-transcript panel are given in the article's Supplementary Tables only. "
        "Sets of 1-2 genes have very low statistical power; a non-significant q-value "
        "here is not evidence of absence.",
        "The study's own inference is a Bayesian posterior probability of receptor "
        "activation from concentration-response patterns, NOT a gene-set "
        "over-representation test. These q-values are a convenience summary and are "
        "not comparable to the study's reported probabilities.",
        "Substantial cross-talk was inferred between the six receptors, so marker "
        "overlap does not resolve to a single initiating event.",
        "AR has no canonical marker gene named in the article text, so no test is "
        "computed for it.",
    ]
    if unverifiable:
        caveats.append(
            f"Panel membership could not be verified from the article text for "
            f"{len(unverifiable)} submitted symbol(s): {', '.join(unverifiable)}. "
            f"They are counted in the query size but may lie outside the 93-transcript panel."
        )
    if replaced:
        caveats.append(
            f"{', '.join(replaced)} had their original probes removed after the first "
            f"reference plate for excessive non-detects, and carry no usable data in this study."
        )

    return [
        {
            **record,
            "universe": {
                "size": universe_size,
                "description": "The study's 93-transcript targeted hepatic qRT-PCR panel",
                "query_size": query_size,
                "query_genes_verifiable_on_panel": on_panel,
            },
            "test": "hypergeometric over-representation, Benjamini-Hochberg FDR",
            "caveats": caveats,
            "source_doi": "10.1038/s41540-020-00166-2",
        }
        for record in records
    ]
