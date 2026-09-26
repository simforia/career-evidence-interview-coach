import streamlit as st
from career_app.storage import get_client, require_auth, load_workspace, save_workspace
from career_app.ui import render_app

st.set_page_config(page_title="Career Evidence & Interview Coach", page_icon="🛠️", layout="wide")

client = get_client()
user_id = require_auth(client)

if "workspace" not in st.session_state:
    st.session_state.workspace = load_workspace(client, user_id)

render_app(client, user_id, st.session_state.workspace, save_workspace)
