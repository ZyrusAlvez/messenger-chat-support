import os
import httpx
from fastapi import FastAPI, Request, Query, HTTPException
from google import genai
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

app = FastAPI()

# Credentials
FB_PAGE_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Website knowledge base
website_content = ""

@app.on_event("startup")
async def load_website_content():
    global website_content
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get("https://aws-learning-club-uphsl.vercel.app/")
            soup = BeautifulSoup(response.text, "html.parser")
            website_content = soup.get_text(separator="\n", strip=True)
            print("Website content loaded successfully")
    except Exception as e:
        print(f"Failed to load website: {e}")

@app.get("/webhook")
async def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """Handles the initial Webhook verification from Meta."""
    if mode == "subscribe" and token == FB_VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def handle_messages(request: Request):
    """Processes incoming messages and sends responses."""
    data = await request.json()
    
    if data.get("object") == "page":
        for entry in data["entry"]:
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event["sender"]["id"]
                user_text = messaging_event.get("message", {}).get("text")
                
                if user_text:
                    # 1. Generate response from Gemini with website context
                    system_prompt = f"""you may use the following website information to answer questions:

{website_content}

Answer based on this information. If the question is not related to the website content, politely say you can only help with questions about the AWS Learning Club."""
                    
                    ai_response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=user_text,
                        config={"system_instruction": system_prompt}
                    )
                    
                    # 2. Send the response back to Messenger
                    await send_messenger_message(sender_id, ai_response.text)
                    
    return {"status": "success"}

async def send_messenger_message(recipient_id: str, text: str):
    """Sends a message back to the user via Facebook's Graph API."""
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={FB_PAGE_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    async with httpx.AsyncClient() as http_client:
        await http_client.post(url, json=payload)