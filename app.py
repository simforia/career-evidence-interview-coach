import streamlit as st
from career_app.storage import get_client, require_auth, load_workspace, save_workspace
from career_app.ui import render_app
from career_app.onboarding import needs_onboarding, render_onboarding

st.set_page_config(page_title="Career Evidence & Interview Coach", page_icon="🛠️", layout="wide")

client = get_client()
user_id = require_auth(client)

if "workspace" not in st.session_state:
    st.session_state.workspace = load_workspace(client, user_id)

if needs_onboarding(st.session_state.workspace):
    render_onboarding(client, user_id, st.session_state.workspace, save_workspace)
    st.stop()

render_app(client, user_id, st.session_state.workspace, save_workspace)
