import os
import time
from dotenv import load_dotenv
import google.generativeai as genai

def query_local_model(prompt: str) -> str:
    load_dotenv()  # Loads .env file
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return "❌ GEMINI_API_KEY not found in environment variables."

    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel(model_name="models/gemini-2.0-flash-lite")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        if "429" in str(e):
            time.sleep(40)
            response = model.generate_content(prompt)
            return response.text
        return f"Error: {str(e)}"
