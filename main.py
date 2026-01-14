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

# Quick links for common requests
QUICK_LINKS = {
    "membership": "https://aws-learning-club-uphsl.vercel.app/membership",
    "discord": "https://discord.com/invite/KFUVjh3Xqt",
    "facebook": "https://www.facebook.com/awslearningclub",
    "contact": "awslc.uphsl@gmail.com"
}

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
                    # Check for quick links
                    response_text = check_quick_links(user_text)
                    
                    if not response_text:
                        # Generate response from Gemini
                        system_prompt = f"""You are a friendly member of AWS Learning Club UPHSL. Be warm, conversational, and helpful.

Guidelines:
- Keep responses SHORT to MEDIUM length (2-4 sentences max)
- Be bilingual: mix Tagalog and English naturally (Taglish is perfect!)
- Sound like a friendly human, not a bot
- Use casual, warm tone with emojis occasionally 😊
- Never mention you're reading from a website or scraping data
- If unsure, admit it kindly and offer to help with something else
- NEVER use bold, italic, or markdown formatting (**, *, _, etc.) - Messenger shows them as plain text
- Write in plain text only

Club Information:
{website_content}

Answer questions about AWS Learning Club naturally as if you're a club member helping out!"""
                        
                        ai_response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=user_text,
                            config={"system_instruction": system_prompt}
                        )
                        response_text = ai_response.text
                    
                    await send_messenger_message(sender_id, response_text)
                    
    return {"status": "success"}

def check_quick_links(text: str) -> str:
    """Check if user is asking for specific links."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["membership", "member", "join", "sumali"]):
        return f"Sure! Here's our membership form 📝\n{QUICK_LINKS['membership']}"
    
    if any(word in text_lower for word in ["discord", "server", "chat"]):
        return f"Join our Discord community! 💬\n{QUICK_LINKS['discord']}"
    
    if any(word in text_lower for word in ["facebook", "fb", "page"]):
        return f"Follow us on Facebook! 👍\n{QUICK_LINKS['facebook']}"
    
    if any(word in text_lower for word in ["event", "events", "activities"]):
        return f"Check out our events here! 🎉\n{QUICK_LINKS['events']}"
    
    return None

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