import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from typing import Generator, Union

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY is missing from .env")

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.3,
    google_api_key=api_key
)

def chat_with_gemini(prompt: str, stream: bool = False) -> Union[Generator[str, None, None], str]:
    """
    Calls Gemini LLM via LangChain.
    If stream=True, yields tokens progressively.
    """
    if not stream:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content

    # --- Streaming mode ---
    def _stream_gen():
        for chunk in llm.stream([HumanMessage(content=prompt)]):
            if chunk.content:
                yield chunk.content

    return _stream_gen()
