import json
import os
import re
import time
from urllib.parse import quote_plus
import logging

import google.generativeai as genai
import requests
from dotenv import load_dotenv
from google.ai.generativelanguage_v1beta.types import content

load_dotenv()

GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API")
# Add a check for the API key
if not GEMINI_API_KEY:
    raise ValueError("GOOGLE_GEMINI_API environment variable not set.")
genai.configure(api_key=GEMINI_API_KEY)

# Google Custom Search API credentials
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# Standard Disclaimer Constant
STANDARD_DISCLAIMER = "Disclaimer: I am an AI Chatbot. This information is not a substitute for professional medical advice. Always consult a doctor for diagnosis and treatment."

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def markdown_to_plain_text(markdown_text):
    """Convert markdown to plain text by removing markdown formatting."""
    if not isinstance(markdown_text, str):
        return "" # Return empty string if input is not a string

    # Remove headers (# Header)
    plain_text = re.sub(r'#+\s+(.*)', r'\1', markdown_text)
    # Remove bold/italic formatting (**bold** or *italic* or __bold__ or _italic_)
    plain_text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', plain_text)
    plain_text = re.sub(r'(\*|_)(.*?)\1', r'\2', plain_text)
    # Remove bullet points/numbered lists
    plain_text = re.sub(r'^\s*[-*+]\s+', '', plain_text, flags=re.MULTILINE)
    plain_text = re.sub(r'^\s*\d+\.\s+', '', plain_text, flags=re.MULTILINE)
    # Remove code blocks and inline code
    plain_text = re.sub(r'```.*?```', '', plain_text, flags=re.DOTALL)
    plain_text = re.sub(r'`(.*?)`', r'\1', plain_text)
    # Remove links [text](url) -> text
    plain_text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', plain_text)
    # Remove horizontal rules
    plain_text = re.sub(r'\n\s*[-*_]{3,}\s*\n', '\n\n', plain_text) # More robust rule removal
    # Replace multiple newlines with two newlines
    plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)
    # Remove extra whitespace
    plain_text = ' '.join(plain_text.split())
    return plain_text.strip()


def gemini_text(message):
    """
    Handles single-turn text generation with structured output, asking follow-ups for initial symptoms.
    """
    # Create the model
    generation_config = {
        "temperature": 2, # Slightly lower temperature for more predictable structure
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_schema": content.Schema(
            type=content.Type.OBJECT,
            # Define all fields expected based on the prompt
            required=["response", "Symptoms", "Remedies", "Precautions", "Guidelines", "is_medical_related_prompt", "medication", "Disclaimer"],
            properties={
                "response": content.Schema(
                    type=content.Type.STRING,
                    description="The chatbot's primary conversational response text."
                ),
                "Symptoms": content.Schema(
                    type=content.Type.STRING,
                    description="Summary of symptoms mentioned or '.' if none/not applicable."
                ),
                "Remedies": content.Schema(
                    type=content.Type.STRING,
                    description="General remedies or guidance, empty string if not applicable."
                ),
                "Precautions": content.Schema(
                    type=content.Type.STRING,
                    description="Relevant precautions, empty string if not applicable."
                ),
                "Guidelines": content.Schema(
                    type=content.Type.STRING,
                    description="General guidelines, empty string if not applicable."
                ),
                "is_medical_related_prompt": content.Schema(
                    type=content.Type.STRING,
                    enum=["Yes", "No"], # Enforce Yes/No
                    description="Indicates if the user's query was classified as medical-related."
                ),
                "medication": content.Schema(
                    type=content.Type.ARRAY,
                    items=content.Schema(type=content.Type.STRING),
                    description="List of medications (should generally remain empty unless specifically requested and safe to mention common OTC types)."
                ),
                "Disclaimer": content.Schema(
                    type=content.Type.STRING,
                    description="Standard medical disclaimer."
                ),
            },
        ),
        "response_mime_type": "application/json",
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash", # Using 2.0 flash as 2.0 is not generally available
        generation_config=generation_config,
        safety_settings={ # More specific safety settings
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    )
    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    """
You are MedAssist, a medical information chatbot. Your primary goal is to provide helpful information while adhering to safety guidelines and a structured response format.

YOUR TASK:
1.  Analyze the user's message to determine if it's a medical-related query or a non-medical query.
2.  For INITIAL medical queries about specific symptoms (like 'I have a headache'), ask 1-2 clarifying follow-up questions in your text `response`. Do not provide remedies/precautions yet in this case.
3.  If the query is non-medical (e.g., 'What's the weather?'), state that you specialize in medical topics in the `response`.
4.  If the query is medical but general (e.g., 'What are the symptoms of flu?') or if you have already asked follow-up questions in a previous turn (context not available in this function, assume single turn), provide a helpful text `response` and fill the structured fields.
5.  ALWAYS structure your entire output as a JSON object conforming to the defined schema, populating all fields appropriately based on the query type and context.

RESPONSE STRUCTURE (JSON Schema):
- `response` (string): Your conversational reply to the user. For initial symptom queries, this contains follow-up questions. For non-medical, explain your focus. For general medical or follow-up, provide information.
- `Symptoms` (string): Summarize mentioned symptoms. Use "." if none mentioned, not applicable (non-medical), or asking follow-up questions.
- `Remedies` (string): Suggest general remedies/guidance. Empty string "" if asking follow-up, non-medical, or none applicable.
- `Precautions` (string): List relevant precautions. Empty string "" if asking follow-up, non-medical, or none applicable.
- `Guidelines` (string): Provide general guidelines. Empty string "" if asking follow-up, non-medical, or none applicable.
- `is_medical_related_prompt` (string): MUST be "Yes" for medical queries, "No" for non-medical queries.
- `medication` (array): Keep as an empty array `[]`. Never prescribe or suggest specific dosages.
- `Disclaimer` (string): MUST include the standard medical disclaimer.

HANDLING SPECIFIC CASES:
- Initial Symptom Query (e.g., "I have a cough"): `response`="Okay, I understand you have a cough. Can you tell me more? How long have you had it, and do you have any other symptoms like fever or sore throat?", `Symptoms`="Cough", `Remedies`="", `Precautions`="", `Guidelines`="", `is_medical_related_prompt`="Yes", `medication`=[], `Disclaimer`="..."
- General Medical Query (e.g., "Tell me about diabetes"): `response`="Diabetes is a chronic condition...", `Symptoms`=".", `Remedies`="Managing diabetes often involves...", `Precautions`="It's important to monitor blood sugar...", `Guidelines`="Regular check-ups are crucial...", `is_medical_related_prompt`="Yes", `medication`=[], `Disclaimer`="..."
- Non-Medical Query (e.g., "What time is it?"): `response`="I am MedAssist, designed to provide medical information. I cannot provide the current time.", `Symptoms`=".", `Remedies`="", `Precautions`="", `Guidelines`="", `is_medical_related_prompt`="No", `medication`=[], `Disclaimer`="..."

Now, process the user's message according to these rules and generate the JSON output.
"""
                ],
            },
            {
                "role": "model",
                "parts": [
                    # Provide a valid JSON confirmation matching the schema
                    json.dumps({
                        "response": "Okay, I understand my role as MedAssist. I will analyze the user's query, determine if it's medical, ask follow-ups for initial symptoms if needed, provide information for general queries, handle non-medical queries appropriately, and always respond with a JSON object matching the required schema, including all fields like `is_medical_related_prompt` and the `Disclaimer`.",
                        "Symptoms": ".",
                        "Remedies": "",
                        "Precautions": "",
                        "Guidelines": "",
                        "is_medical_related_prompt": "Yes", # Default assumption for confirmation
                        "medication": [],
                        "Disclaimer": STANDARD_DISCLAIMER
                    })
                ],
            },
        ]
    )
    try:
        # Send the actual user message here
        response = chat_session.send_message(message)
        response_dict = json.loads(response.text)

        # Process the 'response' text field if it exists
        if "response" in response_dict:
            response_dict["response"] = markdown_to_plain_text(response_dict["response"])
        else:
             # Ensure 'response' field exists, even if empty, if schema expects it
             response_dict["response"] = "" # Or provide a default message

        # Ensure other required fields exist (provide defaults if missing)
        response_dict.setdefault("Symptoms", ".")
        response_dict.setdefault("Remedies", "")
        response_dict.setdefault("Precautions", "")
        response_dict.setdefault("Guidelines", "")
        response_dict.setdefault("is_medical_related_prompt", "No") # Default to No if missing
        response_dict.setdefault("medication", [])
        response_dict.setdefault("Disclaimer", STANDARD_DISCLAIMER)


        return response_dict

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from gemini_text: {e}\nResponse text: {getattr(response, 'text', 'N/A')}")
        # Fallback for JSON error
        return {
            "response": "Sorry, I encountered an technical issue processing that. Could you please rephrase?",
            "Symptoms": ".", "Remedies": "", "Precautions": "", "Guidelines": "",
            "is_medical_related_prompt": "No", "medication": [], "Disclaimer": STANDARD_DISCLAIMER
            }
    except Exception as e:
        print(f"An unexpected error occurred in gemini_text: {e}")
        # General fallback error
        return {
            "response": "Sorry, I encountered an unexpected error. Please try again later.",
            "Symptoms": ".", "Remedies": "", "Precautions": "", "Guidelines": "",
            "is_medical_related_prompt": "No", "medication": [], "Disclaimer": STANDARD_DISCLAIMER
            }


def search_images(query, num_results=3):
    """
    Search for images using Google Custom Search API

    Args:
        query (str): The search query
        num_results (int): Number of image results to return (max 10)

    Returns:
        list: List of image URLs and metadata
    """
    # Check if API keys are configured
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID or GOOGLE_SEARCH_API_KEY == "your-google-search-api-key":
        print("Warning: Google Search API credentials not configured. Returning sample data.")
        # Return sample data for testing
        return [
                   {
                       "url": f"https://via.placeholder.com/150/0000FF/808080?text=Sample+{query.replace(' ', '+')}+1",
                       "title": f"Sample Image 1 for {query}",
                       "context_url": "https://example.com",
                       "thumbnail": f"https://via.placeholder.com/50/0000FF/808080?text=S1",
                       "width": 150,
                       "height": 150
                   },
                   {
                       "url": f"https://via.placeholder.com/150/FF0000/FFFFFF?text=Sample+{query.replace(' ', '+')}+2",
                       "title": f"Sample Image 2 for {query}",
                       "context_url": "https://example.com",
                       "thumbnail": f"https://via.placeholder.com/50/FF0000/FFFFFF?text=S2",
                       "width": 150,
                       "height": 150
                   },
                   {
                       "url": f"https://via.placeholder.com/150/00FF00/000000?text=Sample+{query.replace(' ', '+')}+3",
                       "title": f"Sample Image 3 for {query}",
                       "context_url": "https://example.com",
                       "thumbnail": f"https://via.placeholder.com/50/00FF00/000000?text=S3",
                       "width": 150,
                       "height": 150
                   }
               ][:num_results]

    # Ensure number of results is within valid range (1-10)
    num_results = min(max(1, num_results), 10)

    # Format the API URL
    encoded_query = quote_plus(query)
    url = f"https://www.googleapis.com/customsearch/v1"

    # Set up the parameters
    params = {
        "key": GOOGLE_SEARCH_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": encoded_query,
        "searchType": "image",
        "num": num_results,
        "safe": "active" # Options: active, off
    }

    try:
        # Make the request
        response = requests.get(url, params=params, timeout=10) # Added timeout
        response.raise_for_status()  # Raise an error for bad status codes (4xx or 5xx)

        # Parse the JSON response
        search_results = response.json()

        # Extract image URLs and metadata
        images = []
        if "items" in search_results:
            for item in search_results["items"]:
                image_data = {
                    "url": item.get("link"),
                    "title": item.get("title"),
                    "context_url": item.get("image", {}).get("contextLink"),
                    "thumbnail": item.get("image", {}).get("thumbnailLink"),
                    "width": item.get("image", {}).get("width"),
                    "height": item.get("image", {}).get("height")
                }
                # Basic validation
                if image_data["url"] and image_data["thumbnail"]:
                    images.append(image_data)

        return images

    except requests.exceptions.Timeout:
        print(f"Error: Request to Google Custom Search timed out for query: {query}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error making request to Google Custom Search: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response from Google Custom Search: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred in search_images: {e}")
        return []


def get_image_urls(query, num_results=3):
    """
    Search for images and return only the URLs

    Args:
        query (str): The search query
        num_results (int): Number of image results to return

    Returns:
        list: List of valid image URLs
    """
    images = search_images(query, num_results)
    return [image["url"] for image in images if image.get("url")]


def download_and_save_images(query, save_folder="uploaded_images/search_results", num_results=3):
    """
    Search for images, download them, and save to the specified folder

    Args:
        query (str): The search query
        save_folder (str): Folder path to save the images
        num_results (int): Number of image results to download

    Returns:
        list: List of dicts containing saved image file paths and metadata
    """
    # Create folder if it doesn't exist
    try:
        os.makedirs(save_folder, exist_ok=True)
    except OSError as e:
        print(f"Error creating directory {save_folder}: {e}")
        return []

    # Search for images
    images = search_images(query, num_results)
    if not images:
        print(f"No images found for query: {query}")
        return []

    saved_images = []
    for i, image in enumerate(images):
        image_url = image.get("url")
        if not image_url:
            print(f"Skipping image {i+1} due to missing URL.")
            continue

        try:
            # Generate a unique filename based on query, timestamp, and index
            safe_query = re.sub(r'[\\/*?:"<>|]', "", query)[:50] # Sanitize query for filename
            timestamp = int(time.time())
            # Try to get extension from URL, default to .jpg
            _, ext = os.path.splitext(image_url)
            if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                ext = '.jpg'
            filename = f"{safe_query}_{timestamp}_{i + 1}{ext}"
            filepath = os.path.join(save_folder, filename)

            # Download and save the image
            print(f"Downloading image {i+1} from {image_url}...")
            response = requests.get(image_url, stream=True, timeout=15) # Increased timeout
            response.raise_for_status()

            # Check content type if possible
            content_type = response.headers.get('content-type')
            if content_type and not content_type.startswith('image/'):
                 print(f"Skipping download for image {i+1}: URL content type ({content_type}) doesn't appear to be an image.")
                 continue

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Add metadata to saved image info
            saved_image_info = {
                "filepath": filepath,
                "original_url": image_url,
                "title": image.get("title"),
                "context_url": image.get("context_url")
            }
            saved_images.append(saved_image_info)
            print(f"Saved image {i + 1} to {filepath}")

        except requests.exceptions.Timeout:
            print(f"Error downloading image {i + 1} ({image_url}): Request timed out.")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image {i + 1} ({image_url}): {e}")
        except IOError as e:
             print(f"Error saving image {i+1} to {filepath}: {e}")
        except Exception as e:
            print(f"Unexpected error downloading or saving image {i + 1} ({image_url}): {e}")

    return saved_images


def gemini_generic(message):
    """
    Classifies a query as medical/non-medical and provides a structured JSON output
    without conversational text or follow-up logic.
    """
    # Define the detailed base prompt within the function for clarity
    base_prompt_instructions = """
You are MedAssist, a medical information classification bot. Your task is to analyze a user's query and respond ONLY with a structured JSON object conforming precisely to the schema provided. Do NOT include any conversational text outside the JSON structure.

YOUR TASK:
1.  Determine if the user's query is medical-related ("Yes") or not ("No").
2.  Populate a JSON object according to the specified schema based ONLY on the user's query.

RESPONSE STRUCTURE (JSON Schema - Output ONLY this JSON):
You MUST output a JSON object with these exact fields:
- `Symptoms` (string): If medical and symptoms are mentioned, briefly list them (e.g., "Headache, fever"). If non-medical or no specific symptoms mentioned, use ".".
- `Remedies` (string): If medical and general remedies are applicable *based directly on the query* (e.g., query asks for remedies), provide brief, general suggestions. Otherwise, or if non-medical, use an empty string "".
- `Precautions` (string): If medical and general precautions are applicable *based directly on the query*, list brief precautions. Otherwise, or if non-medical, use an empty string "".
- `Guidelines` (string): If medical and general guidelines are applicable *based directly on the query*, provide brief guidelines. Otherwise, or if non-medical, use an empty string "".
- `is_medical_related_prompt` (string): MUST be exactly "Yes" or "No".
- `medication` (array): MUST be an empty array `[]`.
- `Disclaimer` (string): MUST be the standard disclaimer: "I am an AI chatbot, not a substitute for professional medical advice... consult with a healthcare professional."

HOW TO HANDLE QUERY TYPES:
- **Medical Query (e.g., "symptoms of flu", "remedies for cold", "headache"):** Set `is_medical_related_prompt`="Yes". Populate `Symptoms` if mentioned. Populate `Remedies`, `Precautions`, `Guidelines` ONLY if the query *asks* for them or they are the core topic (e.g., "precautions for diabetes"). Otherwise, leave them as "".
- **Non-Medical Query (e.g., "capital of France", "tell me a joke"):** Set `is_medical_related_prompt`="No". Set `Symptoms`=".". Set `Remedies`, `Precautions`, `Guidelines` to "".

Example Medical Output (Query: "what are flu symptoms"):
```json
{
  "Symptoms": "Fever, cough, sore throat, body aches, fatigue",
  "Remedies": "",
  "Precautions": "",
  "Guidelines": "",
  "is_medical_related_prompt": "Yes",
  "medication": [],
  "Disclaimer": "I am an AI chatbot, not a substitute for professional medical advice..."
}
```
Example Non-Medical Output (Query: "latest sports scores"):
```json
{
  "Symptoms": ".",
  "Remedies": "",
  "Precautions": "",
  "Guidelines": "",
  "is_medical_related_prompt": "No",
  "medication": [],
  "Disclaimer": "I am an AI chatbot, not a substitute for professional medical advice..."
}
```

Now, analyze the following user query and generate ONLY the JSON output according to these strict instructions. User Query:
""" # The user message will be appended by send_message

    generation_config = {
        "temperature": 2, # Lower temp for strict adherence to format
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192, # Can likely reduce this for this function
        "response_schema":content.Schema(
            type = content.Type.OBJECT,
            required = ["Symptoms", "Remedies", "Precautions", "Guidelines", "is_medical_related_prompt", "medication", "Disclaimer"],
            properties = {
                "Symptoms": content.Schema(type = content.Type.STRING),
                "Remedies": content.Schema(type = content.Type.STRING),
                "Precautions": content.Schema(type = content.Type.STRING),
                "Guidelines": content.Schema(type = content.Type.STRING),
                "is_medical_related_prompt": content.Schema(type = content.Type.STRING, enum=["Yes", "No"]),
                "medication": content.Schema(type = content.Type.ARRAY, items = content.Schema(type = content.Type.STRING)),
                "Disclaimer": content.Schema(type = content.Type.STRING),
            },
        ),
        "response_mime_type": "application/json",
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        safety_settings={ # Consistent safety settings
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    )
    # Start chat with only the system prompt
    chat_session = model.start_chat(
        history=[
            {   "role": "user",
                "parts": [ base_prompt_instructions ] # Pass the detailed instructions
            },
             # Optional: Add a model confirmation message (as valid JSON if possible)
             # { "role": "model", "parts": [json.dumps({...example structure...})] }
        ]
    )

    try:
        # Send the user's message
        response = chat_session.send_message(message)
        response_dict = json.loads(response.text)

        # Basic validation: Check if the required classification field is present
        if "is_medical_related_prompt" not in response_dict:
             print(f"Warning: 'is_medical_related_prompt' missing from gemini_generic response.")
             # Add a default or handle error appropriately
             response_dict["is_medical_related_prompt"] = "No" # Safer default

        # Ensure other required fields exist (provide defaults if missing)
        response_dict.setdefault("Symptoms", ".")
        response_dict.setdefault("Remedies", "")
        response_dict.setdefault("Precautions", "")
        response_dict.setdefault("Guidelines", "")
        response_dict.setdefault("medication", [])
        response_dict.setdefault("Disclaimer", STANDARD_DISCLAIMER)

        # No markdown processing needed here as no conversational 'response' field is expected

        return response_dict

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from gemini_generic: {e}\nResponse text: {getattr(response, 'text', 'N/A')}")
        # Fallback for JSON error - return structure matching schema
        return {
             "Symptoms": ".", "Remedies": "", "Precautions": "", "Guidelines": "",
             "is_medical_related_prompt": "No", "medication": [], "Disclaimer": STANDARD_DISCLAIMER
        }
    except Exception as e:
        print(f"An unexpected error occurred in gemini_generic: {e}")
        # General fallback error
        return {
             "Symptoms": ".", "Remedies": "", "Precautions": "", "Guidelines": "",
             "is_medical_related_prompt": "No", "medication": [], "Disclaimer": STANDARD_DISCLAIMER
        }


def gemini_interactive(message, conversation_history=None):
    """
    Enhanced function for multi-step medical conversations with support for follow-up questions
    and symptom rating. Provides structured responses at the end of the conversation.

    Args:
        message (str): The current user message
        conversation_history (list, optional): List of previous messages in the conversation
                                             Each item should be a dict like {"role": "user/model", "parts": ["message text"]}

    Returns:
        dict: Response with conversation data and UI action suggestions
    """
    try:
        # Create the model with appropriate configuration
        generation_config = {
            "temperature": 2,  # Slightly adjusted temperature
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_schema": content.Schema(
                type=content.Type.OBJECT,
                # Added is_medical_related_prompt and made it required for consistency
                required=["response", "needs_follow_up", "is_medical_related", "is_medical_related_prompt", "can_provide_structured_response", "conversation_complete", "Symptoms", "Disclaimer", "image_search_term"],
                properties={
                    "response": content.Schema(
                        type=content.Type.STRING,
                        description="The medical assistant's conversational response to the user."
                    ),
                    "needs_follow_up": content.Schema(
                        type=content.Type.BOOLEAN,
                        description="True if the assistant needs to ask follow-up questions."
                    ),
                    "follow_up_question": content.Schema(
                        type=content.Type.STRING,
                        description="The specific follow-up question to ask if needs_follow_up is true. Empty otherwise."
                    ),
                    "follow_up_type": content.Schema(
                        type=content.Type.STRING,
                        description="Suggested input type for follow-up (e.g., text, scale, select). Default: 'select'.",
                        enum=["text", "scale", "select", "multiselect", "checkbox"]
                    ),
                    "follow_up_options": content.Schema(
                        type=content.Type.ARRAY, items=content.Schema(type=content.Type.STRING),
                        description="Options for 'select', 'multiselect', or 'checkbox' follow-up types. Empty otherwise."
                    ),
                    "rate_symptoms": content.Schema(
                        type=content.Type.BOOLEAN,
                        description="True if the assistant suggests rating symptoms."
                    ),
                    "symptoms_to_rate": content.Schema(
                        type=content.Type.ARRAY, items=content.Schema(type=content.Type.STRING),
                        description="List of symptoms to rate if rate_symptoms is true. Empty otherwise."
                    ),
                    "is_medical_related": content.Schema(
                        type=content.Type.BOOLEAN,
                        description="True if the *current user query* or overall topic is medical-related."
                    ),
                     "is_medical_related_prompt": content.Schema( # Added for consistency
                        type=content.Type.STRING,
                        enum=["Yes", "No"],
                        description="String indicator ('Yes' or 'No') classifying the medical nature of the query/conversation."
                    ),
                    "can_provide_structured_response": content.Schema(
                        type=content.Type.BOOLEAN,
                        description="True if enough information is gathered for a full structured medical summary."
                    ),
                    "conversation_complete": content.Schema(
                        type=content.Type.BOOLEAN,
                        description="True if the conversation thread seems logically complete (no immediate follow-up needed)."
                    ),
                    "current_step": content.Schema(
                        type=content.Type.INTEGER,
                        description="Estimated current step in a multi-step interaction (e.g., 1 of 5). Optional."
                    ),
                    "total_steps": content.Schema(
                        type=content.Type.INTEGER,
                        description="Estimated total steps for the interaction. Optional."
                    ),
                    # --- Structured Medical Fields ---
                    "Symptoms": content.Schema(
                        type=content.Type.STRING,
                        description="Summary of user's symptoms. '.' if none/not applicable."
                    ),
                    "Remedies": content.Schema(
                        type=content.Type.STRING,
                        description="Recommended general remedies. Empty if not applicable."
                    ),
                    "Precautions": content.Schema(
                        type=content.Type.STRING,
                        description="Relevant precautions. Empty if not applicable."
                    ),
                    "Guidelines": content.Schema(
                        type=content.Type.STRING,
                        description="General guidelines. Empty if not applicable."
                    ),
                    "medication": content.Schema(
                        type=content.Type.ARRAY, items=content.Schema(type=content.Type.STRING),
                        description="""List of relevant, common OTC medication types specific to the discussed condition. 
                        Each medication must be appropriate for the specific symptoms/condition discussed.
                        Examples:
                        - For cold/flu: 'Acetaminophen', 'Ibuprofen', 'Decongestants'
                        - For allergies: 'Antihistamines', 'Nasal corticosteroids'
                        - For headache: 'Acetaminophen', 'Ibuprofen', 'Aspirin'
                        - For acid reflux: 'Antacids', 'H2 blockers'
                        - For diarrhea: 'Loperamide', 'Bismuth subsalicylate'
                        - For constipation: 'Fiber supplements', 'Stool softeners'
                        - For minor pain: 'Acetaminophen', 'Ibuprofen', 'Topical analgesics'
                        - For skin rash: 'Antihistamine cream', 'Hydrocortisone cream'
                        - For sore throat: 'Throat lozenges', 'Salt water gargle'
                        - For cough: 'Cough suppressants', 'Expectorants'
                        Keep list short (max 2-3 relevant types). Never include prescription medications or specific dosages."""
                    ),
                    "Disclaimer": content.Schema(
                        type=content.Type.STRING,
                        description="Standard medical disclaimer."
                    ),
                    # --- ADDED: Optional field for AI-suggested image search term ---
                    "image_search_term": content.Schema(
                        type=content.Type.STRING,
                        description="A concise, relevant Google Image search term based on the final medical topic, provided only when conversation is complete and medical. Empty otherwise."
                    )
                }
            ),
            "response_mime_type": "application/json",
        }

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash", # Use 2.0 flash
            generation_config=generation_config,
            safety_settings={ # Consistent safety settings
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )

        # --- History and Initial Prompt Setup ---
        initial_system_prompt = """
# --- ROLE & GOAL ---
You are MedAssist, an interactive AI medical information chatbot. Your primary goal is to engage in a helpful, empathetic, and natural multi-turn conversation to understand the user's health query and provide structured, general information safely.

# --- TONE & STYLE ---
- Be friendly, empathetic, and conversational. Use natural language.
- Avoid overly clinical, robotic, or impersonal phrasing.
- Acknowledge the user's input briefly before asking follow-up questions (e.g., "Okay, thanks for sharing that.", "I understand.").
- Keep your conversational responses (`response` field) clear and focused.

# --- CORE CONVERSATION FLOW & RULES ---
1.  **Analyze Query:** Determine if the user's message is medical or non-medical. Set `is_medical_related` (boolean) and `is_medical_related_prompt` (string "Yes"/"No") accordingly.
2.  **Information Gathering (If Medical):**
    *   **Goal:** Gather sufficient details (symptoms, duration, severity, characteristics, context) to provide a helpful general summary.
    *   **Method:** Ask relevant follow-up questions one main topic at a time. Focus on the *next logical question* based on the conversation history and the user's last message.
    *   **Question Style:** Phrase questions clearly and naturally. PREFER INTERACTIVE COMPONENTS (select, multiselect, scale, checkbox) over free text input whenever feasible to make it easier for the user. Provide relevant `follow_up_options`.
    *   **Clarification:** If the user's response is vague, ambiguous, or warrants more detail, ask a brief, specific clarifying question (e.g., "Could you describe that pain a bit more?", "When did that start happening?").
    *   **Pacing:** Don't rush to a conclusion. Ensure you understand the key aspects of the user's situation before summarizing.
    *   **State:** While gathering info, set `needs_follow_up`=true, `conversation_complete`=false, `can_provide_structured_response`=false.
3.  **Providing Summary (When Sufficient Info Gathered):**
    *   **Trigger:** When you have a reasonable understanding of the primary symptoms, duration, severity, etc.
    *   **Action:**
        - Provide a BRIEF concluding conversational statement in the `response` field (e.g., "Okay, based on what you've told me, here is some general information...").
        - Set `needs_follow_up`=false, `conversation_complete`=true, `can_provide_structured_response`=true.
        - Populate the structured fields (`Symptoms`, `Remedies`, `Precautions`, `Guidelines`) with detailed, actionable, *general* information relevant to the conversation. Aim for 3-5 distinct points per field where applicable, formatted using Markdown (e.g., `**Rest:** Get plenty of sleep.\n**Hydration:** Drink fluids.`).
        - Populate `medication` field safely (see Safety Rules).
        - Generate an `image_search_term` if appropriate (see Safety Rules).
4.  **Handling Non-Medical Queries:**
    *   Politely explain your focus (medical information) in the `response`.
    *   Set `is_medical_related`=false, `is_medical_related_prompt`="No".
    *   Set `needs_follow_up`=false, `conversation_complete`=true, `can_provide_structured_response`=false.
    *   Clear structural fields (`Symptoms`=".", etc.).
5.  **Proactive Suggestions (Use Sparingly):**
    *   Towards the end of information gathering, you *may* briefly offer to discuss closely related topics (e.g., "Would you also like to talk about common triggers?") if it feels natural and helpful. Don't interrupt the primary flow.

# --- SAFETY & OUTPUT RULES ---
1.  **Disclaimer:** ALWAYS include the `Disclaimer`. Emphasize seeking professional help.
2.  **Structured Output:** ALWAYS return a valid JSON object matching the required schema. All required fields must be present.
3.  **Medication Safety:** Only list common, generic OTC medication *types* (e.g., 'Ibuprofen', 'Loratadine') if directly relevant and the conversation is complete. Max 2-3 types. NEVER list dosages, brands, or prescription meds. If unsure, leave `medication` as `[]`.
4.  **Image Search Term Safety:** Only generate `image_search_term` if `conversation_complete` is true AND `is_medical_related` is true. Keep it concise (2-4 words, e.g., 'flu symptoms', 'knee pain relief').
5.  **High Severity:** If the user describes severe symptoms (chest pain, difficulty breathing, etc.), *immediately* prioritize recommending professional medical help (urgent care, emergency services) in the `response`, provide detailed precautions, set `conversation_complete`=true, and include the Disclaimer.

# --- INTERACTIVE COMPONENTS GUIDELINES ---
- Use `select` for single choices (Yes/No, duration ranges, location options).
- Use `multiselect` or `checkbox` for multiple possible symptoms or factors.
- Use `scale` for severity ratings (e.g., pain 1-10).
- Use `text` input only when absolutely necessary for specific details not suited to options.
- Provide clear, concise `follow_up_options`.

# --- TYPICAL CONVERSATION PATTERNS (Examples, Not Rigid Rules) ---
- **Pain:** Often helpful to clarify location -> intensity/type -> duration -> triggers/what makes it better/worse -> associated symptoms.
- **General Symptoms (e.g., cough, fatigue):** Often helpful to clarify onset/duration -> severity/frequency -> characteristics (e.g., dry/wet cough) -> associated symptoms.
- **Follow the user's lead:** If they provide information out of this order, adapt your questioning logically.

# --- ADAPTIVE INSTRUCTIONS (Pay attention to these if they appear before the user message) ---
- (Instructions like 'High Severity Detected', 'Non-Medical Query', 'Sufficient Info Available' help guide focus for the turn)

Now, carefully analyze the conversation history and the latest user message, apply the TONE & STYLE, follow the CORE FLOW, prioritize SAFETY, and generate the appropriate JSON response.
""" # Ensure this closing triple quote is present and correct

        # Construct history
        formatted_history = []
        # Add the main system prompt first
        formatted_history.append({"role": "user", "parts": [initial_system_prompt]})
        # Add the model's confirmation / understanding
        formatted_history.append({
            "role": "model",
            "parts": [json.dumps({ # Must be valid JSON matching schema
                "response": "Understood. I am MedAssist. I will follow the conversation rules, use interactive components when possible to minimize typing, ask follow-ups for initial symptoms, provide structured responses when ready, handle non-medical queries, and always prioritize safety and the required JSON format.",
                "needs_follow_up": False,
                "follow_up_question": "",
                "follow_up_type": "select", # Default to select instead of text
                "follow_up_options": [],
                "rate_symptoms": False,
                "symptoms_to_rate": [],
                "is_medical_related": True, # Default assumption
                "is_medical_related_prompt": "Yes", # Default assumption
                "can_provide_structured_response": False,
                "conversation_complete": False,
                "current_step": 0,
                "total_steps": 0,
                "Symptoms": ".",
                "Remedies": "",
                "Precautions": "",
                "Guidelines": "",
                "medication": [],
                "Disclaimer": STANDARD_DISCLAIMER,
                "image_search_term": ""
            })]
        })

        # Add actual conversation history if provided
        if conversation_history:
             # Make sure history items have the correct structure
             for entry in conversation_history:
                 if isinstance(entry, dict) and "role" in entry and "parts" in entry:
                     # Ensure parts is a list of strings
                     if isinstance(entry["parts"], list) and all(isinstance(p, str) for p in entry["parts"]):
                          formatted_history.append(entry)
                     elif isinstance(entry["parts"], str): # Handle case where parts was just a string
                          formatted_history.append({"role": entry["role"], "parts": [entry["parts"]]})
                 elif isinstance(entry, dict) and "role" in entry and "message" in entry: # Adapt old format
                      formatted_history.append({"role": entry["role"], "parts": [str(entry["message"])]})


        # --- Adaptive Prompting Logic --- (Soften the step-based instructions)
        is_initial_symptom = conversation_history is None or len(conversation_history) == 0
        message_lower = message.lower()
        is_rating_response = "rating" in message_lower and re.search(r'\d\s*/\s*10', message_lower) is not None

        conversation_step = 1
        estimated_total_steps = 4 # Default estimate
        if conversation_history:
            conversation_step = (len(conversation_history) // 2) + 1

        message_to_send = message
        instruction_prefix = ""

        # --- (Keep Non-Medical and High Severity detection as is) ---
        non_medical_keywords = ['weather', 'time', 'joke', 'sports', 'movie', 'music', 'news', 'history', 'capital', 'translate']
        if not any(term in message_lower for term in ['health', 'medical', 'doctor', 'symptom', 'pain', 'sick', 'ill', 'condition', 'treat', 'fever', 'cough', 'ache', 'nausea', 'rash']) \
           and any(term in message_lower for term in non_medical_keywords):
             instruction_prefix = "INSTRUCTION: Non-Medical Query. Set is_medical_related=false, is_medical_related_prompt='No'. Explain focus. Set complete=true, needs_follow_up=false.\n\n"
        elif any(term in message_lower for term in ['severe', 'worst', 'unbearable', 'intense', 'extreme', 'emergency', 'ambulance', 'hospital now', 'urgent care', 'pass out', 'faint', 'chest pain', 'difficulty breathing', 'stroke symptoms']):
             instruction_prefix = "INSTRUCTION: High Severity Detected. Prioritize recommending immediate professional help. Provide detailed home care/precautions (5+ points each) while waiting for help. Set complete=true.\n\n"

        # --- Soften Step-Based Guidance ---
        elif is_initial_symptom and any(term in message_lower for term in ['symptom', 'pain', 'sick', 'ill', 'condition', 'fever', 'cough', 'ache', 'nausea', 'rash', 'headache', 'feel']):
             # Estimate steps based on symptom type (keep this estimation)
             if any(term in message_lower for term in ['headache', 'head', 'migraine']): estimated_total_steps = 4
             elif any(term in message_lower for term in ['stomach', 'nausea', 'vomit', 'diarrhea']): estimated_total_steps = 4
             elif any(term in message_lower for term in ['fever', 'temperature']): estimated_total_steps = 3
             elif any(term in message_lower for term in ['cough', 'breathing']): estimated_total_steps = 4
             elif any(term in message_lower for term in ['rash', 'skin']): estimated_total_steps = 5
             else: estimated_total_steps = 4 # Default
             # Softened Instruction
             instruction_prefix = f"INSTRUCTION: Initial Symptom Query (Approx. Step 1 of {estimated_total_steps}). Ask the most logical first follow-up question based on the symptom (e.g., location, primary characteristic). Use interactive components. Set needs_follow_up=true, complete=false. Set current_step=1, total_steps={estimated_total_steps}.\n\n"

        # General follow-up guidance (less tied to specific step numbers)
        elif conversation_history and not is_rating_response: # If it's not an initial query or rating response
            # Estimate total steps based on history if possible (rough check)
            try:
                last_model_turn_str = conversation_history[-1]['parts'][0]
                last_model_data = json.loads(last_model_turn_str)
                if 'total_steps' in last_model_data and last_model_data['total_steps'] > 0:
                    estimated_total_steps = last_model_data['total_steps']
                elif 'current_step' in last_model_data and last_model_data['current_step'] > 0:
                     estimated_total_steps = max(4, last_model_data['current_step'] + 2) # Estimate a few more steps
            except (IndexError, KeyError, json.JSONDecodeError):
                pass # Keep default estimate

            # Check if enough info might be present (e.g., after 3-4 exchanges)
            if conversation_step >= estimated_total_steps:
                 instruction_prefix = f"INSTRUCTION: Likely Sufficient Info Gathered (Approx. Step {conversation_step}/{estimated_total_steps}). Evaluate if ready for summary. If yes, provide full structured response (brief conversational part), set complete=true. If NO, ask ONE final clarifying question. \n\n"
            else:
                 # Generic instruction to continue gathering info
                 instruction_prefix = f"INSTRUCTION: Continuing Conversation (Approx. Step {conversation_step}/{estimated_total_steps}). Ask the next logical follow-up question based on the history and last user message. Use interactive components. Set needs_follow_up=true, complete=false. Set current_step={conversation_step}, total_steps={estimated_total_steps}.\n\n"

        # --- (Keep handling for rating response and sufficient info detection similar, maybe simplify) ---
        elif is_rating_response:
             instruction_prefix = f"INSTRUCTION: User provided symptom rating (Approx. Step {conversation_step}/{estimated_total_steps}). Process rating. Ask next logical follow-up OR provide summary if sufficient info gathered. Update steps accordingly. \n\n"
        elif conversation_history and len(conversation_history) >= 10: # Fallback completion check
             instruction_prefix = "INSTRUCTION: Sufficient Info Likely Available (long conversation). Provide a full, detailed structured response. Keep the main conversational 'response' field BRIEF. Set complete=true, needs_follow_up=false.\n\n"

        # --- Send Message & Process Response ---
        chat_session = model.start_chat(history=formatted_history)
        final_message_content = instruction_prefix + message # Prepend instruction if any

        # --- ADDED: Retry Logic ---
        response = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logging.info(f"Attempting Gemini API call ({attempt + 1}/{max_retries})...")
                response = chat_session.send_message(final_message_content)
                logging.info(f"Gemini API call successful on attempt {attempt + 1}")
                break # Exit loop on success
            except Exception as send_error:
                logging.warning(f"Gemini API call failed on attempt {attempt + 1}/{max_retries}: {send_error}")
                if attempt < max_retries - 1:
                    time.sleep(1) # Wait 1 second before retrying
                else:
                    logging.error("Gemini API call failed after multiple retries.")
                    raise send_error # Re-raise the exception to be caught by the outer handler

        # If response is still None after loop (shouldn't happen if raise works, but as a safeguard)
        if response is None:
             logging.error("Response object is None after retry loop, raising generic error.")
             raise Exception("Failed to get response from Gemini API after multiple retries.")
        # --- End of Retry Logic ---


        response_dict = json.loads(response.text)

        # --- Post-processing and Default Setting ---
        # Clean response text - REMOVED markdown_to_plain_text for the main response
        # response_dict["response"] = markdown_to_plain_text(response_dict.get("response", ""))
        # Ensure response field exists even if empty after potential removal above
        response_dict.setdefault("response", "")

        # Ensure progress tracking fields are set based on conversation state
        if "current_step" not in response_dict or response_dict["current_step"] == 0:
            response_dict["current_step"] = conversation_step
        
        if "total_steps" not in response_dict or response_dict["total_steps"] == 0:
            response_dict["total_steps"] = estimated_total_steps

        # Set defaults robustly for all defined schema fields
        response_dict.setdefault("needs_follow_up", False)
        response_dict.setdefault("follow_up_question", "" if not response_dict.get("needs_follow_up") else response_dict.get("follow_up_question", "Could you tell me more?")) # Ensure empty if no follow-up
        response_dict.setdefault("follow_up_type", "select") # Default to select instead of text
        
        # If follow-up is needed but no options are provided, add default options based on follow-up type
        if response_dict.get("needs_follow_up", False):
            follow_up_type = response_dict.get("follow_up_type", "select")
            follow_up_options = response_dict.get("follow_up_options", [])
            
            if follow_up_type == "select" and not follow_up_options:
                # Detect duration questions
                if any(term in response_dict.get("follow_up_question", "").lower() for term in ["duration", "how long", "when did", "since when"]):
                    response_dict["follow_up_options"] = ["Less than a day", "1-3 days", "4-7 days", "1-2 weeks", "More than 2 weeks"]
                # Detect yes/no questions
                elif response_dict.get("follow_up_question", "").endswith("?") and len(response_dict.get("follow_up_question", "").split()) < 15:
                    response_dict["follow_up_options"] = ["Yes", "No", "Not sure"]
                # Default select options
                else:
                    response_dict["follow_up_options"] = ["Yes", "No", "Sometimes", "Not sure"]
            
            elif follow_up_type == "multiselect" and not follow_up_options:
                # Try to identify symptom-related questions
                if any(term in response_dict.get("follow_up_question", "").lower() for term in ["symptom", "experience", "feeling", "notice"]):
                    response_dict["follow_up_options"] = ["Fever", "Headache", "Nausea", "Dizziness", "Fatigue", "Cough", "Runny nose", "Sore throat", "None of these"]
                # Default multiselect options
                else:
                    response_dict["follow_up_options"] = ["Option 1", "Option 2", "Option 3", "None of these"]
            
            # If follow-up is needed but type is text, try to convert to select if possible
            if follow_up_type == "text":
                follow_up_question = response_dict.get("follow_up_question", "").lower()
                
                # Convert duration questions to select
                if any(term in follow_up_question for term in ["how long", "duration", "when did", "since when"]):
                    response_dict["follow_up_type"] = "select"
                    response_dict["follow_up_options"] = ["Less than a day", "1-3 days", "4-7 days", "1-2 weeks", "More than 2 weeks"]
                
                # Convert yes/no questions to select
                elif follow_up_question.endswith("?") and len(follow_up_question.split()) < 15:
                    response_dict["follow_up_type"] = "select"
                    response_dict["follow_up_options"] = ["Yes", "No", "Not sure"]
                
                # Convert symptom-related questions to multiselect
                elif any(term in follow_up_question for term in ["symptom", "experience", "feeling", "notice"]):
                    response_dict["follow_up_type"] = "multiselect"
                    response_dict["follow_up_options"] = ["Fever", "Headache", "Nausea", "Dizziness", "Fatigue", "Cough", "Runny nose", "Sore throat", "None of these"]
                
                # Convert severity/intensity questions to scale
                elif any(term in follow_up_question for term in ["pain", "severe", "intensity", "scale", "rate", "level"]):
                    response_dict["follow_up_type"] = "scale"
                    # Ensure we have a follow-up question for scale type
                    if not response_dict.get("follow_up_question"):
                        symptom = response_dict.get("Symptoms", "").strip(".")
                        if symptom:
                            response_dict["follow_up_question"] = f"On a scale of 1 to 10, how would you rate your {symptom}?"
                        else:
                            response_dict["follow_up_question"] = "On a scale of 1 to 10, how would you rate the severity?"
        
        # For scale type, always ensure we have a question
        if response_dict.get("follow_up_type") == "scale" and not response_dict.get("follow_up_question"):
            symptom = response_dict.get("Symptoms", "").strip(".")
            if symptom:
                response_dict["follow_up_question"] = f"On a scale of 1 to 10, how would you rate your {symptom}?"
            else:
                response_dict["follow_up_question"] = "On a scale of 1 to 10, how would you rate the severity?"
        
        # Other default fields
        response_dict.setdefault("rate_symptoms", False)
        response_dict.setdefault("symptoms_to_rate", [])
        response_dict.setdefault("is_medical_related", True) # Default true unless classified otherwise
        # Set is_medical_related_prompt based on boolean if missing
        response_dict.setdefault("is_medical_related_prompt", "Yes" if response_dict.get("is_medical_related", True) else "No")
        response_dict.setdefault("can_provide_structured_response", False)
        response_dict.setdefault("conversation_complete", False)
        response_dict.setdefault("current_step", 0)
        response_dict.setdefault("total_steps", 0)
        response_dict.setdefault("Symptoms", ".")
        response_dict.setdefault("Remedies", "")
        response_dict.setdefault("Precautions", "")
        response_dict.setdefault("Guidelines", "")
        response_dict.setdefault("medication", [])
        response_dict.setdefault("Disclaimer", STANDARD_DISCLAIMER)
        # --- ADDED: Default for image_search_term ---
        response_dict.setdefault("image_search_term", "")


        # --- Logic Enforcement & Post-Processing ---

        # --- ADDED: Post-process medication list for spacing ---
        if isinstance(response_dict.get("medication"), list):
            processed_meds = []
            for med in response_dict["medication"]:
                if isinstance(med, str):
                    # Use regex to split based on lowercase followed by uppercase (e.g., "IbuprofenAcetaminophen")
                    # This also handles single words correctly.
                    split_meds = re.findall(r'[A-Z][a-z]*', med)
                    if split_meds: # If regex found capitalized words
                        processed_meds.extend(split_meds)
                    else:
                        processed_meds.append(med) # Keep original if no pattern matched
                else:
                    # Keep non-string items as is, though schema expects strings
                    processed_meds.append(med)
            response_dict["medication"] = processed_meds
        # ----------------------------------------------------

        # --- ADDED: Force brief response when structured data is present ---
        if response_dict.get("can_provide_structured_response"):
            # Overwrite the potentially verbose AI response with a standard brief one
            response_dict["response"] = "Okay, here is a summary based on our conversation. Please review the details below."
            print("--- Overwriting conversational response with brief summary message. ---")
        # ------------------------------------------------------------------

        # If conversation is complete, it shouldn't need follow-up
        if response_dict["conversation_complete"]:
            response_dict["needs_follow_up"] = False
            response_dict["follow_up_question"] = ""
            # If complete and medical, it *should* provide structured response
            if response_dict["is_medical_related"]:
                 response_dict["can_provide_structured_response"] = True
                 # Ensure key fields aren't trivially empty if complete & medical
                 if not response_dict.get("Symptoms") or response_dict.get("Symptoms") == ".":
                      response_dict["Symptoms"] = "Symptom details were discussed." # Or extract from history
                 if not response_dict.get("Remedies"):
                      response_dict["Remedies"] = "General self-care advice applies. Stay hydrated, rest."
                 if not response_dict.get("Precautions"):
                     response_dict["Precautions"] = "Avoid strenuous activity. Monitor symptoms."
                 if not response_dict.get("Guidelines"):
                     response_dict["Guidelines"] = "Consult a doctor if symptoms worsen or persist."


        # If not medical, ensure structured fields are cleared and flags set correctly
        if not response_dict["is_medical_related"]:
            response_dict["can_provide_structured_response"] = False
            response_dict["Symptoms"] = "." # Keep . for consistency or set to ""
            response_dict["Remedies"] = ""
            response_dict["Precautions"] = ""
            response_dict["Guidelines"] = ""
            response_dict["medication"] = []
            response_dict["needs_follow_up"] = False # Non-medical shouldn't need follow-up
            response_dict["conversation_complete"] = True # Non-medical is usually single turn

        # Ensure boolean and string flags are consistent
        if response_dict["is_medical_related"] and response_dict["is_medical_related_prompt"] == "No":
            print("Warning: Correcting is_medical_related_prompt to 'Yes' based on is_medical_related=true")
            response_dict["is_medical_related_prompt"] = "Yes"
        elif not response_dict["is_medical_related"] and response_dict["is_medical_related_prompt"] == "Yes":
             print("Warning: Correcting is_medical_related_prompt to 'No' based on is_medical_related=false")
             response_dict["is_medical_related_prompt"] = "No"

        # --- ADDED: Disease-specific medication mapping ---
        disease_medication_map = {
            "cold": ["Acetaminophen", "Decongestants", "Cough suppressants"],
            "flu": ["Acetaminophen", "Ibuprofen", "Decongestants"],
            "headache": ["Acetaminophen", "Ibuprofen", "Aspirin"],
            "migraine": ["Acetaminophen", "Ibuprofen", "Aspirin"],
            "fever": ["Acetaminophen", "Ibuprofen"],
            "cough": ["Cough suppressants", "Expectorants"],
            "sore throat": ["Throat lozenges", "Salt water gargle"],
            "allergies": ["Antihistamines", "Nasal corticosteroids"],
            "acid reflux": ["Antacids", "H2 blockers"],
            "diarrhea": ["Loperamide", "Bismuth subsalicylate"],
            "constipation": ["Fiber supplements", "Stool softeners"],
            "rash": ["Antihistamine cream", "Hydrocortisone cream"],
            "pain": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "nausea": ["Ginger supplements", "Antacids"],
            "indigestion": ["Antacids", "H2 blockers"],
            "heartburn": ["Antacids", "H2 blockers"],
            "back pain": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "joint pain": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "muscle pain": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "ear pain": ["Acetaminophen", "Ibuprofen"],
            "sinus": ["Decongestants", "Nasal corticosteroids"],
            "bronchitis": ["Cough suppressants", "Expectorants"],
            "pneumonia": ["Acetaminophen", "Ibuprofen"],
            "asthma": ["Bronchodilators"],  # Note: Usually prescription
            "anxiety": ["Herbal supplements"],  # Note: Usually prescription
            "insomnia": ["Melatonin", "Herbal supplements"],
            "dermatitis": ["Antihistamine cream", "Hydrocortisone cream"],
            "eczema": ["Antihistamine cream", "Hydrocortisone cream"],
            "psoriasis": ["Coal tar", "Salicylic acid"],
            "acne": ["Benzoyl peroxide", "Salicylic acid"],
            "sunburn": ["Aloe vera", "Topical analgesics"],
            "burns": ["Aloe vera", "Topical analgesics"],
            "cuts": ["Antibiotic ointment", "Antiseptic"],
            "bruises": ["Arnica", "Topical analgesics"],
            "sprains": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "strains": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "arthritis": ["Acetaminophen", "Ibuprofen", "Topical analgesics"],
            "gout": ["Acetaminophen", "Ibuprofen"],
            "diabetes": [],  # Note: Usually prescription
            "hypertension": [],  # Note: Usually prescription
            "cholesterol": [],  # Note: Usually prescription
            "thyroid": [],  # Note: Usually prescription
            "depression": [],  # Note: Usually prescription
            "adhd": [],  # Note: Usually prescription
            "epilepsy": [],  # Note: Usually prescription
            "parkinsons": [],  # Note: Usually prescription
            "alzheimers": [],  # Note: Usually prescription
            "cancer": [],  # Note: Usually prescription
            "hiv": [],  # Note: Usually prescription
            "hepatitis": [],  # Note: Usually prescription
            "tuberculosis": [],  # Note: Usually prescription
            "malaria": [],  # Note: Usually prescription
            "dengue": ["Acetaminophen"],  # Note: Avoid NSAIDs
            "chikungunya": ["Acetaminophen"],  # Note: Avoid NSAIDs
            "zika": ["Acetaminophen"],  # Note: Avoid NSAIDs
            "covid": ["Acetaminophen", "Ibuprofen"],
            "measles": ["Acetaminophen", "Ibuprofen"],
            "mumps": ["Acetaminophen", "Ibuprofen"],
            "rubella": ["Acetaminophen", "Ibuprofen"],
            "chickenpox": ["Acetaminophen", "Antihistamines"],
            "shingles": ["Acetaminophen", "Antihistamines"],
            "herpes": ["Antiviral cream"],  # Note: Usually prescription
            "warts": ["Salicylic acid", "Cryotherapy"],
            "fungal infection": ["Antifungal cream", "Antifungal powder"],
            "yeast infection": ["Antifungal cream", "Antifungal suppositories"],
            "uti": ["Cranberry supplements", "Pain relievers"],
            "kidney stones": ["Acetaminophen", "Ibuprofen"],
            "gallstones": ["Acetaminophen", "Ibuprofen"],
            "appendicitis": [],  # Note: Requires surgery
            "hernia": [],  # Note: Usually requires surgery
            "ulcer": ["Antacids", "H2 blockers"],
            "gastritis": ["Antacids", "H2 blockers"],
            "colitis": ["Antidiarrheals", "Antispasmodics"],
            "crohns": [],  # Note: Usually prescription
            "celiac": [],  # Note: Requires diet change
            "lactose intolerance": ["Lactase supplements"],
            "gluten intolerance": [],  # Note: Requires diet change
            "food poisoning": ["Antidiarrheals", "Antiemetics"],
            "dehydration": ["Oral rehydration salts"],
            "vitamin deficiency": ["Multivitamins"],
            "iron deficiency": ["Iron supplements"],
            "calcium deficiency": ["Calcium supplements"],
            "vitamin d deficiency": ["Vitamin D supplements"],
            "vitamin b12 deficiency": ["Vitamin B12 supplements"],
            "folate deficiency": ["Folate supplements"],
            "zinc deficiency": ["Zinc supplements"],
            "magnesium deficiency": ["Magnesium supplements"],
            "potassium deficiency": ["Potassium supplements"],
            "sodium deficiency": ["Oral rehydration salts"],
            "protein deficiency": ["Protein supplements"],
            "omega 3 deficiency": ["Omega-3 supplements"],
            "fiber deficiency": ["Fiber supplements"],
            "probiotic deficiency": ["Probiotic supplements"],
            "enzyme deficiency": ["Digestive enzymes"],
            "hormone deficiency": [],  # Note: Usually prescription
            "immune deficiency": [],  # Note: Usually prescription
            "autoimmune": [],  # Note: Usually prescription
            "allergic reaction": ["Antihistamines", "Epinephrine"],  # Note: Epinephrine usually prescription
            "anaphylaxis": ["Epinephrine"],  # Note: Usually prescription
            "septic shock": [],  # Note: Requires emergency care
            "cardiac arrest": [],  # Note: Requires emergency care
            "stroke": [],  # Note: Requires emergency care
            "heart attack": [],  # Note: Requires emergency care
            "pulmonary embolism": [],  # Note: Requires emergency care
            "deep vein thrombosis": [],  # Note: Usually prescription
            "aneurysm": [],  # Note: Usually requires surgery
            "varicose veins": ["Compression stockings"],
            "hemorrhoids": ["Topical analgesics", "Stool softeners"],
            "anal fissure": ["Topical analgesics", "Stool softeners"],
            "prostatitis": ["Antibiotics"],  # Note: Usually prescription
            "benign prostatic hyperplasia": [],  # Note: Usually prescription
            "prostate cancer": [],  # Note: Usually prescription
            "breast cancer": [],  # Note: Usually prescription
            "cervical cancer": [],  # Note: Usually prescription
            "ovarian cancer": [],  # Note: Usually prescription
            "uterine cancer": [],  # Note: Usually prescription
            "testicular cancer": [],  # Note: Usually prescription
            "bladder cancer": [],  # Note: Usually prescription
            "kidney cancer": [],  # Note: Usually prescription
            "liver cancer": [],  # Note: Usually prescription
            "pancreatic cancer": [],  # Note: Usually prescription
            "stomach cancer": [],  # Note: Usually prescription
            "esophageal cancer": [],  # Note: Usually prescription
            "colon cancer": [],  # Note: Usually prescription
            "rectal cancer": [],  # Note: Usually prescription
            "lung cancer": [],  # Note: Usually prescription
            "brain cancer": [],  # Note: Usually prescription
            "bone cancer": [],  # Note: Usually prescription
            "skin cancer": [],  # Note: Usually requires surgery
            "leukemia": [],  # Note: Usually prescription
            "lymphoma": [],  # Note: Usually prescription
            "multiple myeloma": [],  # Note: Usually prescription
            "sarcoma": [],  # Note: Usually prescription
            "mesothelioma": [],  # Note: Usually prescription
            "neuroblastoma": [],  # Note: Usually prescription
            "retinoblastoma": [],  # Note: Usually prescription
            "wilms tumor": [],  # Note: Usually prescription
            "osteosarcoma": [],  # Note: Usually prescription
            "ewing sarcoma": [],  # Note: Usually prescription
            "rhabdomyosarcoma": [],  # Note: Usually prescription
            "hepatoblastoma": [],  # Note: Usually prescription
            "hepatocellular carcinoma": [],  # Note: Usually prescription
            "cholangiocarcinoma": [],  # Note: Usually prescription
            "gallbladder cancer": [],  # Note: Usually prescription
            "bile duct cancer": [],  # Note: Usually prescription
            "ampullary cancer": [],  # Note: Usually prescription
            "duodenal cancer": [],  # Note: Usually prescription
            "jejunal cancer": [],  # Note: Usually prescription
            "ileal cancer": [],  # Note: Usually prescription
            "cecal cancer": [],  # Note: Usually prescription
            "appendiceal cancer": [],  # Note: Usually prescription
            "anal cancer": [],  # Note: Usually prescription
            "penile cancer": [],  # Note: Usually prescription
            "vaginal cancer": [],  # Note: Usually prescription
            "vulvar cancer": [],  # Note: Usually prescription
            "fallopian tube cancer": [],  # Note: Usually prescription
            "peritoneal cancer": [],  # Note: Usually prescription
            "adrenal cancer": [],  # Note: Usually prescription
            "thyroid cancer": [],  # Note: Usually prescription
            "parathyroid cancer": [],  # Note: Usually prescription
            "pituitary cancer": [],  # Note: Usually prescription
            "pancreatic neuroendocrine tumor": [],  # Note: Usually prescription
            "carcinoid tumor": [],  # Note: Usually prescription
            "pheochromocytoma": [],  # Note: Usually prescription
            "paraganglioma": [],  # Note: Usually prescription
            "medullary thyroid cancer": [],  # Note: Usually prescription
            "anaplastic thyroid cancer": [],  # Note: Usually prescription
            "papillary thyroid cancer": [],  # Note: Usually prescription
            "follicular thyroid cancer": [],  # Note: Usually prescription
            "hurthle cell thyroid cancer": [],  # Note: Usually prescription
            "thyroid lymphoma": [],  # Note: Usually prescription
            "thyroid sarcoma": [],  # Note: Usually prescription
            "thyroid teratoma": [],  # Note: Usually prescription
            "thyroid metastasis": [],  # Note: Usually prescription
            "thyroid adenoma": [],  # Note: Usually prescription
            "thyroid nodule": [],  # Note: Usually prescription
            "thyroid goiter": [],  # Note: Usually prescription
            "thyroiditis": [],  # Note: Usually prescription
            "graves disease": [],  # Note: Usually prescription
            "hashimotos thyroiditis": [],  # Note: Usually prescription
            "subacute thyroiditis": [],  # Note: Usually prescription
            "postpartum thyroiditis": [],  # Note: Usually prescription
            "silent thyroiditis": [],  # Note: Usually prescription
            "drug induced thyroiditis": [],  # Note: Usually prescription
            "radiation induced thyroiditis": [],  # Note: Usually prescription
            "trauma induced thyroiditis": [],  # Note: Usually prescription
            "infectious thyroiditis": [],  # Note: Usually prescription
            "acute thyroiditis": [],  # Note: Usually prescription
            "chronic thyroiditis": [],  # Note: Usually prescription
            "recurrent thyroiditis": [],  # Note: Usually prescription
            "subclinical thyroiditis": [],  # Note: Usually prescription
            "euthyroid sick syndrome": [],  # Note: Usually prescription
            "thyroid storm": [],  # Note: Usually prescription
            "myxedema coma": [],  # Note: Usually prescription
            "thyroid eye disease": [],  # Note: Usually prescription
            "thyroid dermopathy": [],  # Note: Usually prescription
            "thyroid acropachy": [],  # Note: Usually prescription
        }

        # --- ADDED: Function to get disease-specific medications ---
        def get_disease_specific_medications(symptoms_text, remedies_text):
            """Extract disease-specific medications based on symptoms and remedies."""
            # Convert text to lowercase for matching
            symptoms_lower = symptoms_text.lower()
            remedies_lower = remedies_text.lower()
            
            # Disease-specific medication mapping
            disease_medication_map = {
                "cold": ["Decongestants", "Antihistamines", "Cough suppressants"],
                "flu": ["Antiviral medications", "Acetaminophen", "Ibuprofen"],
                "headache": ["Acetaminophen", "Ibuprofen", "Aspirin"],
                "migraine": ["Triptans", "NSAIDs", "Anti-nausea medications"],
                "fever": ["Acetaminophen", "Ibuprofen", "Aspirin"],
                "cough": ["Dextromethorphan", "Guaifenesin", "Codeine-based cough syrup"],
                "sore throat": ["Throat lozenges", "Benzocaine spray", "Salt water gargle"],
                "allergies": ["Antihistamines", "Decongestants", "Nasal corticosteroids"],
                "acid reflux": ["Antacids", "H2 blockers", "Proton pump inhibitors"],
                "diarrhea": ["Loperamide", "Bismuth subsalicylate", "Oral rehydration solutions"],
                "constipation": ["Fiber supplements", "Stool softeners", "Osmotic laxatives"],
                "rash": ["Antihistamine cream", "Hydrocortisone cream", "Calamine lotion"],
                "back pain": ["NSAIDs", "Muscle relaxants", "Topical analgesics"],
                "joint pain": ["NSAIDs", "Topical analgesics", "Joint supplements"],
                "sinus": ["Decongestants", "Nasal corticosteroids", "Saline nasal spray"],
                "bronchitis": ["Bronchodilators", "Expectorants", "Cough suppressants"],
                "pneumonia": ["Antibiotics", "Cough suppressants", "Fever reducers"],
                "asthma": ["Bronchodilators", "Inhaled corticosteroids", "Leukotriene modifiers"],
                "dermatitis": ["Topical corticosteroids", "Antihistamines", "Moisturizing creams"],
                "eczema": ["Topical corticosteroids", "Antihistamines", "Emollients"],
                "psoriasis": ["Topical corticosteroids", "Vitamin D analogs", "Coal tar preparations"],
                "acne": ["Benzoyl peroxide", "Salicylic acid", "Topical antibiotics"],
                "sunburn": ["Aloe vera gel", "Hydrocortisone cream", "Pain relievers"],
                "burns": ["Antibiotic ointments", "Pain relievers", "Burn creams"],
                "cuts": ["Antibiotic ointments", "Antiseptic solutions", "Sterile dressings"],
                "bruises": ["Arnica gel", "Pain relievers", "Compression bandages"],
                "sprains": ["NSAIDs", "Compression bandages", "Topical analgesics"],
                "strains": ["NSAIDs", "Muscle relaxants", "Topical analgesics"]
            }
            
            # Initialize empty list for medications
            medications = []
            
            # First try to match based on specific diseases
            for disease, meds in disease_medication_map.items():
                if disease in symptoms_lower or disease in remedies_lower:
                    medications.extend(meds)
                    break  # Only use medications for the first matching disease
            
            # If no specific disease was found, try to match based on symptom patterns
            if not medications:
                # More specific symptom-based medication matching
                if "fever" in symptoms_lower and "chills" in symptoms_lower:
                    medications.extend(["Acetaminophen", "Ibuprofen", "Antiviral medications"])
                elif "fever" in symptoms_lower:
                    medications.extend(["Acetaminophen", "Ibuprofen"])
                elif "cough" in symptoms_lower and "chest pain" in symptoms_lower:
                    medications.extend(["Bronchodilators", "Expectorants", "Cough suppressants"])
                elif "cough" in symptoms_lower:
                    medications.extend(["Dextromethorphan", "Guaifenesin"])
                elif "sore throat" in symptoms_lower and "fever" in symptoms_lower:
                    medications.extend(["Throat lozenges", "Antibiotics", "Pain relievers"])
                elif "sore throat" in symptoms_lower:
                    medications.extend(["Throat lozenges", "Salt water gargle"])
                elif "headache" in symptoms_lower and "nausea" in symptoms_lower:
                    medications.extend(["Triptans", "Anti-nausea medications"])
                elif "headache" in symptoms_lower:
                    medications.extend(["Acetaminophen", "Ibuprofen"])
                elif "rash" in symptoms_lower and "itching" in symptoms_lower:
                    medications.extend(["Antihistamine cream", "Hydrocortisone cream"])
                elif "rash" in symptoms_lower:
                    medications.extend(["Calamine lotion", "Antihistamine cream"])
                elif "nausea" in symptoms_lower and "vomiting" in symptoms_lower:
                    medications.extend(["Anti-nausea medications", "Oral rehydration solutions"])
                elif "nausea" in symptoms_lower:
                    medications.extend(["Ginger supplements", "Antacids"])
                elif "diarrhea" in symptoms_lower:
                    medications.extend(["Loperamide", "Oral rehydration solutions"])
                elif "constipation" in symptoms_lower:
                    medications.extend(["Fiber supplements", "Stool softeners"])
            
            # Remove duplicates and limit to 3 medications
            medications = list(dict.fromkeys(medications))[:3]
            
            return medications

        # --- ADDED: Update medication list based on symptoms and remedies ---
        if response_dict.get("can_provide_structured_response") and response_dict.get("is_medical_related"):
            symptoms = response_dict.get("Symptoms", "")
            remedies = response_dict.get("Remedies", "")
            
            # Get disease-specific medications
            medications = get_disease_specific_medications(symptoms, remedies)
            
            # Update the medication list in the response
            response_dict["medication"] = medications

        # --- ADDED: Disease-specific remedies mapping ---
        disease_remedies_map = {
            "cold": [
                "Rest and get plenty of sleep",
                "Stay hydrated with warm fluids like tea or soup",
                "Use a humidifier to add moisture to the air",
                "Gargle with warm salt water for sore throat",
                "Use saline nasal drops for congestion"
            ],
            "flu": [
                "Get plenty of rest and sleep",
                "Stay hydrated with water and electrolyte drinks",
                "Use a humidifier to ease breathing",
                "Take warm baths to reduce body aches",
                "Apply warm compresses for sinus pain"
            ],
            "headache": [
                "Rest in a quiet, dark room",
                "Apply cold or warm compress to head/neck",
                "Practice relaxation techniques",
                "Stay hydrated",
                "Avoid screen time and bright lights"
            ],
            "migraine": [
                "Rest in a dark, quiet room",
                "Apply cold compress to head",
                "Stay hydrated",
                "Avoid triggers like bright lights and strong smells",
                "Try gentle neck stretches"
            ],
            "fever": [
                "Rest and stay hydrated",
                "Take lukewarm baths",
                "Dress in light clothing",
                "Keep room temperature comfortable",
                "Use cold compresses on forehead"
            ],
            "cough": [
                "Stay hydrated with warm fluids",
                "Use a humidifier",
                "Try honey for natural relief",
                "Elevate head while sleeping",
                "Avoid irritants like smoke and strong perfumes"
            ],
            "sore throat": [
                "Gargle with warm salt water",
                "Stay hydrated with warm fluids",
                "Use throat lozenges",
                "Rest your voice",
                "Use a humidifier"
            ],
            "allergies": [
                "Avoid known allergens",
                "Use air purifiers",
                "Keep windows closed during high pollen times",
                "Wash hands and face after being outdoors",
                "Use hypoallergenic bedding"
            ],
            "acid reflux": [
                "Eat smaller, more frequent meals",
                "Avoid lying down after eating",
                "Elevate head of bed",
                "Avoid trigger foods (spicy, fatty, acidic)",
                "Maintain healthy weight"
            ],
            "diarrhea": [
                "Stay hydrated with oral rehydration solutions",
                "Follow BRAT diet (Bananas, Rice, Applesauce, Toast)",
                "Avoid dairy and fatty foods",
                "Rest and avoid strenuous activity",
                "Practice good hand hygiene"
            ],
            "constipation": [
                "Increase fiber intake",
                "Stay hydrated",
                "Exercise regularly",
                "Establish regular bathroom routine",
                "Avoid processed foods"
            ],
            "rash": [
                "Keep affected area clean and dry",
                "Avoid scratching",
                "Use gentle, fragrance-free soap",
                "Wear loose, cotton clothing",
                "Apply cool compresses"
            ],
            "back pain": [
                "Practice good posture",
                "Use proper lifting techniques",
                "Apply heat or cold therapy",
                "Do gentle stretches",
                "Maintain healthy weight"
            ],
            "joint pain": [
                "Apply heat or cold therapy",
                "Do gentle exercises",
                "Maintain healthy weight",
                "Use proper posture",
                "Consider low-impact activities"
            ],
            "sinus": [
                "Use saline nasal irrigation",
                "Apply warm compresses",
                "Stay hydrated",
                "Use a humidifier",
                "Avoid irritants like smoke"
            ],
            "bronchitis": [
                "Rest and stay hydrated",
                "Use a humidifier",
                "Avoid smoke and irritants",
                "Practice deep breathing exercises",
                "Take warm showers for steam"
            ],
            "pneumonia": [
                "Get plenty of rest",
                "Stay hydrated",
                "Use a humidifier",
                "Practice deep breathing exercises",
                "Maintain good nutrition"
            ],
            "asthma": [
                "Avoid triggers",
                "Use air purifiers",
                "Practice breathing exercises",
                "Maintain clean living environment",
                "Keep rescue inhaler accessible"
            ],
            "dermatitis": [
                "Keep skin moisturized",
                "Avoid harsh soaps",
                "Use fragrance-free products",
                "Wear cotton clothing",
                "Avoid scratching"
            ],
            "eczema": [
                "Moisturize regularly",
                "Use gentle, fragrance-free products",
                "Avoid hot showers",
                "Wear cotton clothing",
                "Manage stress"
            ],
            "psoriasis": [
                "Moisturize regularly",
                "Get moderate sun exposure",
                "Avoid stress",
                "Use gentle skin care products",
                "Maintain healthy diet"
            ],
            "acne": [
                "Keep face clean",
                "Avoid touching face",
                "Use non-comedogenic products",
                "Don't pop pimples",
                "Manage stress"
            ],
            "sunburn": [
                "Apply cool compresses",
                "Stay hydrated",
                "Use aloe vera gel",
                "Avoid sun exposure",
                "Wear loose clothing"
            ],
            "burns": [
                "Cool the burn with running water",
                "Keep area clean",
                "Don't pop blisters",
                "Apply sterile dressing",
                "Protect from sun"
            ],
            "cuts": [
                "Clean with soap and water",
                "Apply antibiotic ointment",
                "Cover with sterile bandage",
                "Keep area dry",
                "Change dressing regularly"
            ],
            "bruises": [
                "Apply ice pack",
                "Elevate affected area",
                "Rest the area",
                "Use compression if appropriate",
                "Avoid blood thinners"
            ],
            "sprains": [
                "Rest the joint",
                "Apply ice",
                "Use compression",
                "Elevate the limb",
                "Avoid weight-bearing"
            ],
            "strains": [
                "Rest the muscle",
                "Apply ice",
                "Use compression",
                "Elevate the limb",
                "Avoid strenuous activity"
            ],
            "arthritis": [
                "Maintain healthy weight",
                "Exercise regularly",
                "Use heat/cold therapy",
                "Practice joint protection",
                "Consider low-impact activities"
            ],
            "gout": [
                "Stay hydrated",
                "Avoid alcohol",
                "Limit purine-rich foods",
                "Maintain healthy weight",
                "Elevate affected joint"
            ],
            "uti": [
                "Stay hydrated",
                "Urinate frequently",
                "Wipe front to back",
                "Avoid irritants",
                "Use heating pad for pain"
            ],
            "kidney stones": [
                "Stay hydrated",
                "Limit salt intake",
                "Avoid oxalate-rich foods",
                "Use heating pad for pain",
                "Exercise regularly"
            ],
            "gallstones": [
                "Eat smaller, frequent meals",
                "Avoid fatty foods",
                "Stay hydrated",
                "Maintain healthy weight",
                "Exercise regularly"
            ],
            "ulcer": [
                "Eat smaller, frequent meals",
                "Avoid spicy and acidic foods",
                "Limit alcohol and caffeine",
                "Manage stress",
                "Avoid NSAIDs"
            ],
            "gastritis": [
                "Eat smaller, frequent meals",
                "Avoid irritants",
                "Limit alcohol and caffeine",
                "Manage stress",
                "Avoid NSAIDs"
            ],
            "colitis": [
                "Follow low-fiber diet during flare-ups",
                "Stay hydrated",
                "Avoid trigger foods",
                "Manage stress",
                "Get adequate rest"
            ],
            "food poisoning": [
                "Stay hydrated",
                "Follow BRAT diet",
                "Rest",
                "Avoid dairy and fatty foods",
                "Practice good hygiene"
            ],
            "dehydration": [
                "Drink water regularly",
                "Use oral rehydration solutions",
                "Avoid alcohol and caffeine",
                "Rest",
                "Monitor urine color"
            ]
        }

        # --- ADDED: Function to get disease-specific remedies ---
        def get_disease_specific_remedies(symptoms_text, remedies_text):
            """Extract disease-specific remedies based on symptoms and remedies."""
            # Convert text to lowercase for matching
            symptoms_lower = symptoms_text.lower()
            remedies_lower = remedies_text.lower()
            
            # Initialize empty list for remedies
            remedies = []
            
            # Check each disease in the map
            for disease, disease_remedies in disease_remedies_map.items():
                # If disease is mentioned in symptoms or remedies
                if disease in symptoms_lower or disease in remedies_lower:
                    # Add remedies for this disease
                    remedies.extend(disease_remedies)
            
            # If no specific disease was found, try to match based on symptoms
            if not remedies:
                # Common symptom patterns
                if "fever" in symptoms_lower or "chills" in symptoms_lower:
                    remedies.extend([
                        "Rest and stay hydrated",
                        "Take lukewarm baths",
                        "Dress in light clothing",
                        "Keep room temperature comfortable",
                        "Use cold compresses on forehead"
                    ])
                if "cough" in symptoms_lower:
                    remedies.extend([
                        "Stay hydrated with warm fluids",
                        "Use a humidifier",
                        "Try honey for natural relief",
                        "Elevate head while sleeping",
                        "Avoid irritants like smoke"
                    ])
                if "sore throat" in symptoms_lower:
                    remedies.extend([
                        "Gargle with warm salt water",
                        "Stay hydrated with warm fluids",
                        "Use throat lozenges",
                        "Rest your voice",
                        "Use a humidifier"
                    ])
                if "headache" in symptoms_lower:
                    remedies.extend([
                        "Rest in a quiet, dark room",
                        "Apply cold or warm compress",
                        "Practice relaxation techniques",
                        "Stay hydrated",
                        "Avoid screen time"
                    ])
                if "pain" in symptoms_lower:
                    remedies.extend([
                        "Rest the affected area",
                        "Apply heat or cold therapy",
                        "Stay hydrated",
                        "Practice gentle stretches",
                        "Maintain good posture"
                    ])
                if "rash" in symptoms_lower or "itching" in symptoms_lower:
                    remedies.extend([
                        "Keep affected area clean and dry",
                        "Avoid scratching",
                        "Use gentle, fragrance-free soap",
                        "Wear loose, cotton clothing",
                        "Apply cool compresses"
                    ])
                if "nausea" in symptoms_lower or "vomiting" in symptoms_lower:
                    remedies.extend([
                        "Stay hydrated with small sips",
                        "Eat bland foods",
                        "Avoid strong smells",
                        "Rest",
                        "Try ginger tea"
                    ])
                if "diarrhea" in symptoms_lower:
                    remedies.extend([
                        "Stay hydrated with oral rehydration solutions",
                        "Follow BRAT diet",
                        "Avoid dairy and fatty foods",
                        "Rest",
                        "Practice good hand hygiene"
                    ])
                if "constipation" in symptoms_lower:
                    remedies.extend([
                        "Increase fiber intake",
                        "Stay hydrated",
                        "Exercise regularly",
                        "Establish regular bathroom routine",
                        "Avoid processed foods"
                    ])
            
            # Remove duplicates and limit to 5 remedies
            remedies = list(dict.fromkeys(remedies))[:5]
            
            return remedies

        # --- ADDED: Update remedies list based on symptoms and remedies ---
        if response_dict.get("can_provide_structured_response") and response_dict.get("is_medical_related"):
            symptoms = response_dict.get("Symptoms", "")
            remedies = response_dict.get("Remedies", "")
            
            # Get disease-specific remedies
            specific_remedies = get_disease_specific_remedies(symptoms, remedies)
            
            # Update the remedies list in the response
            response_dict["Remedies"] = "\n".join(specific_remedies)

        # --- UPDATED: Function to get disease-specific medications ---
        def get_disease_specific_medications(symptoms_text, remedies_text):
            """Extract disease-specific medications based on symptoms and remedies."""
            # Convert text to lowercase for matching
            symptoms_lower = symptoms_text.lower()
            remedies_lower = remedies_text.lower()
            
            # Initialize empty list for medications
            medications = []
            
            # First, try to identify specific diseases
            for disease, meds in disease_medication_map.items():
                # If disease is mentioned in symptoms or remedies
                if disease in symptoms_lower or disease in remedies_lower:
                    # Add medications for this disease
                    medications.extend(meds)
                    # If we found a specific disease, return its medications
                    return list(dict.fromkeys(medications))[:3]
            
            # If no specific disease was found, try to match based on symptoms
            # Common symptom patterns with specific medications
            if "fever" in symptoms_lower or "chills" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen"])
            if "cough" in symptoms_lower:
                if "dry cough" in symptoms_lower:
                    medications.extend(["Cough suppressants"])
                elif "wet cough" in symptoms_lower or "phlegm" in symptoms_lower:
                    medications.extend(["Expectorants"])
                else:
                    medications.extend(["Cough suppressants", "Expectorants"])
            if "sore throat" in symptoms_lower:
                medications.extend(["Throat lozenges", "Salt water gargle"])
            if "headache" in symptoms_lower:
                if "migraine" in symptoms_lower:
                    medications.extend(["Acetaminophen", "Ibuprofen", "Aspirin"])
                else:
                    medications.extend(["Acetaminophen", "Ibuprofen"])
            if "pain" in symptoms_lower:
                if "joint pain" in symptoms_lower or "muscle pain" in symptoms_lower:
                    medications.extend(["Acetaminophen", "Ibuprofen", "Topical analgesics"])
                elif "back pain" in symptoms_lower:
                    medications.extend(["Acetaminophen", "Ibuprofen", "Topical analgesics"])
                else:
                    medications.extend(["Acetaminophen", "Ibuprofen"])
            if "rash" in symptoms_lower or "itching" in symptoms_lower:
                medications.extend(["Antihistamine cream", "Hydrocortisone cream"])
            if "nausea" in symptoms_lower or "vomiting" in symptoms_lower:
                medications.extend(["Ginger supplements", "Antacids"])
            if "diarrhea" in symptoms_lower:
                medications.extend(["Loperamide", "Bismuth subsalicylate"])
            if "constipation" in symptoms_lower:
                medications.extend(["Fiber supplements", "Stool softeners"])
            if "acid reflux" in symptoms_lower or "heartburn" in symptoms_lower:
                medications.extend(["Antacids", "H2 blockers"])
            if "allergies" in symptoms_lower or "allergic" in symptoms_lower:
                medications.extend(["Antihistamines", "Nasal corticosteroids"])
            if "sinus" in symptoms_lower or "congestion" in symptoms_lower:
                medications.extend(["Decongestants", "Nasal corticosteroids"])
            if "bronchitis" in symptoms_lower:
                medications.extend(["Cough suppressants", "Expectorants"])
            if "pneumonia" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen"])
            if "asthma" in symptoms_lower:
                medications.extend(["Bronchodilators"])  # Note: Usually prescription
            if "dermatitis" in symptoms_lower or "eczema" in symptoms_lower:
                medications.extend(["Antihistamine cream", "Hydrocortisone cream"])
            if "psoriasis" in symptoms_lower:
                medications.extend(["Coal tar", "Salicylic acid"])
            if "acne" in symptoms_lower:
                medications.extend(["Benzoyl peroxide", "Salicylic acid"])
            if "sunburn" in symptoms_lower:
                medications.extend(["Aloe vera", "Topical analgesics"])
            if "burns" in symptoms_lower:
                medications.extend(["Aloe vera", "Topical analgesics"])
            if "cuts" in symptoms_lower:
                medications.extend(["Antibiotic ointment", "Antiseptic"])
            if "bruises" in symptoms_lower:
                medications.extend(["Arnica", "Topical analgesics"])
            if "sprains" in symptoms_lower or "strains" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen", "Topical analgesics"])
            if "arthritis" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen", "Topical analgesics"])
            if "gout" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen"])
            if "uti" in symptoms_lower:
                medications.extend(["Cranberry supplements", "Pain relievers"])
            if "kidney stones" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen"])
            if "gallstones" in symptoms_lower:
                medications.extend(["Acetaminophen", "Ibuprofen"])
            if "ulcer" in symptoms_lower or "gastritis" in symptoms_lower:
                medications.extend(["Antacids", "H2 blockers"])
            if "colitis" in symptoms_lower:
                medications.extend(["Antidiarrheals", "Antispasmodics"])
            if "food poisoning" in symptoms_lower:
                medications.extend(["Antidiarrheals", "Antiemetics"])
            if "dehydration" in symptoms_lower:
                medications.extend(["Oral rehydration salts"])
            
            # Remove duplicates and limit to 3 medications
            medications = list(dict.fromkeys(medications))[:3]
            
            return medications

        return response_dict

    except Exception as e:
        logging.error(f"Error in gemini_interactive: {e}", exc_info=True) # Log the full traceback
        # Return a generic error message in the expected format
        return {
            "response": "I apologize, I encountered a technical difficulty. Could you please select an option below?",
            "needs_follow_up": True, # Encourage user to re-engage
            "follow_up_question": "What would you like to do?",
            "follow_up_type": "select",
            "follow_up_options": ["Try asking again", "Start a new conversation"],
            "rate_symptoms": False,
            "symptoms_to_rate": [],
            "is_medical_related": True, # Assume medical context for error
            "is_medical_related_prompt": "Yes",
            "can_provide_structured_response": False,
            "conversation_complete": False,
            "current_step": 0,
            "total_steps": 0,
            "Symptoms": ".",
            "Remedies": "",
            "Precautions": "",
            "Guidelines": "",
            "medication": [],
            "Disclaimer": STANDARD_DISCLAIMER,
            "image_search_term": ""
        }


# Example Usage (Optional)
if __name__ == "__main__":
    print("--- Testing gemini_text ---")
    # Test 1: Initial Symptom
    response1 = gemini_text("I have a bad headache.")
    print("Initial Symptom Query:\n", json.dumps(response1, indent=2))

    # Test 2: General Medical
    response2 = gemini_text("What are the common cold symptoms?")
    print("\nGeneral Medical Query:\n", json.dumps(response2, indent=2))

    # Test 3: Non-Medical
    response3 = gemini_text("What's the weather like today?")
    print("\nNon-Medical Query:\n", json.dumps(response3, indent=2))


    print("\n--- Testing gemini_generic ---")
     # Test 4: Medical Classification
    response4 = gemini_generic("Tell me about asthma precautions.")
    print("Medical Classification Query:\n", json.dumps(response4, indent=2))

    # Test 5: Non-Medical Classification
    response5 = gemini_generic("Who won the game last night?")
    print("\nNon-Medical Classification Query:\n", json.dumps(response5, indent=2))


    print("\n--- Testing gemini_interactive ---")
    # Test 6: Interactive - First Turn (Symptom)
    print("\nInteractive Turn 1 (User: 'I feel sick')")
    convo_history = []
    response6 = gemini_interactive("I feel sick", convo_history)
    print(json.dumps(response6, indent=2))
    if response6.get('response'):
         convo_history.append({"role": "user", "parts": ["I feel sick"]})
         convo_history.append({"role": "model", "parts": [response6['response']]}) # Add AI response to history

    # Test 7: Interactive - Second Turn (Follow-up Answer)
    print("\nInteractive Turn 2 (User: 'I have a fever and cough, started yesterday')")
    # Assume response6 asked for details
    response7 = gemini_interactive("I have a fever and cough, started yesterday", convo_history)
    print(json.dumps(response7, indent=2))
    if response7.get('response'):
         convo_history.append({"role": "user", "parts": ["I have a fever and cough, started yesterday"]})
         convo_history.append({"role": "model", "parts": [response7['response']]})

    # Test 8: Interactive - Non-Medical
    print("\nInteractive Turn (Non-Medical)")
    response8 = gemini_interactive("Can you tell me a joke?", [])
    print(json.dumps(response8, indent=2))

    # Test 9: Image Search (uses sample data if keys missing)
    print("\n--- Testing search_images ---")
    images = search_images("skin rash types", 2)
    print("Image Search Results:\n", json.dumps(images, indent=2))

    # Test 10: Download Images (uses sample data if keys missing, careful with actual downloads)
    # print("\n--- Testing download_and_save_images ---")
    # saved = download_and_save_images("flu symptoms illustration", num_results=1)
    # print("Saved Image Info:\n", json.dumps(saved, indent=2))
