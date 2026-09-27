import os
import streamlit as st
from datetime import datetime
from supabase import create_client

def _secret(name):
    try:
        return os.getenv(name) or st.secrets.get(name, "")
    except Exception:
        return os.getenv(name, "")

def get_client():
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        st.error("Supabase is not configured. Add SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY to Streamlit secrets.")
        st.stop()
    if "supabase_client" not in st.session_state:
        st.session_state.supabase_client = create_client(url, key)
    return st.session_state.supabase_client

def require_auth(client):
    if st.session_state.get("authenticated") and st.session_state.get("user_id"):
        return st.session_state.user_id

    st.title("Career Evidence & Interview Coach")
    st.caption("Sign in to your private workspace.")
    sign_in, create_account = st.tabs(["Sign in", "Create account"])

    with sign_in:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Sign in", type="primary", use_container_width=True):
            try:
                response = client.auth.sign_in_with_password({"email": email, "password": password})
                if response.user:
                    st.session_state.authenticated = True
                    st.session_state.user_id = str(response.user.id)
                    st.rerun()
            except Exception as exc:
                st.error(f"Sign-in failed: {exc}")

    with create_account:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Create account", use_container_width=True):
            try:
                response = client.auth.sign_up({"email": email, "password": password})
                if response.session and response.user:
                    st.session_state.authenticated = True
                    st.session_state.user_id = str(response.user.id)
                    st.rerun()
                st.success("Account created. Confirm your email if confirmation is enabled, then sign in.")
            except Exception as exc:
                st.error(f"Account creation failed: {exc}")
    st.stop()

def empty_workspace():
    return {
        "version": 5,
        "onboarding_complete": False,
        "candidate": {},
        "master_facts": [],
        "strengths": [],
        "stories": [],
        "jobs": [],
        "sessions": [],
        "practice_log": [],
        "interview_profiles": {},
        "selected_profile": "",
    }

def load_workspace(client, user_id):
    try:
        response = client.table("workspace_state").select("state").eq("user_id", user_id).limit(1).execute()
        if response.data and isinstance(response.data[0].get("state"), dict):
            return response.data[0]["state"]
    except Exception as exc:
        st.warning(f"Could not load workspace: {exc}")
    return empty_workspace()

def save_workspace(client, user_id, workspace):
    client.table("workspace_state").upsert({
        "user_id": user_id,
        "state": workspace,
        "updated_at": datetime.now().isoformat(),
    }).execute()
