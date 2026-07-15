"""
llm.py — LLM client with automatic fallback.

Primary:  Groq llama-3.3-70b-versatile
Fallback: Gemini 2.0 Flash
"""

from groq import Groq
from google import genai as google_genai
import os
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
google_client = google_genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def call_llm(prompt: str, temperature: float = 0.9,
             max_tokens: int = 150) -> str:
    """
    Call LLM with automatic fallback.
    Tries Groq first, falls back to Gemini on any error.
    """
    # Try Groq first
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as groq_error:
        error_str = str(groq_error)
        if "429" in error_str or "rate_limit" in error_str.lower():
            print("⚠  Groq limit reached. Switching to Gemini...")
        else:
            print(f"⚠  Groq error: {groq_error}. Switching to Gemini...")
        # Fallback to Gemini
        try:
            response = google_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception as gemini_error:
            print(f"⚠  Gemini error: {gemini_error}")
            return "I could not generate a response. Please try again."
