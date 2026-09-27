from datetime import datetime
import streamlit as st

from career_app.storage import get_client, require_auth, load_workspace, save_workspace
from career_app.core import search_live_jobs, build_practice_questions, add_log

st.set_page_config(page_title="Daily Job Search", page_icon="🔎", layout="wide")

client = get_client()
user_id = require_auth(client)

if "workspace" not in st.session_state:
    st.session_state.workspace = load_workspace(client, user_id)
workspace = st.session_state.workspace

st.title("Daily Job Search")
st.caption("Current openings near the candidate, ranked against verified career evidence.")

cfg = workspace.setdefault("job_search_config", {
    "location": workspace.get("candidate", {}).get("location", "Jessup, PA") or "Jessup, PA",
    "radius_miles": 50,
    "roles": [
        "data center technician",
        "network technician",
        "IT support technician",
        "infrastructure technician",
        "cybersecurity analyst",
        "field service technician",
    ],
    "auto_daily": True,
    "min_fit_score": 15,
})

left, right = st.columns(2)
with left:
    cfg["location"] = st.text_input("Search center", cfg.get("location", "Jessup, PA"))
    cfg["radius_miles"] = st.slider("Radius", 10, 100, int(cfg.get("radius_miles", 50)), 5)
with right:
    cfg["auto_daily"] = st.checkbox("Refresh once per day when this page is opened", cfg.get("auto_daily", True))
    cfg["min_fit_score"] = st.slider("Minimum evidence-fit signal", 0, 60, int(cfg.get("min_fit_score", 15)), 5)

roles = st.text_area(
    "Role families — one per line",
    "\n".join(cfg.get("roles", [])),
    height=150,
)
cfg["roles"] = [x.strip() for x in roles.splitlines() if x.strip()]

try:
    app_id = st.secrets.get("ADZUNA_APP_ID", "")
    app_key = st.secrets.get("ADZUNA_APP_KEY", "")
except Exception:
    app_id = ""
    app_key = ""

ready = bool(app_id and app_key)
if not ready:
    st.warning("Adzuna credentials are not configured in Streamlit Secrets.")

today = datetime.now().date().isoformat()
last_run = workspace.get("daily_job_search_last_run", "")
manual = st.button("Search now", type="primary", use_container_width=True)
auto = cfg.get("auto_daily", True) and ready and last_run != today

if ready and (manual or auto):
    if not cfg["roles"]:
        st.error("Add at least one role family.")
    else:
        with st.spinner("Searching current openings and ranking them against verified evidence..."):
            results, error = search_live_jobs(
                app_id,
                app_key,
                cfg["location"],
                cfg["radius_miles"],
                cfg["roles"],
                workspace,
            )
        if error:
            st.error(error)
        else:
            workspace["daily_job_results"] = results
            workspace["daily_job_search_last_run"] = today
            add_log(workspace, "daily_job_search", "Ran nearby job search", f"{len(results)} listings retrieved")
            save_workspace(client, user_id, workspace)
            st.success(f"Search complete: {len(results)} unique listings retrieved.")

results = workspace.get("daily_job_results", [])
visible = [
    x for x in results
    if not x.get("senior_mismatch", False)
    and x.get("fit_score", 0) >= cfg.get("min_fit_score", 15)
]

if results:
    st.write(f"**{len(visible)} likely-fit listings** from the latest search.")
    st.caption("Fit is an evidence-matching signal, not a prediction that an employer will hire the candidate.")

for i, item in enumerate(visible[:40]):
    company = item.get("company", "Unknown")
    title = item.get("title", "Job")
    label = f"{item.get('fit_score', 0)}% fit — {company} — {title}"

    with st.expander(label):
        st.write(f"**Location:** {item.get('location', '')}")
        if item.get("created"):
            st.write(f"**Posted:** {item['created']}")
        if item.get("salary_min") or item.get("salary_max"):
            st.write(f"**Salary shown:** {item.get('salary_min') or '—'} to {item.get('salary_max') or '—'}")

        st.write("**Supported evidence terms:** " + (", ".join(item.get("matched", [])[:20]) or "None detected"))
        st.write("**Potential gaps:** " + (", ".join(item.get("gaps", [])[:15]) or "None detected"))

        if item.get("description"):
            st.write(item["description"][:1200])
        if item.get("url"):
            st.link_button("Open listing", item["url"])

        a, b = st.columns(2)

        if a.button("Save to Job Review", key=f"save_job_{i}", use_container_width=True):
            job_id = f"job-{len(workspace.get('jobs', [])) + 1}"
            workspace.setdefault("jobs", []).append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": item.get("location", ""),
                "text": item.get("description", ""),
                "score": item.get("evidence_score", 0),
                "matched": item.get("matched", []),
                "gaps": item.get("gaps", []),
                "created": datetime.now().isoformat(timespec="seconds"),
                "source_url": item.get("url", ""),
            })
            add_log(workspace, "job_saved", f"{company} — {title}", "Saved from Daily Job Search", job_id=job_id)
            save_workspace(client, user_id, workspace)
            st.success("Saved to Job Review.")

        if b.button("Save + create mock interview", key=f"practice_job_{i}", use_container_width=True):
            job_id = f"job-{len(workspace.get('jobs', [])) + 1}"
            workspace.setdefault("jobs", []).append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": item.get("location", ""),
                "text": item.get("description", ""),
                "score": item.get("evidence_score", 0),
                "matched": item.get("matched", []),
                "gaps": item.get("gaps", []),
                "created": datetime.now().isoformat(timespec="seconds"),
                "source_url": item.get("url", ""),
            })

            questions = build_practice_questions(workspace, "job", job_id, "Mixed mock")[:8]
            session_id = f"session-{len(workspace.get('sessions', [])) + 1}"
            workspace.setdefault("sessions", []).append({
                "id": session_id,
                "source_type": "job",
                "source_id": job_id,
                "job_id": job_id,
                "title": f"{company} — {title}",
                "mode": "Mixed mock",
                "input_mode": "Voice",
                "questions": questions,
                "question_index": 0,
                "answers": {},
                "evaluations": {},
                "created": datetime.now().isoformat(timespec="seconds"),
            })
            add_log(workspace, "session", "Created mock interview from job search", title, job_id, session_id)
            save_workspace(client, user_id, workspace)
            st.success("Job saved and mock interview created. Open the main app and choose Practice Sessions.")
