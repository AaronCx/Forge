import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

from app.routers import agents, runs, api_keys
from app.services.rate_limiter import limiter
from app.services.templates import seed_templates
from app.database import supabase as supabase_client

load_dotenv()

app = FastAPI(
    title="AgentForge API",
    description="AI workflow agent platform backend",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(api_keys.router, prefix="/api")


@app.on_event("startup")
async def startup():
    try:
        await seed_templates(supabase_client)
    except Exception:
        pass  # Templates will be seeded on next startup if DB isn't ready


@app.get("/")
async def root():
    return {"name": "AgentForge API", "version": "1.0.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok"}
