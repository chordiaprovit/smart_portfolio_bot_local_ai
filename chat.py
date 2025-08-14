import os
import time
from dotenv import load_dotenv
import google.generativeai as genai

def query_local_model(prompt: str) -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return "❌ GEMINI_API_KEY not found in environment variables."

    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel(model_name="models/gemini-2.0-flash-lite")
        response = model.generate_content(prompt + "\n\nPlease answer in 1-2 concise sentences only.")
        print("Gemini raw response:", response.result.candidates[0].content.parts[0].text)  # For debugging
        try:
            return response.result.candidates[0].content.parts[0].text
        except Exception as e:
            print(f"Gemini response parsing error: {e}")
            return "❌ Could not parse Gemini response text."

    except Exception as e:
        print(f"Gemini API error: {e}")  # For debugging
        if "429" in str(e):
            time.sleep(40)
            try:
                response = model.generate_content(prompt)
                try:
                    return response.result.candidates[0].content.parts[0].text
                except Exception as e2:
                    return f"❌ Could not parse Gemini response text after retry: {str(e2)}"
            except Exception as e2:
                return f"Error after retry: {str(e2)}"
        return f"Error: {str(e)}"
