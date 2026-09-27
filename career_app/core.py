import io, re, requests
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

def search_live_jobs(app_id, app_key, location, radius_miles, roles, workspace, results_per_role=20):
    if not app_id or not app_key:
        return [], "Adzuna credentials are not configured."

    senior_markers = {
        "senior","sr.","sr ","lead","principal","manager","director","architect",
        "staff engineer","level 4","level iv","level 5","level v"
    }
    seen = set()
    ranked = []

    for role in roles:
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": results_per_role,
            "what": role,
            "where": location,
            "distance": radius_miles,
            "sort_by": "date",
            "content-type": "application/json",
        }
        try:
            response = requests.get(
                "https://api.adzuna.com/v1/api/jobs/us/search/1",
                params=params,
                headers={"Accept":"application/json"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return ranked, f"Live job search failed: {exc}"

        for item in payload.get("results", []):
            title = (item.get("title") or "").strip()
            company = ((item.get("company") or {}).get("display_name") or "Unknown").strip()
            url = item.get("redirect_url") or ""
            key = (title.lower(), company.lower(), url)
            if key in seen:
                continue
            seen.add(key)

            description = (item.get("description") or "").strip()
            score, matched, gaps = assess_job(f"{title}\n{description}", workspace)
            lower_title = title.lower()
            senior_flag = any(marker in lower_title for marker in senior_markers)

            loc = ((item.get("location") or {}).get("display_name") or "").strip()
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            created = item.get("created")

            fit_score = max(0, score - (25 if senior_flag else 0))
            ranked.append({
                "source": "Adzuna",
                "title": title,
                "company": company,
                "location": loc,
                "url": url,
                "description": description,
                "created": created,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "matched": matched,
                "gaps": gaps,
                "evidence_score": score,
                "fit_score": fit_score,
                "senior_mismatch": senior_flag,
                "search_role": role,
            })

    ranked.sort(key=lambda x: (x.get("senior_mismatch",False), -x.get("fit_score",0), x.get("created") or ""))
    return ranked, None

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

def evaluate_practice_answer(answer, mode="Mixed mock", question=""):
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

    result = {
        "score": score,
        "label": label,
        "feedback": feedback,
        "weak_areas": weak,
        "followup": followup,
    }
    result["coaching"] = coach_interview_answer(question, text, result)
    return result

def _split_sentences(text):
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]

def _remove_speech_fillers(sentence):
    s = sentence.strip()
    s = re.sub(r"^(um+|uh+|erm+)[, ]+", "", s, flags=re.I)
    s = re.sub(r"\b(you know|I mean)\b[, ]*", "", s, flags=re.I)
    s = re.sub(r"\b(basically|essentially)\b[, ]*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    if s:
        s = s[0].upper() + s[1:]
    return s

def coach_interview_answer(question, answer, evaluation):
    text = (answer or "").strip()
    sentences = [_remove_speech_fillers(s) for s in _split_sentences(text)]
    sentences = [s for s in sentences if s]
    lower_sentences = [s.lower() for s in sentences]

    action_words = [
        "configured","tested","checked","traced","installed","replaced","isolated",
        "reviewed","verified","troubleshot","built","changed","documented","used",
        "created","set up","diagnosed","connected","removed","updated","researched",
        "compared","reset","rebooted","measured","found","identified"
    ]
    result_words = [
        "result","resolved","fixed","worked","verified","confirmed","reduced","improved",
        "successful","restored","prevented","solved","passed","stable","working","completed"
    ]
    reflection_words = [
        "learned","next time","after that","since then","would do","lesson","taught me",
        "realized","now I","from that"
    ]

    used = set()
    result_idx = [
        i for i,s in enumerate(lower_sentences)
        if any(word in s for word in result_words)
    ]
    reflection_idx = [
        i for i,s in enumerate(lower_sentences)
        if any(word.lower() in s for word in reflection_words)
    ]
    action_idx = [
        i for i,s in enumerate(lower_sentences)
        if (" i " in f" {s} " or s.startswith("i ") or " my " in f" {s} ")
        and any(word in s for word in action_words)
    ]

    context_idx = []
    for i,s in enumerate(sentences):
        if i not in result_idx and i not in reflection_idx and i not in action_idx:
            context_idx.append(i)
            break
    if not context_idx and sentences:
        context_idx = [0]

    ordered = []
    for group in [context_idx, action_idx, result_idx, reflection_idx]:
        for i in group:
            if i not in used and i < len(sentences):
                ordered.append(sentences[i])
                used.add(i)
    for i,s in enumerate(sentences):
        if i not in used:
            ordered.append(s)

    suggested = " ".join(ordered).strip()
    if suggested and suggested[-1] not in ".!?":
        suggested += "."

    weak = set(evaluation.get("weak_areas", []))
    improvements = []
    if "depth" in weak:
        improvements.append("Add enough context for the interviewer to understand the problem before jumping into the fix.")
    if "ownership" in weak:
        improvements.append("Make your personal ownership unmistakable: say what you decided, checked, changed, or verified.")
    if "technical_detail" in weak:
        improvements.append("Name the actual troubleshooting steps, tools, settings, or tests you used.")
    if "result" in weak:
        improvements.append("Finish with the outcome and how you knew the fix worked. Do not invent a metric if you did not measure one.")
    if "specificity" in weak:
        improvements.append("Add one concrete detail from the real event—device, setting, error, scale, test, or observed behavior.")
    if "reflection" in weak:
        improvements.append("For behavioral questions, close with the lesson learned or what you would repeat next time.")
    if not improvements:
        improvements.append("Keep the same evidence, but deliver it more directly: brief context, your actions, verified result, then stop.")

    score = evaluation.get("score", 0)
    if score >= 85:
        opening = "Strong answer. The evidence is clear. A tighter delivery will make it sound more confident and easier for the interviewer to follow."
    elif score >= 70:
        opening = "Good answer. The substance is there; this will land better if you tighten the setup, emphasize what you personally did, and close on the result."
    elif score >= 55:
        opening = "There is a solid example here. It needs a cleaner structure and more concrete evidence before it will have maximum interview impact."
    else:
        opening = "You have the start of a usable answer, but the interviewer still needs clearer evidence of what happened, what you personally did, and what changed."

    missing = []
    if "result" in weak:
        missing.append("verified result")
    if "technical_detail" in weak:
        missing.append("specific technical actions")
    if "ownership" in weak:
        missing.append("clear personal ownership")
    if "specificity" in weak:
        missing.append("concrete detail")
    if "reflection" in weak:
        missing.append("lesson learned / reflection")

    return {
        "opening": opening,
        "suggested_answer": suggested or text,
        "improvements": improvements,
        "missing": missing,
        "guardrail": "Suggested wording is built only from the answer you gave. Add missing details only if they are true and you can defend them under follow-up.",
    }

def add_log(workspace, kind, title, body="", job_id=None, session_id=None):
    workspace.setdefault("practice_log", []).append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind, "title": title, "body": body,
        "job_id": job_id, "session_id": session_id,
    })
