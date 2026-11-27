"""Africa Malaria Intelligence — complete Streamlit workspace."""
from __future__ import annotations
from io import BytesIO
from datetime import datetime, timezone
import pandas as pd
import plotly.express as px
import streamlit as st
from malaria_intel.analytics import answer_data_question, filter_observations, forecast_linear, latest_country_values, validate_observations, year_over_year
from malaria_intel.config import APP_NAME, DEFAULT_START_YEAR, DEFAULT_END_YEAR, INDICATORS, SOURCE_LINKS, EXTERNAL_INDICATOR_LABELS
from malaria_intel.data_sources import DataSourceError, fetch_african_countries, fetch_indicator_bundle, discover_who_malaria_indicators, fetch_who_gho_indicator, fetch_owid_bundle, MAP_METRICS, fetch_map_releases, fetch_map_admin1, fetch_map_series

st.set_page_config(page_title=APP_NAME, page_icon="🦟", layout="wide", initial_sidebar_state="expanded")
THEMES = {
 "Emerald": ("#071B18","#102A25","#38D9A9","#E8F4F0","#9CB8AE"),
 "Navy": ("#0B1424","#14233A","#69B7FF","#EEF4FF","#A7B6CC"),
 "Light": ("#F4F7F8","#FFFFFF","#087F69","#172B2A","#617472"),
 "Dark": ("#101418","#1B242B","#5ED6C0","#F1F5F4","#AAB8B5"),
}
@st.cache_data(ttl=86400, show_spinner=False)
def load_data(start, end):
    countries = fetch_african_countries()
    rows, status = fetch_indicator_bundle(start, end)
    owid_rows, owid_status = fetch_owid_bundle(start, end)
    return countries, rows + owid_rows, status + owid_status
@st.cache_data(ttl=86400, show_spinner=False)
def who_catalogue():
    return discover_who_malaria_indicators()
@st.cache_data(ttl=86400, show_spinner=False)
def map_releases():
    return fetch_map_releases()
@st.cache_data(ttl=86400, show_spinner=False)
def map_admin_units(iso3, admin_version):
    return fetch_map_admin1(iso3, admin_version)
@st.cache_data(ttl=86400, show_spinner=False)
def map_series(metric, version, level, iso3, admin_id, stat):
    return fetch_map_series(metric, version, level, iso3=iso3, admin_unit_id=admin_id, stat=stat)
def label(code):
    x = next((i for i in INDICATORS if i.code == code), None)
    return f"{x.name} · {x.unit}" if x else EXTERNAL_INDICATOR_LABELS.get(code, code)
def line_chart(df, title, unit):
    if df.empty:
        st.info("No non-missing observations are available for this selection. Try another indicator, country or period.")
        return
    fig = px.line(df, x="year", y="value", color="country", markers=True, title=title,
                  labels={"year":"Reference year","value":unit,"country":"Country"})
    fig.update_layout(hovermode="x unified", legend_title_text="", margin=dict(l=8,r=8,t=55,b=8))
    st.plotly_chart(fig, use_container_width=True)
def excel_bytes(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Observations")
    return buf.getvalue()

with st.sidebar:
    st.markdown("## 🦟 Africa Malaria Intelligence")
    st.caption("Open-data epidemiological intelligence")
    theme_name = st.selectbox("Appearance", list(THEMES))
    bg,panel,accent,fg,muted = THEMES[theme_name]
    if st.button("↻ Refresh public data", use_container_width=True):
        load_data.clear(); who_catalogue.clear(); map_releases.clear(); map_admin_units.clear(); map_series.clear(); st.rerun()
    st.caption("Public sources cached for 24 hours.")
st.markdown(f"""<style>
.stApp{{background:{bg};color:{fg}}}[data-testid="stSidebar"]{{background:{panel}}}
[data-testid="stMetric"]{{background:{panel};border:1px solid rgba(130,170,160,.22);padding:15px;border-radius:14px}}
[data-testid="stMetricLabel"] p{{color:{muted}!important}}[data-testid="stMetricValue"]{{color:{fg}!important}}
.ami-hero{{padding:24px 28px;border-radius:18px;background:linear-gradient(120deg,{panel},rgba(20,85,70,.4));border:1px solid rgba(130,170,160,.2);margin-bottom:18px}}
.ami-eyebrow{{color:{accent};text-transform:uppercase;letter-spacing:.14em;font-size:.72rem;font-weight:700}}
</style>""", unsafe_allow_html=True)
st.markdown(f'<div class="ami-hero"><div class="ami-eyebrow">Continental public-health intelligence</div><h1>🦟 {APP_NAME}</h1><div style="color:{muted}">Evidence-led malaria burden, trends, interventions and country comparisons across Africa.</div></div>', unsafe_allow_html=True)

with st.spinner("Connecting to public open-data sources…"):
    try:
        countries, rows, statuses = load_data(DEFAULT_START_YEAR, DEFAULT_END_YEAR)
        load_error = None
    except Exception as exc:
        countries, rows, statuses, load_error = [], [], [], str(exc)
country_names = {c["iso3"]:c["name"] for c in countries}
raw = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["iso3","country","year","indicator_code","value","source","source_url"])
if countries and not raw.empty:
    raw = raw[raw["iso3"].isin(country_names)].copy()
if st.session_state.get("who_rows"):
    raw = pd.concat([raw, pd.DataFrame(st.session_state.who_rows)], ignore_index=True)
with st.sidebar:
    st.markdown("### Analysis filters")
    iso_options = [c["iso3"] for c in countries] or sorted(raw.get("iso3",pd.Series(dtype=str)).dropna().unique())
    default_iso = [x for x in ["SOM","KEN","ETH","UGA","TZA","NGA","GHA","COD"] if x in iso_options]
    selected_iso = st.multiselect("Countries", iso_options, default=default_iso)
    years = sorted(raw["year"].dropna().unique().tolist()) if not raw.empty else list(range(DEFAULT_START_YEAR,DEFAULT_END_YEAR+1))
    year_range = st.slider("Reference period", int(min(years)), int(max(years)), (int(min(years)),int(max(years)))) if len(years)>1 else (DEFAULT_START_YEAR,DEFAULT_END_YEAR)
    upload = st.file_uploader("Upload supplementary CSV", type=["csv"], help="Required columns: iso3,country,year,indicator_code,value,source. Session-only.")
if upload is not None:
    try:
        extra = pd.read_csv(upload)
        if "source" not in extra: extra["source"] = "User-uploaded dataset"
        if "source_url" not in extra: extra["source_url"] = "User-provided file"
        extra,_ = validate_observations(extra)
        raw = pd.concat([raw,extra],ignore_index=True)
        raw,_ = validate_observations(raw)
        st.sidebar.success(f"Added {len(extra):,} session rows.")
    except Exception as exc:
        st.sidebar.error(f"Upload rejected: {exc}")
if not raw.empty:
    raw, quality = validate_observations(raw)
else:
    quality = {"rows":0,"missing_values":0,"duplicate_keys_removed":0,"countries":0,"indicators":0,"years":0}
if load_error: st.warning(f"Public sources unavailable: {load_error}. Upload a compatible CSV to continue.")
nav = st.sidebar.radio("WORKSPACES", [
 "Executive Overview","Country Intelligence","Surveillance & Trends","Spatial Intelligence",
 "Prevention & Health Systems","MAP Subnational Intelligence","Forecasting & Risk Analysis","AI Malaria Analyst",
 "Reports & Downloads","Data Quality & Sources"])
view = filter_observations(raw,countries=selected_iso or None,start_year=year_range[0],end_year=year_range[1]) if not raw.empty else raw
codes = sorted(raw["indicator_code"].dropna().unique()) if not raw.empty else []
malaria_codes = [c for c in codes if c.startswith("SH.MLR") or c == "SH.STA.MALR" or c.startswith("OWID:")]
default_code = next((c for c in ["SH.MLR.INCD.P3","SH.MLR.CASES","SH.MLR.DEATHS","SH.MLR.MORT"] if c in codes), codes[0] if codes else None)

if nav == "Executive Overview":
    st.subheader("Continental malaria situation")
    st.caption("Latest available observations. Reference years can differ by indicator and country.")
    if raw.empty: st.info("No observations loaded. Check public-source connectivity or upload a compatible dataset.")
    else:
        latest_year = int(raw.loc[raw.value.notna(),"year"].max()) if raw.value.notna().any() else "—"
        a,b,c,d = st.columns(4)
        a.metric("Countries represented",f"{raw.iso3.nunique():,}")
        b.metric("Indicators loaded",f"{raw.indicator_code.nunique():,}")
        c.metric("Observations",f"{len(raw):,}")
        d.metric("Latest reference year",str(latest_year))
        if default_code:
            st.markdown("#### Latest country observations")
            latest = latest_country_values(view,default_code)
            st.dataframe(latest[["country","iso3","year","value","source"]].rename(columns={"country":"Country","iso3":"ISO3","year":"Year","value":"Value","source":"Source"}),use_container_width=True,hide_index=True)
        if malaria_codes:
            code = st.selectbox("Featured malaria indicator",malaria_codes,format_func=label)
            line_chart(filter_observations(view,indicator=code),f"{label(code)} over time",label(code))
        else: st.info("No malaria-specific indicator observations were returned. Context indicators are not substituted for malaria burden.")

elif nav == "Country Intelligence":
    st.subheader("Country intelligence profiles")
    if not codes: st.info("Load data or upload a compatible CSV.")
    else:
        iso = st.selectbox("Country",sorted(raw.iso3.unique()),format_func=lambda x:f"{country_names.get(x,x)} ({x})")
        prof = raw[(raw.iso3==iso)&raw.value.notna()].sort_values("year")
        st.markdown(f"### {country_names.get(iso,iso)}")
        for code in codes:
            series = prof[prof.indicator_code==code]
            if not series.empty:
                last=series.iloc[-1]; st.metric(label(code),f"{last.value:,.3g}",f"Reference year {int(last.year)}")
        code = st.selectbox("Historical indicator",codes,format_func=label,key="profile_code")
        line_chart(prof[prof.indicator_code==code],f"{country_names.get(iso,iso)} · {label(code)}",label(code))
        st.dataframe(prof[["year","indicator_code","value","source","source_url"]],use_container_width=True,hide_index=True)

elif nav == "Surveillance & Trends":
    st.subheader("Surveillance and epidemiological trends")
    if not codes: st.info("No indicator series are loaded.")
    else:
        code=st.selectbox("Indicator",codes,format_func=label)
        countries_pick=st.multiselect("Compare countries",sorted(raw.iso3.unique()),default=(selected_iso[:5] if selected_iso else sorted(raw.iso3.unique())[:5]),key="trend_countries")
        trend=filter_observations(raw,indicator=code,countries=countries_pick or None,start_year=year_range[0],end_year=year_range[1])
        line_chart(trend,f"{label(code)} · country trends",label(code))
        if not trend.empty:
            iso=st.selectbox("Country for year-on-year analysis",sorted(trend.iso3.unique()))
            changes=year_over_year(raw,code,iso)
            st.dataframe(changes[["year","value","absolute_change","percent_change","source"]],use_container_width=True,hide_index=True)

elif nav == "Spatial Intelligence":
    st.subheader("Geographic distribution")
    if not codes: st.info("No spatial observations are loaded.")
    else:
        code=st.selectbox("Map indicator",codes,format_func=label)
        latest=latest_country_values(raw,code)
        if latest.empty: st.info("No country observations available for this indicator.")
        else:
            latest["country_label"]=latest.iso3.map(lambda x:country_names.get(x,x))
            fig=px.choropleth(latest,locations="iso3",locationmode="ISO-3",color="value",hover_name="country_label",
                hover_data={"iso3":True,"year":True,"value":":,.3g"},color_continuous_scale="YlOrRd",title=f"Latest available · {label(code)}")
            fig.update_geos(showframe=False,showcoastlines=True,showcountries=True,projection_type="natural earth")
            fig.update_layout(margin=dict(l=0,r=0,t=55,b=0))
            st.plotly_chart(fig,use_container_width=True)
            st.caption("Country-level choropleth, not a subnational transmission-risk map. Reference years may differ.")
            st.dataframe(latest[["country_label","iso3","year","value","source"]],use_container_width=True,hide_index=True)

elif nav == "Prevention & Health Systems":
    st.subheader("Prevention, vulnerability and health systems")
    groups={"Treatment & prevention":["SH.MLR.TRET.ZS"],"Population & vulnerability":["SP.POP.TOTL","SP.POP.0014.TO.ZS","SH.DYN.MORT"],"Health systems & financing":["SH.XPD.CHEX.GD.ZS","SH.XPD.CHEX.PC.CD"]}
    for group,items in groups.items():
        st.markdown(f"#### {group}")
        available=[x for x in items if x in codes]
        if not available: st.caption("No observations currently available. This does not mean zero coverage.")
        for code in available: line_chart(filter_observations(view,indicator=code),label(code),label(code))
    st.info("These are contextual programme measures, not direct measures of current transmission, diagnosis quality or treatment effectiveness.")


elif nav == "MAP Subnational Intelligence":
    st.subheader("Malaria Atlas Project · national and subnational estimates")
    st.caption("Published modelled estimates from an explicitly selected MAP release. These are not individual case reports or real-time surveillance.")
    st.markdown("#### 1. Select release and geography")
    if not countries:
        st.error("African country metadata is unavailable. Retry after restoring the World Bank country connector.")
    else:
        try:
            releases = map_releases()
            if not releases:
                st.warning("MAP release metadata is currently unavailable.")
            else:
                release_by_label = {
                    f"{r['version']} · through {r['data_end_year']}{' · provisional' if r['provisional'] else ''}": r
                    for r in releases
                }
                release_label = st.selectbox("MAP data release", list(release_by_label))
                release = release_by_label[release_label]
                country_iso = st.selectbox("Country", sorted(country_names), format_func=lambda x: f"{country_names.get(x,x)} ({x})", key="map_country")
                geography = st.radio("Geographic level", ["National","Subnational (admin-1)"], horizontal=True)
                level = "admin0" if geography == "National" else "admin1"
                refs = release.get("geo_server_refs", {})
                available_metrics = []
                for token, meta in MAP_METRICS.items():
                    if refs.get(meta["availability_key"]):
                        available_metrics.append(token)
                if not available_metrics:
                    st.warning("This release does not advertise any of the supported malaria or intervention metrics.")
                else:
                    metric = st.selectbox("Malaria indicator", available_metrics, format_func=lambda x: f"{MAP_METRICS[x]['name']} · {MAP_METRICS[x]['unit']}")
                    admin_choices = []
                    if level == "admin1":
                        if not release.get("admin_version"):
                            st.error("This MAP release does not provide an administrative boundary version.")
                        else:
                            admin_choices = map_admin_units(country_iso, release["admin_version"])
                            if not admin_choices:
                                st.warning("No admin-1 units were returned for this country and boundary release.")
                    if level == "admin0" or admin_choices:
                        if st.button("Load MAP estimates", type="primary"):
                            try:
                                with st.spinner("Retrieving MAP estimates and uncertainty bounds…"):
                                    means = map_series(metric, release["version"], level, country_iso, None, "mean")
                                    result = pd.DataFrame(means)
                                    if level == "admin1":
                                        names = {u["id"]:u["name"] for u in admin_choices}
                                        result["country"] = result["admin1_id"].map(names).fillna(result["country"])
                                        result = result[result["admin1_id"].isin(names)]
                                    if metric not in {"Antimalarial_EFT-rate","IRS_coverage-rate"}:
                                        lower = pd.DataFrame(map_series(metric, release["version"], level, country_iso, None, "lci"))
                                        upper = pd.DataFrame(map_series(metric, release["version"], level, country_iso, None, "uci"))
                                        keys = ["year", "admin1_id"] if level == "admin1" else ["year", "iso3"]
                                        if not lower.empty and not upper.empty:
                                            result = result.merge(lower[keys+["value"]].rename(columns={"value":"lower_bound"}),on=keys,how="left")
                                            result = result.merge(upper[keys+["value"]].rename(columns={"value":"upper_bound"}),on=keys,how="left")
                                    result["country"] = result["country"].replace("", country_names.get(country_iso,country_iso))
                                    st.session_state.map_result = result
                                    st.session_state.map_context = {
                                        "metric":metric,"version":release["version"],"level":level,
                                        "country":country_names.get(country_iso,country_iso),
                                        "provisional":release["provisional"],
                                    }
                            except Exception as exc:
                                st.error(f"MAP retrieval failed: {exc}")
                result = st.session_state.get("map_result")
                context = st.session_state.get("map_context")
                if result is not None and context is not None:
                    if context["provisional"]:
                        st.warning("The selected MAP release is marked provisional.")
                    st.markdown("#### 2. Explore the estimates")
                    st.caption(f"{context['country']} · release {context['version']} · {MAP_METRICS[context['metric']]['name']}")
                    plot = result.copy()
                    fig = px.line(plot, x="year", y="value", color="country" if context["level"]=="admin1" else None,
                                  markers=True, title=MAP_METRICS[context["metric"]]["name"],
                                  labels={"year":"Year","value":MAP_METRICS[context["metric"]]["unit"],"country":"Admin-1 unit"})
                    if {"lower_bound","upper_bound"}.issubset(plot.columns) and context["level"]=="admin0":
                        fig.add_scatter(x=plot.year,y=plot.upper_bound,mode="lines",line=dict(width=0),showlegend=False,hoverinfo="skip")
                        fig.add_scatter(x=plot.year,y=plot.lower_bound,mode="lines",fill="tonexty",line=dict(width=0),name="Published uncertainty range",hoverinfo="skip")
                    fig.update_layout(hovermode="x unified",margin=dict(l=8,r=8,t=55,b=8))
                    st.plotly_chart(fig,use_container_width=True)
                    if "possible_missing_zero" in result and result.possible_missing_zero.any():
                        st.warning("MAP documents that some zero values can indicate unavailable estimates. Review release availability and neighbouring years before interpreting zero as no burden.")
                    st.dataframe(result,use_container_width=True,hide_index=True)
                    st.download_button("Download MAP estimates · CSV",result.to_csv(index=False).encode("utf-8"),"map_malaria_estimates.csv","text/csv")
                    st.caption("MAP estimates are modelled. Lower/upper bounds are shown only where the source provides genuine uncertainty bounds; treatment effectiveness and IRS coverage are point estimates.")
        except Exception as exc:
            st.error(f"MAP services could not be loaded: {exc}")
    st.markdown("**Source and attribution:** Malaria Atlas Project, selected dataset and release. Reuse MAP maps under CC BY 3.0 with the dataset-specific citation and attribution. Third-party source data retains its own licence and citation.")

elif nav == "Forecasting & Risk Analysis":
    st.subheader("Exploratory trend modelling")
    st.warning("Statistical extrapolations only—not outbreak predictions, operational alerts or clinical advice. Weather, vector ecology, interventions and reporting changes are not modelled.")
    if not codes: st.info("No time series available.")
    else:
        code=st.selectbox("Indicator",codes,format_func=label,key="forecast_code")
        candidates=sorted(raw[raw.indicator_code==code].iso3.unique())
        iso=st.selectbox("Country",candidates,format_func=lambda x:f"{country_names.get(x,x)} ({x})")
        horizon=st.slider("Extrapolation horizon",1,5,3)
        if st.button("Run exploratory trend",type="primary"):
            try:
                fc=forecast_linear(raw,code,iso,horizon)
                hist=raw[(raw.indicator_code==code)&(raw.iso3==iso)&raw.value.notna()][["year","value"]].copy()
                hist["series"]="Historical"; future=fc[["year","forecast"]].rename(columns={"forecast":"value"}); future["series"]="Linear extrapolation"
                fig=px.line(pd.concat([hist,future]),x="year",y="value",color="series",markers=True,title=f"{country_names.get(iso,iso)} · {label(code)}")
                st.plotly_chart(fig,use_container_width=True); st.metric("In-sample RMSE",f"{fc.rmse_in_sample.iloc[0]:,.3g}")
                st.dataframe(fc,use_container_width=True,hide_index=True)
            except Exception as exc: st.error(str(exc))

elif nav == "AI Malaria Analyst":
    st.subheader("Model-free Malaria Analyst")
    st.caption("Calculates answers from loaded data. It does not invent unavailable facts or use a generative model.")
    if "ami_messages" not in st.session_state: st.session_state.ami_messages=[]
    for msg in st.session_state.ami_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    prompt=st.chat_input("Ask about incidence, cases, deaths, a country or a trend…")
    if prompt:
        st.session_state.ami_messages.append({"role":"user","content":prompt})
        st.session_state.ami_messages.append({"role":"assistant","content":answer_data_question(raw,prompt,country_names)})
        st.rerun()
    if st.button("Clear conversation"): st.session_state.ami_messages=[]; st.rerun()

elif nav == "Reports & Downloads":
    st.subheader("Reports and data exports")
    if raw.empty: st.info("No observations available to export.")
    else:
        export=filter_observations(raw,countries=selected_iso or None,start_year=year_range[0],end_year=year_range[1])
        st.metric("Rows in current export",f"{len(export):,}")
        st.dataframe(export.head(1000),use_container_width=True,hide_index=True)
        st.download_button("Download filtered data · CSV",export.to_csv(index=False).encode("utf-8"),"africa_malaria_observations.csv","text/csv",use_container_width=True)
        try: st.download_button("Download filtered data · Excel",excel_bytes(export),"africa_malaria_observations.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        except Exception as exc: st.warning(f"Excel export unavailable: {exc}")
        summary=export.groupby(["indicator_code","source"],dropna=False).agg(observations=("value","count"),countries=("iso3","nunique"),first_year=("year","min"),last_year=("year","max")).reset_index()
        st.markdown("#### Export summary"); st.dataframe(summary,use_container_width=True,hide_index=True)

elif nav == "Data Quality & Sources":
    st.subheader("Data quality, provenance and connector health")
    a,b,c,d=st.columns(4)
    a.metric("Rows",f"{quality['rows']:,}"); b.metric("Missing values",f"{quality['missing_values']:,}")
    c.metric("Countries",f"{quality['countries']:,}"); d.metric("Duplicate keys removed",f"{quality['duplicate_keys_removed']:,}")
    st.markdown("#### World Bank connector status")
    if statuses: st.dataframe(pd.DataFrame(statuses),use_container_width=True,hide_index=True)
    else: st.info("No connector status returned.")
    st.markdown("#### Open source catalogue")
    for name,url in SOURCE_LINKS.items(): st.markdown(f"- [{name}]({url})")
    st.markdown("#### WHO GHO malaria indicator discovery")
    if st.button("Discover WHO malaria indicators"):
        try:
            st.session_state.who_catalogue = who_catalogue()
        except DataSourceError as exc: st.error(f"WHO GHO unavailable: {exc}")
    catalogue = st.session_state.get("who_catalogue", [])
    if catalogue:
        st.dataframe(pd.DataFrame(catalogue),use_container_width=True,hide_index=True)
        chosen = st.selectbox("WHO GHO indicator to retrieve", catalogue, format_func=lambda x: f"{x['name']} ({x['code']})", key="who_indicator_choice")
        if st.button("Fetch selected WHO indicator observations"):
            try:
                who_rows = fetch_who_gho_indicator(chosen["code"])
                africa_codes = set(country_names)
                who_rows = [r for r in who_rows if r["iso3"] in africa_codes]
                st.session_state.who_rows = who_rows
                st.success(f"Retrieved {len(who_rows):,} WHO observations for African countries. Revisit this workspace to include them in the analytical views.")
            except Exception as exc: st.error(f"WHO indicator retrieval failed: {exc}")
    st.markdown("#### Interpretation safeguards")
    st.markdown("- Modelled estimates, reported counts and contextual health indicators are not interchangeable.\n- Latest years may differ across countries.\n- Missing values are not zero.\n- Country-level statistics do not establish subnational outbreak conditions.\n- This is a research and programme-intelligence tool, not a diagnostic or treatment system.")
    st.caption(f"Rendered {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Cached public observations may be up to 24 hours old.")

st.divider()
st.caption("Africa Malaria Intelligence · Open-data research platform · Not a real-time case surveillance system · Verify source definitions before policy use.")
