# ai_client.py
import os
import logging
import requests
import json

# Global AI state
AI_AVAILABLE = False
LAST_AI_ERROR = None
MODEL = None
API_KEY = None

def init_ai():
    global AI_AVAILABLE, LAST_AI_ERROR, MODEL, API_KEY

    logging.info("🔍 init_ai() called for Gemini")

    API_KEY = os.getenv("GEMINI_API_KEY")
    MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    logging.info(f"🔑 GEMINI_API_KEY present: {bool(API_KEY)}")
    logging.info(f"🧠 Requested model: {MODEL}")

    if not API_KEY:
        AI_AVAILABLE = False
        LAST_AI_ERROR = "GEMINI_API_KEY missing"
        logging.error("❌ Gemini API key missing")
        return False

    AI_AVAILABLE = True
    LAST_AI_ERROR = None
    logging.info(f"🚀 Gemini READY | model={MODEL}")
    return True

def generate_json_response(prompt: str):
    """
    Generate a JSON response from Gemini using REST API.
    """
    global AI_AVAILABLE, LAST_AI_ERROR, MODEL, API_KEY
    
    if not AI_AVAILABLE:
        logging.error("❌ AI not available, cannot generate response")
        raise Exception("AI not initialized")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Structure prompt to enforce JSON
    payload = {
        "contents": [{
            "parts": [{"text": prompt + "\n\nReturn strict JSON only. Do not use markdown."}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract content
        try:
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            # Sanitize just in case
            if "```" in raw_text:
                raw_text = raw_text.replace("```json", "").replace("```", "")
            return json.loads(raw_text)
        except (KeyError, IndexError) as e:
            logging.error(f"❌ Unexpected Gemini response structure: {data}")
            raise Exception("Invalid response structure from Gemini")

    except Exception as e:
        logging.exception(f"❌ Gemini Generation Failed: {e}")
        raise

def generate_response(prompt: str):
    """
    Generate a text response from Gemini using REST API.
    """
    global AI_AVAILABLE, LAST_AI_ERROR, MODEL, API_KEY
    
    if not AI_AVAILABLE:
        logging.error("❌ AI not available, cannot generate response")
        return "AI features are currently unavailable. Please check API key configuration."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Structure prompt
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract content
        try:
            return data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            logging.error(f"❌ Unexpected Gemini response structure: {data}")
            return "I encountered an error processing your request."

    except Exception as e:
        logging.exception(f"❌ Gemini Generation Failed: {e}")
        return f"Error: {str(e)}"
