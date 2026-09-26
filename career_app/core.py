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

def add_log(workspace, kind, title, body="", job_id=None, session_id=None):
    workspace.setdefault("practice_log", []).append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind, "title": title, "body": body,
        "job_id": job_id, "session_id": session_id,
    })
