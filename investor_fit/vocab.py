"""Shared vocabulary: the only values the funder data and company profiles may use."""

SECTORS = [
    "agribusiness", "agri_processing", "agri_fintech", "fintech", "manufacturing",
    "trade_export", "renewable_energy", "healthcare", "education", "infrastructure",
    "financial_institutions", "consumer", "technology", "retail", "logistics", "real_estate",
    "tourism_hospitality", "extractives", "water_sanitation", "climate", "media_creative",
    "professional_services",
]

# Sectors that partly overlap. A funder in a related sector earns partial sector credit.
RELATED_SECTORS = {
    "agribusiness": {"agri_processing", "agri_fintech", "trade_export"},
    "agri_processing": {"agribusiness", "manufacturing", "trade_export"},
    "agri_fintech": {"agribusiness", "fintech", "technology"},
    "fintech": {"agri_fintech", "technology", "financial_institutions"},
    "manufacturing": {"agri_processing", "trade_export"},
    "trade_export": {"agribusiness", "agri_processing", "manufacturing"},
    "technology": {"fintech", "agri_fintech"},
    "financial_institutions": {"fintech"},
    "renewable_energy": {"infrastructure", "climate"},
    "infrastructure": {"renewable_energy"},
    "healthcare": set(),
    "education": set(),
    "consumer": {"retail"},
    "retail": {"consumer"},
    "logistics": {"trade_export", "infrastructure"},
    "real_estate": {"infrastructure"},
    "tourism_hospitality": {"consumer"},
    "extractives": {"infrastructure"},
    "water_sanitation": {"infrastructure", "climate"},
    "climate": {"renewable_energy", "water_sanitation"},
    "media_creative": {"technology"},
    "professional_services": set(),
}

STAGES = ["startup", "early", "growth", "mature"]

STAGE_HELP = {
    "startup": "pre-revenue or first sales",
    "early": "has revenue, under about 3 years",
    "growth": "scaling, 3 or more years",
    "mature": "established, stable cash flows",
}

INSTRUMENTS = [
    "equity", "quasi_equity", "debt", "working_capital", "trade_finance",
    "guarantee", "grant", "on_lending",
]

# What a company asks for -> funder instruments that can satisfy it.
# "on_lending" means the money reaches the company through a partner bank.
INSTRUMENT_FAMILIES = {
    "equity": {"equity", "quasi_equity"},
    "quasi_equity": {"quasi_equity", "equity", "debt"},
    "debt": {"debt", "working_capital", "trade_finance", "quasi_equity", "on_lending"},
    "working_capital": {"working_capital", "trade_finance", "debt", "on_lending"},
    "trade_finance": {"trade_finance", "working_capital", "on_lending"},
    "guarantee": {"guarantee"},
    "grant": {"grant"},
}

FUNDER_TYPES = ["dfi", "export_credit", "impact_fund", "impact_lender", "vc", "pe", "bank"]

# ---------------------------------------------------------------- geography (global)
# Regions follow the UN M49 groupings, with a few finance-world groupings added.

WEST_AFRICA = {"BJ", "BF", "CV", "CI", "GM", "GH", "GN", "GW", "LR", "ML", "MR", "NE", "NG", "SN", "SL", "TG"}
EAST_AFRICA = {"BI", "KM", "DJ", "ER", "ET", "KE", "MG", "MW", "MU", "MZ", "RW", "SC", "SO", "SS", "TZ", "UG", "ZM", "ZW"}
CENTRAL_AFRICA = {"AO", "CM", "CF", "TD", "CG", "CD", "GQ", "GA", "ST"}
SOUTHERN_AFRICA = {"BW", "SZ", "LS", "NA", "ZA"}
NORTH_AFRICA = {"DZ", "EG", "LY", "MA", "SD", "TN"}
AFRICA = WEST_AFRICA | EAST_AFRICA | CENTRAL_AFRICA | SOUTHERN_AFRICA | NORTH_AFRICA
SUB_SAHARAN_AFRICA = AFRICA - NORTH_AFRICA | {"SD"}

MIDDLE_EAST = {"BH", "IQ", "IR", "IL", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "SY", "AE", "YE", "TR"}
MENA = MIDDLE_EAST | NORTH_AFRICA
SOUTH_ASIA = {"AF", "BD", "BT", "IN", "MV", "NP", "PK", "LK"}
SOUTHEAST_ASIA = {"BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"}
EAST_ASIA = {"CN", "HK", "JP", "KP", "KR", "MN", "MO", "TW"}
CENTRAL_ASIA = {"KZ", "KG", "TJ", "TM", "UZ"}
ASIA = SOUTH_ASIA | SOUTHEAST_ASIA | EAST_ASIA | CENTRAL_ASIA | {"AM", "AZ", "GE"}
OCEANIA = {"AU", "NZ", "FJ", "PG", "SB", "VU", "WS", "TO", "KI", "FM", "MH", "NR", "PW", "TV"}
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV",
      "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
EUROPE = EU | {"AL", "AD", "BY", "BA", "FO", "IS", "XK", "LI", "MD", "MC", "ME", "MK", "NO", "RU", "SM",
               "RS", "CH", "UA", "GB", "VA"}
NORTH_AMERICA = {"US", "CA"}
CARIBBEAN = {"AG", "BS", "BB", "CU", "DM", "DO", "GD", "HT", "JM", "KN", "LC", "VC", "TT", "PR"}
LATIN_AMERICA = {"AR", "BZ", "BO", "BR", "CL", "CO", "CR", "EC", "SV", "GT", "GY", "HN", "MX", "NI", "PA",
                 "PY", "PE", "SR", "UY", "VE"} | CARIBBEAN

# High-income economies (World Bank grouping, approximate). Everything else counts as an emerging market.
HIGH_INCOME = (EU - {"BG"}) | NORTH_AMERICA | {
    "AU", "NZ", "JP", "KR", "SG", "HK", "MO", "TW", "IL", "AE", "SA", "QA", "KW", "BH", "OM", "GB", "CH",
    "NO", "IS", "LI", "MC", "AD", "SM", "BN", "BS", "BB", "TT", "UY", "CL", "PA", "PR", "AG", "KN", "SC",
}
ALL_COUNTRIES = AFRICA | MENA | ASIA | OCEANIA | EUROPE | NORTH_AMERICA | LATIN_AMERICA
EMERGING_MARKETS = ALL_COUNTRIES - HIGH_INCOME

REGIONS = {
    "west_africa": WEST_AFRICA, "east_africa": EAST_AFRICA, "central_africa": CENTRAL_AFRICA,
    "southern_africa": SOUTHERN_AFRICA, "north_africa": NORTH_AFRICA, "africa": AFRICA,
    "sub_saharan_africa": SUB_SAHARAN_AFRICA, "middle_east": MIDDLE_EAST, "mena": MENA,
    "south_asia": SOUTH_ASIA, "southeast_asia": SOUTHEAST_ASIA, "east_asia": EAST_ASIA,
    "central_asia": CENTRAL_ASIA, "asia": ASIA, "oceania": OCEANIA, "eu": EU, "europe": EUROPE,
    "north_america": NORTH_AMERICA, "caribbean": CARIBBEAN, "latin_america": LATIN_AMERICA,
    "emerging_markets": EMERGING_MARKETS,
}

# Most specific first: used to score how closely a funder's focus matches the company's country.
REGION_SPECIFICITY = [
    ("west_africa", 12), ("east_africa", 12), ("central_africa", 12), ("southern_africa", 12),
    ("north_africa", 12), ("southeast_asia", 12), ("south_asia", 12), ("east_asia", 12),
    ("central_asia", 12), ("middle_east", 12), ("caribbean", 12), ("north_america", 12), ("eu", 11),
    ("sub_saharan_africa", 10), ("mena", 10), ("latin_america", 10), ("europe", 10), ("oceania", 10),
    ("africa", 9), ("asia", 9), ("emerging_markets", 6), ("global", 6),
]

def region_covers(token: str, country: str) -> bool:
    """True if a funder geography token (country code or region) covers the company's country."""
    token = token.strip().lower()
    if token == "global":
        return True
    if token in REGIONS:
        return country in REGIONS[token]
    return token.upper() == country
