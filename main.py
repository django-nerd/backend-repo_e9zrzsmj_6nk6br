import os
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from schemas import ContactSubmission

# --- Basic logging setup ---
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("backend")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / "app.log")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

app = FastAPI(title="Furry Verein Backend")

# --- CORS configuration ---
# We keep Starlette's CORSMiddleware, but also add a hardening middleware to ensure
# Access-Control-Allow-* headers are always present even behind proxies (e.g. Vercel).

def parse_allowed_origins() -> List[str]:
    # Allow list via env (comma-separated). Falls back to explicit frontend or wildcard.
    env_val = os.getenv("ALLOW_ORIGINS", "").strip()
    if env_val:
        return [o.strip() for o in env_val.split(",") if o.strip()]
    # Fallbacks
    frontend_env = os.getenv("FRONTEND_ORIGIN")
    if frontend_env:
        return [frontend_env]
    # Last resort: open CORS (no credentials)
    return ["*"]

ALLOWED_ORIGINS = parse_allowed_origins()
ALLOW_CREDENTIALS = False  # keep false to legally allow "*"
ALLOW_METHODS = ["*"]
ALLOW_HEADERS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=ALLOW_METHODS,
    allow_headers=ALLOW_HEADERS,
)

# Hardening middleware: always attach CORS headers on responses.
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = "*" in ALLOWED_ORIGINS or (origin in ALLOWED_ORIGINS if origin else False)

    # Handle preflight early
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*" if "*" in ALLOWED_ORIGINS else (origin or ALLOWED_ORIGINS[0]),
            "Access-Control-Allow-Methods": ", ".join(["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
            "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", ", ".join(ALLOW_HEADERS)),
            "Access-Control-Max-Age": "86400",
            "Vary": "Origin",
        }
        return Response(status_code=204, headers=headers)

    response = await call_next(request)

    # Attach headers on all responses (including errors)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = "*" if "*" in ALLOWED_ORIGINS else origin
    else:
        # If we have a fixed allow list and no origin matched, still expose the first allowed
        # to avoid missing header in some edge deployments (non-browser requests will ignore it).
        response.headers["Access-Control-Allow-Origin"] = "*" if "*" in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0]

    response.headers["Access-Control-Allow-Methods"] = ", ".join(["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    response.headers["Access-Control-Allow-Headers"] = ", ".join(ALLOW_HEADERS) if isinstance(ALLOW_HEADERS, list) else str(ALLOW_HEADERS)
    response.headers["Vary"] = "Origin"
    return response


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


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


# Contact submission endpoint with honeypot and rate limit (no persistence)
@app.post("/api/contact")
async def submit_contact(payload: ContactSubmission, request: Request):
    """Receive contact messages and perform spam/rate checks only.
    No database persistence and no server-side email.
    """
    # Honeypot: if filled, pretend success but do nothing
    if payload.hp and payload.hp.strip():
        logger.info("Honeypot triggered. Skipping any processing.")
        return {"ok": True}

    # Rate limit per IP
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        logger.info("Rate limited IP: %s", client_ip)
        # Return 200 with a rate-limited hint to keep UX simple
        return {"ok": False, "reason": "rate_limited"}

    # All good: acknowledge only
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
