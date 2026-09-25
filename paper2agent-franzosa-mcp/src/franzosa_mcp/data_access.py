"""Loading and lookup for the bundled, provenance-tagged study dataset."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_ENV_DIRS = (
    Path(__file__).resolve().parents[2] / "data",
    Path(__file__).resolve().parent / "data",
)

DATA_FILENAME = "sample_data.json"


def _locate() -> Path:
    for directory in _DATA_ENV_DIRS:
        candidate = directory / DATA_FILENAME
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(d / DATA_FILENAME) for d in _DATA_ENV_DIRS)
    raise FileNotFoundError(f"bundled dataset not found; searched: {searched}")


@lru_cache(maxsize=1)
def load_data() -> dict[str, Any]:
    """Load the bundled dataset (cached)."""
    with _locate().open(encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(value: str) -> str:
    """Case- and punctuation-insensitive key for chemical name matching.

    Isomer prefixes such as ``p,p'-`` carry meaning (p,p'-DDT and o,p'-DDT are
    distinct entries with different receptor profiles), so the comma and prime
    are preserved as a single separator rather than discarded.
    """
    text = value.strip().lower()
    text = text.replace("’", "'").replace("´", "'")
    text = re.sub(r"[\s_]+", " ", text)
    return text.strip(" -")


_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def is_casrn(value: str) -> bool:
    return bool(_CAS_RE.match(value.strip()))


@lru_cache(maxsize=1)
def _chemical_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in load_data()["reference_chemicals"]:
        keys = [record["name"], *record.get("synonyms", [])]
        casrn = record.get("casrn")
        if casrn:
            keys.append(casrn)
        for key in keys:
            index.setdefault(_normalize(key), record)
    return index


def find_chemical(query: str) -> dict[str, Any] | None:
    """Resolve a chemical by name, synonym, or CAS RN. Returns None if unknown."""
    if not query or not query.strip():
        return None
    index = _chemical_index()
    key = _normalize(query)
    if key in index:
        return index[key]
    # Fall back to a containment match so "DDT" style partials do not silently
    # resolve to the wrong isomer: only accept an unambiguous single match.
    matches = {id(v): v for k, v in index.items() if key and (key in k or k in key)}
    if len(matches) == 1:
        return next(iter(matches.values()))
    return None


def known_chemicals() -> list[str]:
    """Names of every chemical the bundled dataset can resolve."""
    return [record["name"] for record in load_data()["reference_chemicals"]]
