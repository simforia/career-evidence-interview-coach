import streamlit as st

from career_app.storage import get_client, require_auth, load_workspace, save_workspace

st.set_page_config(page_title="Profile & Goals", page_icon="👤", layout="wide")

client = get_client()
user_id = require_auth(client)

if "workspace" not in st.session_state:
    st.session_state.workspace = load_workspace(client, user_id)
workspace = st.session_state.workspace

st.title("Profile & Goals")
st.caption("These settings drive nearby job searches and help keep recommendations aligned with your current career stage.")

candidate = workspace.setdefault("candidate", {})
cfg = workspace.setdefault("job_search_config", {})

with st.form("profile_goals"):
    a,b = st.columns(2)
    with a:
        name = st.text_input("Name", value=candidate.get("name",""))
        location = st.text_input("Job-search center", value=cfg.get("location") or candidate.get("location",""))
        radius = st.slider("Default search radius (miles)", 10, 100, int(cfg.get("radius_miles",50)), 5)
    with b:
        stages = [
            "High school / pre-career",
            "College or training student",
            "New graduate",
            "Entry-level",
            "Early career (1–3 years)",
            "Experienced",
            "Career change",
        ]
        current = candidate.get("experience_level","New graduate")
        stage_index = stages.index(current) if current in stages else 2
        stage = st.selectbox("Current career stage", stages, index=stage_index)
        min_fit = st.slider("Minimum job-search evidence-fit signal", 0, 60, int(cfg.get("min_fit_score",15)), 5)
        auto_daily = st.checkbox("Refresh job search once per day when opened", value=cfg.get("auto_daily",True))

    roles = st.text_area(
        "Target job families — one per line",
        value="\n".join(cfg.get("roles",[])),
        height=180,
        placeholder="Data Center Technician\nIT Support Technician\nCybersecurity Analyst"
    )

    if st.form_submit_button("Save profile and goals", type="primary", use_container_width=True):
        if not name.strip() or not location.strip():
            st.error("Name and job-search center are required.")
        else:
            candidate["name"] = name.strip()
            candidate["location"] = location.strip()
            candidate["experience_level"] = stage
            cfg["location"] = location.strip()
            cfg["radius_miles"] = radius
            cfg["roles"] = [x.strip() for x in roles.splitlines() if x.strip()]
            cfg["min_fit_score"] = min_fit
            cfg["auto_daily"] = auto_daily
            workspace["onboarding_complete"] = True
            save_workspace(client,user_id,workspace)
            st.success("Profile and job-search goals saved.")
