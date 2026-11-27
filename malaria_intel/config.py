"""Configuration and indicator catalogue for Africa Malaria Intelligence."""
from dataclasses import dataclass

APP_NAME = "Africa Malaria Intelligence"
DEFAULT_START_YEAR = 2000
DEFAULT_END_YEAR = 2024
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
    Indicator("SH.MLR.INCD.P3", "Malaria incidence", "Estimated malaria cases per 1,000 population at risk.", "per 1,000 at risk", "Burden", kind="modelled"),
    Indicator("SH.MLR.CASES", "Malaria cases", "Estimated number of malaria cases.", "cases", "Burden", kind="modelled"),
    Indicator("SH.MLR.DEATHS", "Malaria deaths", "Estimated number of malaria deaths.", "deaths", "Burden", kind="modelled"),
    Indicator("SH.MLR.MORT", "Malaria mortality rate", "Malaria mortality rate per 100,000 population at risk.", "per 100,000 at risk", "Burden", kind="modelled"),
    Indicator("SH.MLR.PREV.ZS", "Malaria prevalence", "Estimated malaria parasite prevalence indicator, where available.", "%", "Burden", kind="modelled"),
    Indicator("SH.MLR.NETS.ZS", "Insecticide-treated net use", "Use of insecticide-treated nets among the relevant population, where available.", "%", "Prevention"),
    Indicator("SP.POP.TOTL", "Total population", "Total population, used for contextual analysis.", "people", "Population"),
    Indicator("SP.POP.0014.TO.ZS", "Population ages 0–14", "Children as a share of the population.", "%", "Population"),
    Indicator("SH.DYN.MORT", "Under-five mortality", "Under-five mortality rate, a contextual child-health indicator.", "per 1,000 live births", "Vulnerability"),
    Indicator("SH.XPD.CHEX.GD.ZS", "Health expenditure", "Current health expenditure as a share of GDP.", "% GDP", "Health systems"),
    Indicator("SH.XPD.CHEX.PC.CD", "Health expenditure per capita", "Current health expenditure per capita in current US dollars.", "current US$", "Health systems"),
    Indicator("SP.DYN.LE00.IN", "Life expectancy", "Life expectancy at birth, total years.", "years", "Population"),
]
INDICATOR_BY_CODE = {item.code: item for item in INDICATORS}
SOURCE_LINKS = {
    "World Bank": "https://data.worldbank.org/",
    "WHO Global Health Observatory": "https://www.who.int/data/gho",
    "WHO World Malaria Report": "https://www.who.int/teams/global-malaria-programme/reports/world-malaria-report",
    "Malaria Atlas Project": "https://malariaatlas.org/",
    "UNICEF Data": "https://data.unicef.org/",
    "Our World in Data": "https://ourworldindata.org/malaria",
}
