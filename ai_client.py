# ai_client.py
import os
import logging
from openai import OpenAI

# Global AI state
client = None
AI_AVAILABLE = False
LAST_AI_ERROR = None
MODEL = None
PROVIDER = "openrouter"


def init_ai():
    global client, AI_AVAILABLE, LAST_AI_ERROR, MODEL

    logging.info("🔍 init_ai() called")

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    logging.info(f"🔑 OPENROUTER_API_KEY present: {bool(api_key)}")
    logging.info(f"🧠 Requested model: {model}")

    if not api_key:
        AI_AVAILABLE = False
        LAST_AI_ERROR = "OPENROUTER_API_KEY missing"
        logging.error("❌ OpenRouter API key missing")
        return False

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Revolutionary Invoice AI"
            }
        )

        MODEL = model
        AI_AVAILABLE = True
        LAST_AI_ERROR = None

        logging.info(f"🚀 OpenRouter READY | model={MODEL}")
        return True

    except Exception as e:
        AI_AVAILABLE = False
        LAST_AI_ERROR = str(e)
        logging.exception("❌ OpenRouter initialization failed")
        return False
