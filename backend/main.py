from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Import routers
from routers import videos, sessions, websocket, static
from services.cleanup_service import cleanup_service

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    asyncio.create_task(cleanup_service.start_periodic_cleanup(interval_minutes=30))
    print("✅ Background tasks started")
    yield
    # Shutdown (if needed)
    print("👋 Shutting down...")

app = FastAPI(title="Automaton API", version="1.0.0", lifespan=lifespan)

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(videos.router)
app.include_router(sessions.router)
app.include_router(websocket.router)
app.include_router(static.router)

@app.get("/")
async def root():
    return {"message": "Automaton API", "status": "running"}

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",  # Import string instead of app object
        host="0.0.0.0", 
        port=8000,
        reload=True,
        reload_includes=["*.py"],  # Only reload on Python file changes
        reload_excludes=["uploads/**", "sessions/**", "screenshots/**", "*.log", "*.jsonl", "*.json"]
    )
