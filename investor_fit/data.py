"""Loads and searches the funder database (data/funders.json)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .vocab import region_covers

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "funders.json"


@lru_cache(maxsize=4)
def load_funders(path: str | None = None) -> list[dict[str, Any]]:
    """The built-in checked list (or another file in the same format)."""
    with open(path or DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def get_funder(funder_id: str) -> dict[str, Any] | None:
    fid = funder_id.strip().lower()
    for f in load_funders():
        if f.get("id") == fid:
            return f
    return None


def search(
    country: str | None = None,
    sector: str | None = None,
    instrument: str | None = None,
    funder_type: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    out = []
    for f in load_funders():
        if country and not any(region_covers(g, country.upper()) for g in f.get("geographies", [])):
            continue
        if sector and sector not in f.get("sectors", []) and "any" not in f.get("sectors", []):
            continue
        if instrument and instrument not in f.get("instruments", []):
            continue
        if funder_type and f.get("type") != funder_type:
            continue
        if text:
            hay = " ".join([f.get("name", ""), f.get("notes") or "", " ".join((f.get("requirements") or {}).get("other") or [])]).lower()
            if text.lower() not in hay:
                continue
        out.append(f)
    return out


def brief(f: dict[str, Any]) -> dict[str, Any]:
    """Short card used in search results."""
    from .matching import _ticket_range

    return {
        "funder_id": f.get("id"),
        "name": f.get("name"),
        "type": f.get("type"),
        "geographies": f.get("geographies"),
        "sectors": f.get("sectors"),
        "stages": f.get("stages"),
        "instruments": f.get("instruments"),
        "ticket_range": _ticket_range(f),
        "direct_application": f.get("direct_application"),
        "data_confidence": f.get("confidence"),
        "last_checked": f.get("last_checked"),
    }
