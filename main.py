import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Westside-Furs – Minimal Backend (not used by contact form)")

# Open CORS so the frontend can call health endpoints if ever needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "message": "Backend running, but not required for the contact form."}

@app.get("/test")
def test():
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
