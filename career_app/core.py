import io, re
from datetime import datetime

try:
    from docx import Document
except Exception:
    Document = None
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

STOP = set("a an and are as at be been but by can could did do does for from had has have how i if in into is it its may my of on or our should so than that the their then there these they this to was we were what when where which who why will with would you your".split())

BEHAVIORAL = [
    "Tell me about a time you had to troubleshoot a technical problem you had never seen before.",
    "Tell me about a time you took ownership of a problem that was not fully defined.",
    "Tell me about a time you made a mistake. What did you do next?",
    "Tell me about a time you had to learn something quickly to complete a task.",
    "Tell me about a time you had to explain a technical problem to someone who was not technical.",
    "Tell me about a time you used evidence, logs, testing, or measurements to find a root cause.",
    "Tell me about a time attention to detail prevented or corrected a problem.",
    "Tell me about a time you received feedback and changed your approach.",
]

def extract_text(upload):
    raw = upload.getvalue()
    name = upload.name.lower()
    if name.endswith((".txt", ".md")):
        return raw.decode("utf-8", errors="ignore")
    if name.endswith(".docx") and Document:
        doc = Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)
    if name.endswith(".pdf") and PdfReader:
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return ""

def tokens(text):
    return {w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#./-]{2,}", text.lower()) if w not in STOP}

def evidence_text(workspace):
    bits = [x["fact"] for x in workspace.get("master_facts", []) if x.get("verified")]
    bits += [s.get("action", "") + " " + s.get("result", "") for s in workspace.get("stories", []) if s.get("action") or s.get("result")]
    return " ".join(bits)

def assess_job(text, workspace):
    job_terms = tokens(text)
    evidence_terms = tokens(evidence_text(workspace))
    overlap = sorted(job_terms & evidence_terms)
    missing = sorted(job_terms - evidence_terms)
    score = min(100, round((len(overlap) / max(1, min(len(job_terms), 60))) * 100))
    return score, overlap[:40], missing[:30]

def targeted_resume(job, workspace):
    target_terms = tokens((job or {}).get("text", ""))
    ranked = []
    for item in workspace.get("master_facts", []):
        if item.get("verified"):
            ranked.append((len(tokens(item["fact"]) & target_terms), item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    selected = [item for score, item in ranked if score > 0][:14]
    if len(selected) < 10:
        for _, item in ranked:
            if item not in selected:
                selected.append(item)
            if len(selected) >= 10:
                break
    name = workspace.get("candidate", {}).get("name", "Candidate")
    lines = [name.upper(), f"Target: {(job or {}).get('title', 'Selected Role')}", "", "VERIFIED QUALIFICATIONS"]
    lines += [f"• {x['fact']}" for x in selected]
    lines += ["", "EDUCATION & CERTIFICATIONS"]
    lines += [f"• {x['fact']}" for x in workspace.get("master_facts", []) if x.get("verified") and x.get("category") in ("Education", "Certification")]
    lines += ["", "NOTE: Generated only from verified evidence. Review wording before submission."]
    return "\n".join(lines)

def build_practice_questions(workspace, source_type, source_id, mode):
    verified = [x["fact"] for x in workspace.get("master_facts", []) if x.get("verified")]
    profiles = workspace.get("interview_profiles", {})
    jobs = workspace.get("jobs", [])
    focus = []
    gaps = []
    title = ""

    if source_type == "profile":
        profile = profiles.get(source_id, {})
        title = source_id
        focus = profile.get("focus", [])
    else:
        job = next((j for j in jobs if j.get("id") == source_id), {})
        title = f"{job.get('company','')} — {job.get('title','Job')}".strip(" —")
        gaps = job.get("gaps", [])
        focus = job.get("matched", [])[:10]

    behavioral = list(BEHAVIORAL)
    resume_defense = [
        f"Your resume says: {fact} Walk me through one specific example that proves this."
        for fact in verified[:25]
    ] or ["Choose one technical claim from your resume and prove it with a specific example."]

    job_specific = []
    for item in focus[:12]:
        job_specific.append(
            f"This role emphasizes {item}. What have you personally done that is relevant, and how would you apply it here?"
        )
    for item in gaps[:8]:
        job_specific.append(
            f"This role references {item}. What can you honestly claim today, what can you not claim, and how would you close the gap?"
        )
    if not job_specific:
        job_specific = [
            f"For {title or 'this role'}, which technical requirement is your strongest fit? Give a concrete example.",
            f"For {title or 'this role'}, which requirement would require the most learning, and how would you approach it?"
        ]

    if mode == "Behavioral / STAR":
        return behavioral
    if mode == "Resume defense":
        return resume_defense
    if mode == "Job-specific":
        return job_specific

    mixed = []
    pools = [behavioral, job_specific, resume_defense]
    longest = max(len(p) for p in pools)
    for i in range(longest):
        for pool in pools:
            if i < len(pool):
                mixed.append(pool[i])
    return mixed

def evaluate_practice_answer(answer, mode="Mixed mock"):
    text = (answer or "").strip()
    words = text.split()
    lower = text.lower()
    score = 0
    feedback = []
    weak = []

    if len(words) >= 80:
        score += 20
    elif len(words) >= 40:
        score += 14
    elif len(words) >= 20:
        score += 8
    else:
        feedback.append("Answer is too short to establish context, action, and result.")
        weak.append("depth")

    ownership_terms = ["i ", "i'd ", "i would", "my ", "personally"]
    if any(term in lower for term in ownership_terms):
        score += 20
    else:
        feedback.append("Use first-person ownership so the interviewer knows what you personally did.")
        weak.append("ownership")

    action_terms = ["configured","tested","checked","traced","installed","replaced","isolated","reviewed","verified","troubleshot","built","changed","documented","used"]
    if sum(1 for term in action_terms if term in lower) >= 2:
        score += 20
    else:
        feedback.append("Add concrete technical actions, tools, commands, tests, or decision steps.")
        weak.append("technical_detail")

    result_terms = ["result","resolved","fixed","worked","verified","confirmed","reduced","improved","successful","restored","prevented"]
    if any(term in lower for term in result_terms):
        score += 20
    else:
        feedback.append("State the result and how you verified that it worked.")
        weak.append("result")

    reflection_terms = ["learned","next time","after that","since then","would do","improved my","lesson"]
    if any(term in lower for term in reflection_terms):
        score += 10
    elif mode == "Behavioral / STAR" or mode == "Mixed mock":
        feedback.append("Add what you learned or what you would do differently.")
        weak.append("reflection")
    else:
        score += 5

    specificity = bool(re.search(r"\b\d+\b", text)) or any(ch in text for ch in ["/",":"])
    if specificity:
        score += 10
    else:
        feedback.append("Use one or two concrete specifics where appropriate: scale, tool, setting, test, or measurable result.")
        weak.append("specificity")

    score = min(100, score)
    if score >= 85:
        label = "Strong"
    elif score >= 70:
        label = "Interview-ready with minor tightening"
    elif score >= 55:
        label = "Developing"
    else:
        label = "Needs another pass"

    if not feedback:
        feedback.append("Clear, specific, evidence-based answer. Keep it concise under follow-up pressure.")

    if "result" in weak:
        followup = "How did you verify the problem was actually resolved?"
    elif "technical_detail" in weak:
        followup = "What exact steps, tools, commands, or tests did you personally use?"
    elif "ownership" in weak:
        followup = "Which parts were specifically your responsibility, and what did you personally decide or do?"
    elif "specificity" in weak:
        followup = "Give me one concrete detail that proves this happened: scale, setting, device, error, test, or outcome."
    elif "reflection" in weak:
        followup = "What did you learn, and what would you do differently next time?"
    else:
        followup = "What was the hardest follow-up question an interviewer could ask about this example, and how would you answer it?"

    return {
        "score": score,
        "label": label,
        "feedback": feedback,
        "weak_areas": weak,
        "followup": followup,
    }

def add_log(workspace, kind, title, body="", job_id=None, session_id=None):
    workspace.setdefault("practice_log", []).append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind, "title": title, "body": body,
        "job_id": job_id, "session_id": session_id,
    })
