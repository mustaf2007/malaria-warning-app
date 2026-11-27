"""Configuration and indicator catalogue for Africa Malaria Intelligence."""
from dataclasses import dataclass
from datetime import datetime, timezone

APP_NAME = "Africa Malaria Intelligence"
DEFAULT_START_YEAR = 1960
# Follow the current calendar year; each source returns only years it actually publishes.
DEFAULT_END_YEAR = datetime.now(timezone.utc).year


def year_range_bounds(observed_years=None) -> tuple[int, int]:
    """Return slider bounds covering the default analysis window and observed years."""
    values = [int(year) for year in (observed_years or [])]
    return min([DEFAULT_START_YEAR, *values]), max([DEFAULT_END_YEAR, *values])
REQUEST_TIMEOUT = 25
USER_AGENT = "AfricaMalariaIntelligence/1.0 (open-data research dashboard)"

@dataclass(frozen=True)
class Indicator:
    code: str
    name: str
    description: str
    unit: str
    group: str
    source: str = "World Bank"
    kind: str = "reported_or_modelled"

INDICATORS = [
    Indicator("SH.MLR.INCD.P3", "Malaria incidence", "Estimated new malaria cases per 1,000 population at risk.", "per 1,000 at risk", "Burden", kind="modelled"),
    Indicator("SH.STA.MALR", "Reported confirmed malaria cases", "Confirmed malaria cases reported by national malaria control programmes.", "reported cases", "Burden", kind="reported"),
    Indicator("SH.MLR.TRET.ZS", "Children with fever receiving antimalarial drugs", "Share of children under five with recent fever who received an appropriate antimalarial drug.", "%", "Treatment", kind="survey"),
    Indicator("SP.POP.TOTL", "Total population", "Total population, used for contextual analysis.", "people", "Population"),
    Indicator("SP.POP.0014.TO.ZS", "Population ages 0–14", "Children as a share of the population.", "%", "Population"),
    Indicator("SH.DYN.MORT", "Under-five mortality", "Under-five mortality rate, a contextual child-health indicator.", "per 1,000 live births", "Vulnerability"),
    Indicator("SH.XPD.CHEX.GD.ZS", "Health expenditure", "Current health expenditure as a share of GDP.", "% GDP", "Health systems"),
    Indicator("SH.XPD.CHEX.PC.CD", "Health expenditure per capita", "Current health expenditure per capita in current US dollars.", "current US$", "Health systems"),
    Indicator("SP.DYN.LE00.IN", "Life expectancy", "Life expectancy at birth, total years.", "years", "Population"),
]
INDICATOR_BY_CODE = {item.code: item for item in INDICATORS}
OWID_DATASETS = {
    "number-of-deaths-from-malaria-ghe": "Estimated malaria deaths",
    "death-rate-from-malaria": "Malaria death rate",
    "estimated-number-of-malaria-cases": "Estimated malaria cases",
}
EXTERNAL_INDICATOR_LABELS = {f"OWID:{slug}": name for slug, name in OWID_DATASETS.items()}
SOURCE_LINKS = {
    "World Bank": "https://data.worldbank.org/",
    "WHO Global Health Observatory": "https://www.who.int/data/gho",
    "WHO World Malaria Report": "https://www.who.int/teams/global-malaria-programme/reports/world-malaria-report",
    "Malaria Atlas Project": "https://malariaatlas.org/",
    "UNICEF Data": "https://data.unicef.org/",
    "Our World in Data": "https://ourworldindata.org/malaria",
}
