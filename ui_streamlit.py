import streamlit as st
from tools import nl_query
from types import GeneratorType
import time
import base64

# --- Page config ---
st.set_page_config(page_title="Employee MCP", page_icon="💼", layout="centered")

# --- Session state for conversation ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of dicts {role, content}

if "chat_id" not in st.session_state:
    st.session_state.chat_id = 1  # track different chats

# --- Sidebar ---
with st.sidebar:
    st.title("💬 Chats")
    if st.button("➕ New Chat"):
        st.session_state.chat_id += 1
        st.session_state.chat_history = []  # reset chat
        st.rerun()

    st.write(f"Current Chat ID: {st.session_state.chat_id}")

# --- Main UI ---
st.title("💼 Employee MCP Chat")

# Chat container
chat_container = st.container()

with chat_container:
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        else:
            st.chat_message("assistant").write(msg["content"])

user_input = st.chat_input("Type your question about employees or resumes...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    
    with st.chat_message("assistant"):
        placeholder = st.empty()
        streamed_text = ""

        with st.spinner("🤖 Assistant is thinking..."):
            response = nl_query(user_input, stream=True)

            if isinstance(response, GeneratorType):
                for chunk in response:
                    if chunk and getattr(chunk, "text", None):
                        streamed_text += chunk.text
                        placeholder.markdown(streamed_text)
                        time.sleep(0.02)  # small delay for smooth typing effect

            elif isinstance(response, list):
                streamed_text = response[0].text if response else "⚠️ No output"
                placeholder.markdown(streamed_text)

            else:
                streamed_text = "⚠️ Unexpected response format"
                placeholder.markdown(streamed_text)

    st.session_state.chat_history.append({"role": "assistant", "content": streamed_text})
    st.rerun()

st.subheader("📄 Upload Resume")
uploaded_file = st.file_uploader("Upload CV (PDF/DOCX)", type=["pdf", "docx"])

if uploaded_file:
    with st.spinner("📂 Processing resume..."):
        file_bytes = uploaded_file.read()
        file_type = uploaded_file.type

        resume_prompt = f"The user uploaded a resume: {uploaded_file.name}"

        response = nl_query(resume_prompt, stream=False, file_bytes=file_bytes, file_type=file_type)

    if isinstance(response, list) and response:
        st.success("✅ Resume uploaded and parsed!")
        st.write(response[0].text)
    else:
        st.error("⚠️ Failed to process resume.")

