import os
import smtplib
from email.message import EmailMessage
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from schemas import Contact, ContactSubmission
from database import create_document, db

app = FastAPI(title="Furry Verein Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database and email env are available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
        "smtp": {
            "host": "❌ Not Set",
            "port": "",
            "user": "",
            "from": ""
        },
        "rate_limit": os.getenv("RATE_LIMIT_PER_MIN", "not set")
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check SMTP envs
    response["smtp"]["host"] = "✅ Set" if os.getenv("SMTP_HOST") else "❌ Not Set"
    response["smtp"]["port"] = os.getenv("SMTP_PORT") or ""
    response["smtp"]["user"] = "✅ Set" if os.getenv("SMTP_USER") else "❌ Not Set"
    response["smtp"]["from"] = os.getenv("EMAIL_FROM") or ""

    return response


def send_email_notification(contact: Contact):
    """Send an email notification via SMTP using environment variables.

    Required envs: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    if not all([host, port, user, password, email_from, email_to]):
        # Silently skip if email not configured; don't block contact storage
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Neue Kontaktanfrage: {contact.subject or 'Ohne Betreff'}"
    msg["From"] = email_from
    msg["To"] = email_to

    body = (
        f"Name: {contact.name}\n"
        f"E-Mail: {contact.email}\n"
        f"Betreff: {contact.subject or '-'}\n\n"
        f"Nachricht:\n{contact.message}\n"
    )
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


# Simple in-process rate limiting using env-based threshold
from time import time
from collections import defaultdict

RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
request_times = defaultdict(list)

def is_rate_limited(client_ip: str) -> bool:
    now = time()
    window_start = now - 60
    times = request_times[client_ip]
    # prune old
    request_times[client_ip] = [t for t in times if t >= window_start]
    if len(request_times[client_ip]) >= RATE_LIMIT_PER_MIN:
        return True
    request_times[client_ip].append(now)
    return False


# Contact submission endpoint with honeypot and rate limit
@app.post("/api/contact")
async def submit_contact(payload: ContactSubmission, request: Request):
    """Receive contact messages and store them in MongoDB.
    Includes spam protection: honeypot (hp) and simple per-IP rate limit.
    """
    # Honeypot: if filled, pretend success but do nothing
    if payload.hp and payload.hp.strip():
        return {"ok": True}

    # Rate limit per IP
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        # 429 might expose to UI; we return 200 but indicate throttling in body
        return {"ok": False, "reason": "rate_limited"}

    try:
        # Convert to Contact (drop honeypot)
        contact = Contact(**payload.model_dump(exclude={"hp"}))
        contact_id = create_document("contact", contact)

        # Fire-and-forget email notification
        send_email_notification(contact)

        return {"ok": True, "id": contact_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
