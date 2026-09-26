# Career Evidence & Interview Coach

Generic Streamlit application for evidence-based career management and interview preparation.

## Features

- Private Supabase-backed user workspaces
- Master career evidence record
- Strengths and gaps tracking
- STAR evidence builder
- Job posting upload and evidence-match review
- Job-specific practice sessions
- Resume-defense practice
- Evidence-only resume generation
- Workspace backup and restore

## Privacy

This public repository contains application code only. Personal career data belongs in the authenticated Supabase workspace and should never be committed to GitHub.

## Streamlit Community Cloud

Deploy with:

- Repository: `simforia/career-evidence-interview-coach`
- Branch: `main`
- Main file path: `app.py`

Configure these values in Streamlit **Secrets**:

```toml
SUPABASE_URL="https://YOUR_PROJECT.supabase.co"
SUPABASE_PUBLISHABLE_KEY="YOUR_PUBLISHABLE_KEY"
```

Do not commit actual secret values to this repository.

## Local run

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
