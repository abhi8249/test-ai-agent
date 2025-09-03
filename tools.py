import re
from typing import List, Generator
from fastmcp import FastMCP
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import SessionLocal, engine, Base
from mcp.types import TextContent
from models import Employee, Resume
from llm import chat_with_gemini
import pytesseract
from pdf2image import convert_from_bytes
from io import BytesIO

# --- MCP App ---
mcp = FastMCP(name="Employee-MCP")

# --- DB bootstrap ---
Base.metadata.create_all(bind=engine)

def _db() -> Session:
    return SessionLocal()

# --- Conversation memory ---
conversation_history: List[str] = []

# --- Schema description ---
schema_description = """
Tables:
1. employees (
    id, name, role, email, leave_date, skills, on_leave [0=No, 1=Yes]
)
2. resumes (
    id, employee_email, candidate_name, phone, skills, raw_text
)
"""

# ---------------- TOOL IMPLEMENTATIONS ---------------- #

def _greeting_tool_impl(user_input: str, stream: bool = False):
    answer = chat_with_gemini(user_input, stream=stream)
    conversation_history.append(f"User: {user_input}")

    if not stream:
        conversation_history.append(f"Assistant: {answer}")
        return [TextContent(type="text", text=answer)]

    def _stream_gen():
        full = ""
        for token in answer:
            full += token
            yield TextContent(type="text", text=token)
        conversation_history.append(f"Assistant: {full}")

    return _stream_gen()

def _general_tool_impl(user_input: str, stream: bool = False):
    answer = "Sorry, I don’t have permission to answer that."
    conversation_history.append(f"Assistant: {answer}")
    return [TextContent(type="text", text=answer)]

def _db_tool_impl(user_input: str, stream: bool = False):
    db = _db()
    try:
        sql_prompt = f"""
You are an expert SQL generator.
User query: {user_input}

Schema:
{schema_description}

Only return the SQL (no explanations, no markdown fences).
Important: Use 'on_leave' column for leave status (0=No, 1=Yes).

Rules:
- You do NOT have permission to perform any action related to schema/table structure.
- That means: no CREATE, DROP, ALTER, TRUNCATE, or any DDL statements.
- You are only allowed to generate SELECT, INSERT, UPDATE, DELETE.
"""
        raw_sql = chat_with_gemini(sql_prompt).strip()
        cleaned_sql = re.sub(r"^```(?:sql)?|```$", "", raw_sql, flags=re.MULTILINE).strip()
        stmt = text(cleaned_sql)

        # --- SELECT case ---
        if cleaned_sql.lower().startswith("select"):
            result = db.execute(stmt).mappings().all()
            rows = [dict(r) for r in result]

            if not rows:
                ans = "No results found."
                conversation_history.append(f"Assistant: {ans}")
                return [TextContent(type="text", text=ans)]

            explain_prompt = (
                f"Convert the following database rows into a simple human-friendly table:\n\n{rows} "
                f"and also add a short explanatory message so the user can understand."
            )

            if not stream:
                ans = chat_with_gemini(explain_prompt)
                conversation_history.append(f"Assistant: {ans}")
                return [TextContent(type="text", text=ans)]

            # --- Streaming response ---
            response = chat_with_gemini(explain_prompt, stream=True)

            def _stream_gen():
                full = ""
                for token in response:
                    full += token
                    yield TextContent(type="text", text=token)
                conversation_history.append(f"Assistant: {full}")

            return _stream_gen()

        # --- Non-SELECT (update/insert/delete) ---
        else:
            db.execute(stmt)
            db.commit()
            ans = f"[SQL]\n{cleaned_sql}\n\n✅ Query executed successfully."
            conversation_history.append(f"Assistant: {ans}")
            return [TextContent(type="text", text=ans)]

    except Exception as e:
        err = f"❌ Error executing SQL: {e}"
        conversation_history.append(f"Assistant: {err}")
        return [TextContent(type="text", text=err)]
    finally:
        db.close()

# --- Resume Tools ---

def _extract_text_from_file(file_bytes: bytes, file_type: str) -> str:
    """Extract text from PDF, DOCX, or TXT file."""
    try:
        print(f"Extracting text from {file_type} file...")
        if file_type == "application/pdf":
            pages = convert_from_bytes(file_bytes)
            text_content = ""
            for page in pages:
                text_content += pytesseract.image_to_string(page)
                
            print(f"Extracted {len(text_content)} characters from PDF.")
            return text_content
        else:
            return file_bytes.decode("utf-8", errors="ignore")

    except Exception as e:
        return f"❌ Error extracting text from file: {e}"


# --- Resume Tools ---

def _resume_upload_tool_impl(file_bytes: bytes, file_type: str, stream: bool = False):
    """
    Step 1: Extract text via OCR and summarize using LLM.
    Does NOT save to DB yet.
    """
    raw_text = _extract_text_from_file(file_bytes, file_type) #pending we can now save the extracted data on db
    if raw_text.startswith("❌"):
        return [TextContent(type="text", text=raw_text)]

    summarize_prompt = f"""
You are an AI assistant that processes resumes.
The following is the raw resume text:

{raw_text}

1. Extract all details.
2. Provide a clean, short summary for the HR manager.
Do not add unrelated information.
"""

    if not stream:
        ans = chat_with_gemini(summarize_prompt)
        return [TextContent(type="text", text=f"📄 Resume Summary:\n\n{ans}")]

    response = chat_with_gemini(summarize_prompt, stream=True)
    def _stream_gen():
        for token in response:
            yield TextContent(type="text", text=token)
    return _stream_gen()

def _resume_confirm_save_tool_impl(user_input: str, stream: bool = False):
    ans = "Resume confirmed and stored. You can now query or match employees with it."
    return [TextContent(type="text", text=ans)]

# ---------------- Register Tools for MCP ---------------- #

@mcp.tool()
def greeting_tool(user_input: str, stream: bool = False):
    return _greeting_tool_impl(user_input, stream=stream)

@mcp.tool()
def general_tool(user_input: str, stream: bool = False):
    return _general_tool_impl(user_input, stream=stream)

@mcp.tool()
def db_tool(user_input: str, stream: bool = False):
    return _db_tool_impl(user_input, stream=stream)

@mcp.tool()
def resume_upload_tool(file_bytes: bytes, file_type: str, stream: bool = False):
    return _resume_upload_tool_impl(file_bytes, file_type, stream=stream)

@mcp.tool()
def resume_confirm_save_tool(user_input: str, stream: bool = False):
    return _resume_confirm_save_tool_impl(user_input, stream=stream)

# ---------------- ROUTER ---------------- #

def _nl_query_impl(query: str, stream: bool = False, file_bytes=None, file_type=None):
    global conversation_history

    conversation_history.append(f"User: {query}")
    if len(conversation_history) > 5:
        conversation_history = conversation_history[-5:]

    history_context = "\n".join(conversation_history)

    router_prompt = f"""
You are an assistant for an HR Employee Database on MySQL.

We have 5 tools:
1. greeting_tool(user_input)
2. general_tool(user_input)
3. db_tool(user_input)
4. resume_upload_tool(user_input)
5. resume_confirm_save_tool(user_input)

Schema (only for db_tool):
{schema_description}

Conversation so far:
{history_context}

User query: {query}

Decide which tool to call.
Return ONLY in the format:
TOOL: <tool_name>
"""

    decision = chat_with_gemini(router_prompt).strip()

    if "greeting_tool" in decision:
        return _greeting_tool_impl(query, stream=stream)
    elif "general_tool" in decision:
        return _general_tool_impl(query, stream=stream)
    elif "db_tool" in decision:
        return _db_tool_impl(query, stream=stream)
    elif "resume_upload_tool" in decision:
        if file_bytes is None or file_type is None:
            return [TextContent(type="text", text="⚠️ No file provided for upload.")]
        return _resume_upload_tool_impl(file_bytes, file_type, stream=stream)
    elif "resume_confirm_save_tool" in decision:
        return _resume_confirm_save_tool_impl(query, stream=stream)
    else:
        return [TextContent(type="text", text="⚠️ Could not route query.")]
    
    
def nl_query(query: str, stream: bool = False, file_bytes=None, file_type=None):
    return _nl_query_impl(query, stream=stream, file_bytes=file_bytes, file_type=file_type)


# ✅ MCP prompt wrapper for MCP server
@mcp.prompt()
def nl_query_prompt(query: str, stream: bool = False):
    return _nl_query_impl(query, stream=stream)
