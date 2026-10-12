"""Company profile in plain Python (no third-party libraries), so matching runs anywhere,
including inside a user's Claude code-execution sandbox.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional

from .vocab import INSTRUMENT_FAMILIES, SECTORS, STAGES


class ProfileError(ValueError):
    pass


@dataclass
class Profile:
    country: str
    sector: str
    name: Optional[str] = None
    stage: Optional[str] = None
    amount_usd: Optional[float] = None
    instruments_wanted: list = field(default_factory=list)
    annual_revenue_usd: Optional[float] = None
    years_operating: Optional[float] = None
    audited_years: Optional[int] = None
    has_export_history: Optional[bool] = None
    has_export_order: Optional[bool] = None
    impact_focus: Optional[bool] = None
    women_led: Optional[bool] = None
    documents: list = field(default_factory=list)  # document types the company holds, e.g. "tax clearance certificate"

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, [])}

    # pydantic-compatible name used by older callers
    def model_dump(self, exclude_none: bool = True) -> dict[str, Any]:
        return self.as_dict()


def make_profile(data: Any) -> Profile:
    """Build a Profile from a dict (or return an existing Profile / pydantic model as a Profile)."""
    if isinstance(data, Profile):
        return data
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    if not isinstance(data, dict):
        raise ProfileError("company profile must be a JSON object")
    known = {f.name for f in fields(Profile)}
    d = {k: v for k, v in data.items() if k in known}
    problems = []
    country = str(d.get("country") or "").strip().upper()
    if len(country) != 2 or not country.isalpha():
        problems.append("country must be a 2-letter ISO code such as GH, NG, KE, BR")
    d["country"] = country
    if d.get("sector") not in SECTORS:
        problems.append(f"sector must be one of: {', '.join(SECTORS)}")
    if d.get("stage") is not None and d["stage"] not in STAGES:
        problems.append(f"stage must be one of: {', '.join(STAGES)}")
    wanted = d.get("instruments_wanted") or []
    bad = [w for w in wanted if w not in INSTRUMENT_FAMILIES]
    if bad:
        problems.append(f"instruments_wanted has unknown values {bad}; use {', '.join(INSTRUMENT_FAMILIES)}")
    for k in ("amount_usd", "annual_revenue_usd", "years_operating"):
        if d.get(k) is not None:
            try:
                d[k] = float(d[k])
            except (TypeError, ValueError):
                problems.append(f"{k} must be a number")
    if d.get("audited_years") is not None:
        try:
            d["audited_years"] = int(d["audited_years"])
        except (TypeError, ValueError):
            problems.append("audited_years must be a whole number")
    d["documents"] = [str(x).strip().lower() for x in (d.get("documents") or [])]
    if problems:
        raise ProfileError("; ".join(problems))
    return Profile(**d)
