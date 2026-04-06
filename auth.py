import streamlit as st
import sqlite3
import uuid
import hmac
from pathlib import Path

DB_PATH = Path("auth.db")

# =========================================================
# SIMPLE USER LIST
# Edit this dictionary to add/remove users
# Format: "username": "password"
# =========================================================
USERS = st.secrets["users"]

# =========================================================
# Database helpers
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            username TEXT PRIMARY KEY,
            session_token TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def set_active_session(username: str, session_token: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO active_sessions (username, session_token)
        VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET session_token=excluded.session_token
    """, (username, session_token))
    conn.commit()
    conn.close()

def get_active_session(username: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT session_token FROM active_sessions WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def clear_active_session(username: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM active_sessions WHERE username = ?", (username,))
    conn.commit()
    conn.close()

# =========================================================
# Session state helpers
# =========================================================
def init_auth_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "session_token" not in st.session_state:
        st.session_state.session_token = None

# =========================================================
# Login / logout
# =========================================================
def login_user(username: str):
    token = str(uuid.uuid4())
    st.session_state.authenticated = True
    st.session_state.username = username
    st.session_state.session_token = token
    set_active_session(username, token)

def logout_user():
    username = st.session_state.username
    current_token = st.session_state.session_token

    if username and current_token:
        active = get_active_session(username)
        if active == current_token:
            clear_active_session(username)

    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.session_token = None
    st.rerun()

def check_for_session_takeover():
    if not st.session_state.authenticated or not st.session_state.username:
        return

    active = get_active_session(st.session_state.username)
    if active != st.session_state.session_token:
        st.warning("This account was signed in somewhere else. You have been logged out.")
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.session_token = None
        st.stop()

# =========================================================
# UI
# =========================================================
def show_login_screen():
    st.title("Private Question Bank")

    st.write("Please log in to continue.")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Log in"):
        expected_password = USERS.get(username)

        if expected_password and hmac.compare_digest(password, expected_password):
            login_user(username)
            st.rerun()
        else:
            st.error("Invalid username or password.")

def require_login():
    init_db()
    init_auth_state()

    if not st.session_state.authenticated:
        show_login_screen()
        st.stop()

    check_for_session_takeover()

def show_user_banner():
    st.markdown(
        f"""
        <div style="
            position: fixed;
            top: 10px;
            right: 15px;
            opacity: 0.35;
            font-size: 14px;
            z-index: 9999;
            background-color: rgba(255,255,255,0.6);
            padding: 4px 8px;
            border-radius: 6px;
        ">
            User: {st.session_state.username}
        </div>
        """,
        unsafe_allow_html=True,
    )

def show_logout_button():
    if st.sidebar.button("Log out"):
        logout_user()