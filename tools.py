import json
import os
import tempfile
from typing import Dict, Any, Optional

from fastmcp import FastMCP
from sqlalchemy.orm import Session
from sqlalchemy import select

from db import SessionLocal, engine
from models import Employee, Resume
from llm import chat_with_gemini

# OCR stack
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from sqlalchemy import text
from mcp.types import TextContent
import re


mcp = FastMCP(name="Employee-MCP")

# --- DB bootstrap (create tables if not exist) ---
from db import Base
Base.metadata.create_all(bind=engine)

# --- Helpers ---
def _db() -> Session:
    return SessionLocal()

@mcp.prompt()
def nl_query(query: str):
    schema_description = """
    Tables:
    1. employees (id, name, role, email,leave_date, skills, on_leave [0=No, 1=Yes])
    2. resumes (id, employee_email, candidate_name, phone, skills, raw_text)
    """

    sql_prompt = f"""
You are an assistant that translates natural language into SQL for a MySQL database.

Schema:
{schema_description}

Important rules:
- Always make results human-friendly.
- Specifically, for employees.on_leave:
  - Convert it using: CASE WHEN on_leave=1 THEN 'Yes' ELSE 'No' END AS on_leave
  - Never return raw 0/1 values.
- Prefer clear column aliases when transforming values.
- Return ONLY the SQL query (no markdown, no explanations).

User question:
---
{query}
---
    """

    raw_sql = chat_with_gemini(sql_prompt).strip()

    # 🧹 Clean ```sql ... ``` fences
    cleaned_sql = re.sub(r"^```(?:sql)?|```$", "", raw_sql.strip(), flags=re.MULTILINE).strip()

    db = _db()
    try:
        stmt = text(cleaned_sql)

        if cleaned_sql.lower().startswith("select"):
            result = db.execute(stmt).mappings().all()
            rows = [dict(r) for r in result]
            return [TextContent(
                type="text",
                text=f"{rows}"
            )]
        else:
            db.execute(stmt)
            db.commit()
            return [TextContent(
                type="text",
                text=f"[SQL]\n{cleaned_sql}\n\n[Result]\n✅ Query executed successfully."
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Error executing SQL: {e}\nGenerated SQL:\n{cleaned_sql}"
        )]
    finally:
        db.close()
