import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY is missing from .env")

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.3,
    google_api_key=api_key
)

def chat_with_gemini(prompt: str) -> str:
    """Send a message to Gemini and return the response text."""
    try:
        resp = llm.invoke(prompt)
        return resp.content
    except Exception as e:
        return f"⚠️ Gemini error: {e}"
