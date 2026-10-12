"""Company profile: what the user tells Claude about their business."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .vocab import INSTRUMENT_FAMILIES, SECTORS, STAGES

Sector = Literal[tuple(SECTORS)]  # type: ignore[valid-type]
Stage = Literal[tuple(STAGES)]  # type: ignore[valid-type]
Wanted = Literal[tuple(INSTRUMENT_FAMILIES)]  # type: ignore[valid-type]


class CompanyProfile(BaseModel):
    """Leave a field empty (null) when the user has not said. Never guess."""

    name: Optional[str] = Field(None, description="Company name, if given")
    country: str = Field(..., description="ISO 3166 alpha-2 code of the country it operates in, e.g. GH, NG, CI")
    sector: Sector = Field(..., description="Closest sector from the fixed list")
    stage: Optional[Stage] = Field(
        None, description="startup = pre-revenue or first sales; early = revenue, under ~3 years; growth = scaling, 3+ years; mature = established"
    )
    amount_usd: Optional[float] = Field(None, description="Amount being raised, in US dollars")
    instruments_wanted: list[Wanted] = Field(
        default_factory=list,
        description="What kind of money: equity, quasi_equity, debt, working_capital, trade_finance, guarantee, grant. Empty = open to any.",
    )
    annual_revenue_usd: Optional[float] = Field(None, description="Last full year's revenue in US dollars")
    years_operating: Optional[float] = Field(None, description="Years the business has been trading")
    audited_years: Optional[int] = Field(None, description="Number of years of audited financial statements available")
    has_export_history: Optional[bool] = Field(None, description="Has the company exported before?")
    has_export_order: Optional[bool] = Field(None, description="Does it hold a confirmed export order or contract now?")
    impact_focus: Optional[bool] = Field(
        None, description="Does it create measurable social or environmental impact (smallholder farmers, jobs, women, climate)?"
    )
    women_led: Optional[bool] = Field(None, description="Is it women-owned or women-led?")

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("country must be a 2-letter ISO code such as GH, NG or CI")
        return v


# ---------------------------------------------------------------- funders found online

from .vocab import FUNDER_TYPES, INSTRUMENTS  # noqa: E402

FunderType = Literal[tuple(FUNDER_TYPES)]  # type: ignore[valid-type]
Instrument = Literal[tuple(INSTRUMENTS)]  # type: ignore[valid-type]
SectorOrAny = Literal[tuple(SECTORS + ["any"])]  # type: ignore[valid-type]


class Requirements(BaseModel):
    min_revenue_usd: Optional[float] = None
    min_years_operating: Optional[float] = None
    audited_years: Optional[int] = None
    export_history_required: Optional[bool] = None
    impact_required: Optional[bool] = None
    other: list[str] = Field(default_factory=list, description="Other stated requirements, short phrases")


class FoundFunder(BaseModel):
    """Criteria Claude read on a funder's own web page. Only facts stated on the page; null if not stated."""

    name: str
    type: FunderType
    geographies: list[str] = Field(..., description="ISO alpha-2 codes and/or regions: west_africa, east_africa, africa, sub_saharan_africa, mena, south_asia, southeast_asia, latin_america, europe, eu, emerging_markets, global ...")
    sectors: list[SectorOrAny]
    stages: list[Stage] = Field(default_factory=list, description="Empty if not stated")
    instruments: list[Instrument]
    ticket_min_usd: Optional[float] = None
    ticket_max_usd: Optional[float] = None
    requirements: Requirements = Field(default_factory=Requirements)
    direct_application: Optional[bool] = None
    how_to_apply: Optional[str] = None
    apply_url: Optional[str] = None
    source_urls: list[str] = Field(..., min_length=1, description="The page(s) where these criteria were read")
