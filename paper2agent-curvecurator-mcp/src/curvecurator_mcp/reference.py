"""Loading and querying the curated paper reference data."""

from __future__ import annotations

import functools
import json
from importlib import resources
from pathlib import Path
from typing import Any

_PACKAGE_DATA = "data/paper_reference.json"


@functools.lru_cache(maxsize=1)
def load_reference() -> dict[str, Any]:
    """Load ``paper_reference.json`` from package data or the repository checkout."""
    try:
        text = (
            resources.files("curvecurator_mcp")
            .joinpath(_PACKAGE_DATA)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        # Fallback for unusual import paths; the file is the same one.
        text = (Path(__file__).resolve().parent / _PACKAGE_DATA).read_text(encoding="utf-8")
    return json.loads(text)


def citation() -> dict[str, str]:
    source = load_reference()["source"]
    return {
        "doi": source["doi"],
        "pmid": source["pmid"],
        "citation": (
            f"{source['authors']}. {source['title']}. "
            f"{source['journal']} {source['volume']}:{source['article_number']} "
            f"({source['year']}). doi:{source['doi']}"
        ),
    }


def dataset_names() -> list[str]:
    return sorted(load_reference()["datasets"])


def get_dataset(name: str) -> dict[str, Any] | None:
    datasets = load_reference()["datasets"]
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "kinobeads": "kinobeads",
        "klaeger": "kinobeads",
        "drug_target": "kinobeads",
        "kinase_inhibitors": "kinobeads",
        "ctrp": "ctrp",
        "viability": "ctrp",
        "cell_viability": "ctrp",
        "decryptm": "decryptm",
        "decryptm_ptm": "decryptm",
        "phosphoproteome": "decryptm",
        "ptm": "decryptm",
    }
    resolved = aliases.get(key, key)
    return datasets.get(resolved)
