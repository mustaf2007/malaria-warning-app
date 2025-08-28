import streamlit as st

def malaria_early_warning(rainfall_mm, keyword_increase, rdt_positivity):
    rainfall_threshold = 75
    keyword_threshold = 30
    rdt_threshold = 25

    if rainfall_mm > rainfall_threshold and keyword_increase > keyword_threshold and rdt_positivity > rdt_threshold:
        return "🔴 HIGH RISK - Immediate Intervention Needed"
    elif (rainfall_mm > rainfall_threshold and keyword_increase > keyword_threshold) or (rdt_positivity > rdt_threshold):
        return "🟠 MEDIUM RISK - Monitor Closely and Prepare Response"
    elif keyword_increase > 20:
        return "🟡 LOW RISK - Watch Public Sentiment and Weather Trends"
    else:
        return "🟢 NO ALERT - Situation Normal"

st.set_page_config(page_title="Malaria Early Warning System", layout="centered")

st.title("🦟 Malaria Early Warning System - Somalia")
st.markdown("Enter the latest health and environmental data to assess malaria outbreak risk.")

rainfall_mm = st.number_input("🌧️ Rainfall (last 5 days, mm)", min_value=0.0, value=60.0)
keyword_increase = st.number_input("📈 Keyword Increase (% compared to last week)", min_value=0.0, value=25.0)
rdt_positivity = st.number_input("🧪 RDT Positivity Rate (%)", min_value=0.0, value=20.0)

if st.button("🔍 Predict Risk Level"):
    alert = malaria_early_warning(rainfall_mm, keyword_increase, rdt_positivity)
    st.subheader("Prediction Result:")
    st.success(alert) if "🟢" in alert else st.warning(alert) if "🟡" in alert else st.error(alert)
