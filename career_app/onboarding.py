import re
from datetime import datetime
import streamlit as st

from .core import extract_text, add_log


HEADER_WORDS = {
    "summary","skills","experience","education","certifications","certificates",
    "projects","employment","work experience","technical skills","objective",
    "professional summary","qualifications","awards","references"
}


def needs_onboarding(workspace):
    candidate = workspace.get("candidate", {}) or {}
    if workspace.get("onboarding_complete"):
        return False
    if candidate.get("name"):
        return False
    if workspace.get("master_facts") or workspace.get("jobs") or workspace.get("sessions"):
        return False
    return True


def _resume_suggestions(text):
    suggestions = []
    seen = set()
    for raw in (text or "").splitlines():
        line = re.sub(r"^[\s•●▪◦*\-–—]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if not line or len(line) < 12 or len(line) > 320:
            continue
        low = line.lower().strip(":")
        if low in HEADER_WORDS:
            continue
        if "@" in line or re.search(r"https?://|www\.", low):
            continue
        if re.fullmatch(r"[\d\s().+\-]{7,}", line):
            continue
        if line.upper() == line and len(line.split()) <= 6:
            continue

        if any(x in low for x in ["bachelor", "associate degree", "master of", "b.s.", "b.a.", "a.s.", "a.a.", "degree", "university", "college"]):
            category = "Education"
        elif any(x in low for x in ["comptia", "certified", "certification", "certificate", "cissp", "ccna", "itil", "isc2", "aws certified", "azure fundamentals"]):
            category = "Certification"
        elif any(x in low for x in ["python", "linux", "windows", "network", "cyber", "server", "hardware", "software", "sql", "cloud", "security", "support"]):
            category = "Experience"
        else:
            category = "Experience"

        key = (category, low)
        if key not in seen:
            seen.add(key)
            suggestions.append({"category": category, "fact": line})
        if len(suggestions) >= 35:
            break
    return suggestions


def _lines(text):
    return [re.sub(r"^[\s•●▪◦*\-–—]+", "", x).strip() for x in (text or "").splitlines() if x.strip()]


def render_onboarding(client, user_id, workspace, save_fn):
    st.title("Set up your career workspace")
    st.caption("This takes a few minutes. Your answers create the starting point for job matching, resume evidence, and interview practice.")

    with st.form("onboarding_form"):
        st.subheader("1. About you")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Name", placeholder="First and last name")
            location = st.text_input(
                "Job-search center",
                placeholder="City, State or ZIP",
                help="Used for nearby job searches. You can change it later."
            )
        with c2:
            experience = st.selectbox(
                "Current career stage",
                [
                    "High school / pre-career",
                    "College or training student",
                    "New graduate",
                    "Entry-level",
                    "Early career (1–3 years)",
                    "Experienced",
                    "Career change",
                ],
                index=2,
            )
            radius = st.slider("Default job-search radius (miles)", 10, 100, 50, 5)

        st.subheader("2. What kind of work are you looking for?")
        targets = st.text_area(
            "Target job families — one per line",
            placeholder="Example:\nData Center Technician\nNetwork Technician\nCybersecurity Analyst",
            height=130,
            help="Use broad role families rather than one exact posting."
        )

        st.subheader("3. Education and certifications")
        e1, e2 = st.columns(2)
        with e1:
            education = st.text_area(
                "Education — one item per line",
                placeholder="B.S. Cybersecurity — Example University — 2026",
                height=130,
            )
        with e2:
            certs = st.text_area(
                "Certifications / licenses — one item per line",
                placeholder="CompTIA Security+\nOSHA 10\nFAA Part 107",
                height=130,
            )
        confirm = st.checkbox(
            "I confirm the education and certification items I entered above are accurate.",
            value=False,
        )

        st.subheader("4. Optional resume import")
        resume = st.file_uploader(
            "Upload an existing resume",
            type=["txt","md","docx","pdf"],
            help="The resume stays in your private authenticated workspace. Extracted claims are staged as unverified until you review them."
        )
        import_resume = st.checkbox(
            "Stage useful resume lines as unverified career facts for me to review",
            value=True,
        )

        submitted = st.form_submit_button("Create my workspace", type="primary", use_container_width=True)

    if not submitted:
        st.info("Nothing is saved until you click **Create my workspace**.")
        return

    if not name.strip():
        st.error("Enter your name.")
        return
    if not location.strip():
        st.error("Enter a city, state, or ZIP for the job-search center.")
        return

    target_roles = _lines(targets)
    edu_lines = _lines(education)
    cert_lines = _lines(certs)

    workspace["candidate"] = {
        "name": name.strip(),
        "location": location.strip(),
        "experience_level": experience,
    }
    workspace["job_search_config"] = {
        "location": location.strip(),
        "radius_miles": radius,
        "roles": target_roles,
        "auto_daily": True,
        "min_fit_score": 15,
    }

    facts = workspace.setdefault("master_facts", [])
    existing = {(x.get("category",""), x.get("fact","").lower()) for x in facts}

    for fact in edu_lines:
        item = ("Education", fact.lower())
        if item not in existing:
            facts.append({
                "category": "Education",
                "fact": fact,
                "source": "Onboarding",
                "verified": bool(confirm),
            })
            existing.add(item)

    for fact in cert_lines:
        item = ("Certification", fact.lower())
        if item not in existing:
            facts.append({
                "category": "Certification",
                "fact": fact,
                "source": "Onboarding",
                "verified": bool(confirm),
            })
            existing.add(item)

    if resume is not None:
        resume_text = extract_text(resume)
        workspace["resume_intake"] = {
            "filename": resume.name,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
            "text": resume_text,
        }
        if import_resume and resume_text:
            for suggestion in _resume_suggestions(resume_text):
                item = (suggestion["category"], suggestion["fact"].lower())
                if item not in existing:
                    facts.append({
                        "category": suggestion["category"],
                        "fact": suggestion["fact"],
                        "source": f"Resume import: {resume.name}",
                        "verified": False,
                    })
                    existing.add(item)

    workspace["onboarding_complete"] = True
    workspace["onboarding_completed_at"] = datetime.now().isoformat(timespec="seconds")
    workspace["version"] = max(int(workspace.get("version", 1)), 5)

    add_log(
        workspace,
        "onboarding",
        "Completed first-time setup",
        f"Career stage: {experience}; target roles: {len(target_roles)}; initial facts: {len(facts)}"
    )
    save_fn(client, user_id, workspace)
    st.session_state.workspace = workspace
    st.success("Workspace created.")
    st.rerun()
