from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Health API", version="1.0.0")

# Open CORS so the frontend can reach health routes in any environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "backend-minimal"}

@app.get("/test")
async def test():
    return {"message": "backend alive"}
