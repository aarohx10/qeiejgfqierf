import asyncio
import logging
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from datetime import datetime
import os

from src.services.supabase_client import SupabaseClient
from src.services.redis_client import RedisClient
from src.services.signalwire_service import SignalWireService
from src.services.gemini_service import GeminiService
from src.services.elevenlabs_service import ElevenLabsService
from src.services.deepgram_service import DeepgramService
from src.core_ai_pipeline import CoreAIPipeline
from src.config import (
    SUPABASE_URL, SUPABASE_KEY, REDIS_URL, REDIS_PASSWORD,
    SIGNALWIRE_PROJECT_ID, SIGNALWIRE_TOKEN, SIGNALWIRE_SPACE_URL,
    GEMINI_API_KEY, ELEVENLABS_API_KEY, DEEPGRAM_API_KEY
)
from src.api.management_api import router as management_router
from src.middleware.auth_middleware import get_current_user

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AI Call Center API",
    description="API for managing AI-powered call center operations",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
supabase = SupabaseClient()
redis = RedisClient()
signalwire = SignalWireService(
    project_id=os.getenv("SIGNALWIRE_PROJECT_ID"),
    token=os.getenv("SIGNALWIRE_TOKEN"),
    space_url=os.getenv("SIGNALWIRE_SPACE_URL")
)
gemini = GeminiService(
    api_key=os.getenv("GEMINI_API_KEY")
)
elevenlabs = ElevenLabsService(
    api_key=os.getenv("ELEVENLABS_API_KEY")
)
deepgram = DeepgramService(
    api_key=os.getenv("DEEPGRAM_API_KEY")
)

# Initialize core AI pipeline
core_ai_pipeline = CoreAIPipeline(
    supabase_client=supabase,
    redis_client=redis,
    gemini_service=gemini,
    elevenlabs_service=elevenlabs,
    deepgram_service=deepgram
)

# Include management API router
app.include_router(management_router)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    try:
        # Connect to services
        await redis._connect()
        await signalwire.connect()
        await gemini.connect()
        await elevenlabs.connect()
        await deepgram.connect()
        
        # Set initial health check status
        await redis.set_health_check("redis", "healthy")
        await redis.set_health_check("signalwire", "healthy")
        await redis.set_health_check("gemini", "healthy")
        await redis.set_health_check("elevenlabs", "healthy")
        await redis.set_health_check("deepgram", "healthy")
        
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup services on shutdown."""
    try:
        # Disconnect from services
        await redis.disconnect()
        await signalwire.disconnect()
        await gemini.disconnect()
        await elevenlabs.disconnect()
        await deepgram.disconnect()
        
        logger.info("All services disconnected successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

@app.get("/health")
async def health_check():
    """Check health of all services."""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "redis": await redis.get_health_check("redis"),
                "signalwire": await redis.get_health_check("signalwire"),
                "gemini": await redis.get_health_check("gemini"),
                "elevenlabs": await redis.get_health_check("elevenlabs"),
                "deepgram": await redis.get_health_check("deepgram")
            }
        }
        return health_status
    except Exception as e:
        logger.error(f"Error during health check: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/calls/{call_id}/end")
async def end_call(
    call_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """End a call."""
    try:
        # Update call status in database
        await supabase.update_call_record(call_id, {
            "status": "completed",
            "end_time": datetime.utcnow().isoformat()
        })
        
        # Clear call data from Redis
        await redis.clear_call_cache(call_id)
        
        return {"message": "Call ended successfully"}
    except Exception as e:
        logger.error(f"Error ending call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calls/{call_id}")
async def get_call(
    call_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get call details."""
    try:
        call = await supabase.get_call_record(call_id)
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        return call
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calls")
async def list_calls(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """List all calls."""
    try:
        calls = await supabase.list_records(
            "calls",
            filters={"user_id": f"eq.{current_user['id']}"},
            order_by="created_at.desc"
        )
        return calls
    except Exception as e:
        logger.error(f"Error listing calls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 