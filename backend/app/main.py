import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import supabase as supabase_client
from app.routers import (
    agents,
    api_keys,
    costs,
    dashboard,
    messages,
    orchestration,
    runs,
)
from app.services.rate_limiter import limiter
from app.services.templates import seed_templates

load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        await seed_templates(supabase_client)
    except Exception:
        logger.warning("Failed to seed templates — will retry on next startup", exc_info=True)
    yield


app = FastAPI(
    title="AgentForge API",
    description="AI workflow agent platform backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

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
app.include_router(dashboard.router, prefix="/api")
app.include_router(costs.router, prefix="/api")
app.include_router(orchestration.router, prefix="/api")
app.include_router(messages.router, prefix="/api")


@app.get("/")
async def root():
    return {"name": "AgentForge API", "version": "1.0.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok"}
