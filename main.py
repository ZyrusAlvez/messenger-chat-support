import os
import httpx
from fastapi import FastAPI, Request, Query, HTTPException
from groq import Groq
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

app = FastAPI()

# Credentials
FB_PAGE_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq Client
client = Groq(api_key=GROQ_API_KEY)

# Website knowledge base
website_content = ""
website_links = ""

# Conversation history per user (stores last 10 messages)
conversation_history = {}

@app.on_event("startup")
async def load_website_content():
    global website_content, website_links
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get("https://aws-learning-club-uphsl.vercel.app/")
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract text content
            website_content = soup.get_text(separator="\n", strip=True)
            
            # Extract all links
            links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                text = a_tag.get_text(strip=True)
                if href.startswith('http'):
                    links.append(f"{text}: {href}" if text else href)
            
            website_links = "\n".join(links) if links else "No links found"
            print("Website content and links loaded successfully")
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
                    # Get or create conversation history for this user
                    if sender_id not in conversation_history:
                        conversation_history[sender_id] = []
                    
                    # Build conversation context
                    history = conversation_history[sender_id]
                    
                    system_prompt = f"""You are a representative of AWS Learning Club UPHSL. Be friendly yet professional in your responses.

Guidelines:
- Keep responses SHORT to MEDIUM length (2-4 sentences max)
- Write primarily in English, with occasional Tagalog words or phrases for a natural Filipino touch
- Use Tagalog sparingly - only for common expressions like "po", "salamat", "welcome", or casual connectors
- Maintain a warm but professional tone
- Use emojis ONLY when extremely necessary (greetings, celebrations, or expressing gratitude)
- Never mention you're reading from a website or accessing external data
- If unsure about something, politely acknowledge it and offer alternative assistance
- NEVER use bold, italic, or markdown formatting (**, *, _, etc.) - Messenger shows them as plain text
- Write in plain text only
- Be helpful and informative while maintaining professionalism
- When users ask for links, provide relevant links from the available links below

Club Information:
{website_content}

Available Links:
{website_links}

Answer questions about AWS Learning Club naturally and professionally."""
                    
                    # Build messages with history
                    messages = [{"role": "system", "content": system_prompt}]
                    for i, msg in enumerate(history):
                        role = "user" if i % 2 == 0 else "assistant"
                        messages.append({"role": role, "content": msg})
                    messages.append({"role": "user", "content": user_text})
                    
                    ai_response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=300
                    )
                    response_text = ai_response.choices[0].message.content
                    
                    # Update conversation history (keep last 10 messages)
                    history.append(user_text)
                    history.append(response_text)
                    if len(history) > 20:  # 10 exchanges (user + bot)
                        history.pop(0)
                        history.pop(0)
                    
                    await send_messenger_message(sender_id, response_text)
                    
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