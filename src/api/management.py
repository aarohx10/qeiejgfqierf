from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import structlog

from src.services.signalwire_service import SignalWireService
from src.core_ai_pipeline import CoreAIPipeline
from src.config import SIGNALWIRE_WEBHOOK_URL_BASE, SIGNALWIRE_PROJECT_ID, SIGNALWIRE_TOKEN, SIGNALWIRE_SPACE_URL
from src.supabase_client import SupabaseClient
from src.redis_client import RedisClient
from src.middleware.auth import get_current_user

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/management", tags=["management"])

# Models
class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    voice_id: str = Field(..., min_length=1)
    initial_greeting: Optional[str] = Field(None, max_length=500)
    system_prompt: Optional[str] = Field(None, max_length=2000)

class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    voice_id: Optional[str] = Field(None, min_length=1)
    initial_greeting: Optional[str] = Field(None, max_length=500)
    system_prompt: Optional[str] = Field(None, max_length=2000)

class Agent(BaseModel):
    id: str
    name: str
    description: Optional[str]
    voice_id: str
    initial_greeting: Optional[str]
    system_prompt: Optional[str]
    created_at: datetime
    updated_at: datetime

class Call(BaseModel):
    id: str
    status: str
    direction: str
    from_number: str
    to_number: str
    agent_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration: Optional[int]
    recording_url: Optional[str]
    transcription_url: Optional[str]

# Dependency to get SignalWire service
async def get_signalwire_service():
    service = SignalWireService(
        project_id=SIGNALWIRE_PROJECT_ID,
        token=SIGNALWIRE_TOKEN,
        space_url=SIGNALWIRE_SPACE_URL
    )
    await service.initialize()
    try:
        yield service
    finally:
        await service.close()

# Dependency to get Supabase client
async def get_supabase_client():
    client = SupabaseClient()
    await client.initialize()
    try:
        yield client
    finally:
        await client.close()

# Dependency to get Redis client
async def get_redis_client():
    client = RedisClient()
    await client.initialize()
    try:
        yield client
    finally:
        await client.close()

# Dependency to get core AI pipeline
async def get_core_ai_pipeline() -> CoreAIPipeline:
    return CoreAIPipeline()

@router.post("/agents", response_model=Agent)
async def create_agent(
    agent: AgentCreate,
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """Create a new AI agent."""
    try:
        agent_data = agent.dict()
        agent_data["created_by"] = current_user["id"]
        created_agent = await supabase.create_agent(agent_data)
        return created_agent
    except Exception as e:
        logger.error(f"Failed to create agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/agents", response_model=List[Agent])
async def list_agents(
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """List all AI agents."""
    try:
        agents = await supabase.list_agents()
        return agents
    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(
    agent_id: str,
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """Get agent details."""
    try:
        agent = await supabase.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/agents/{agent_id}", response_model=Agent)
async def update_agent(
    agent_id: str,
    agent: AgentUpdate,
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """Update agent details."""
    try:
        updated_agent = await supabase.update_agent(agent_id, agent.dict(exclude_unset=True))
        if not updated_agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return updated_agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """Delete an agent."""
    try:
        success = await supabase.delete_agent(agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"message": "Agent deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls", response_model=List[Call])
async def list_calls(
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(20, ge=1, le=100),
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """List calls with optional filters."""
    try:
        # TODO: Implement call listing with filters
        raise HTTPException(status_code=501, detail="Not implemented")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls/{call_id}", response_model=Call)
async def get_call(
    call_id: str,
    signalwire: SignalWireService = Depends(get_signalwire_service),
    supabase: SupabaseClient = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """Get call details."""
    try:
        call = await signalwire.get_call(call_id)
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        return call
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calls/{call_id}/end")
async def end_call(
    call_id: str,
    signalwire: SignalWireService = Depends(get_signalwire_service),
    current_user: dict = Depends(get_current_user)
):
    """End an active call."""
    try:
        success = await signalwire.end_call(call_id)
        if not success:
            raise HTTPException(status_code=404, detail="Call not found")
        return {"message": "Call ended successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls/{call_id}/recordings")
async def get_call_recordings(
    call_id: str,
    signalwire: SignalWireService = Depends(get_signalwire_service),
    current_user: dict = Depends(get_current_user)
):
    """Get recordings for a call."""
    try:
        recordings = await signalwire.get_call_recordings(call_id)
        return recordings
    except Exception as e:
        logger.error(f"Failed to get recordings for call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls/{call_id}/transcriptions")
async def get_call_transcriptions(
    call_id: str,
    signalwire: SignalWireService = Depends(get_signalwire_service),
    current_user: dict = Depends(get_current_user)
):
    """Get transcriptions for a call."""
    try:
        transcriptions = await signalwire.get_call_transcriptions(call_id)
        return transcriptions
    except Exception as e:
        logger.error(f"Failed to get transcriptions for call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls/{call_id}/quality")
async def get_call_quality(
    call_id: str,
    signalwire: SignalWireService = Depends(get_signalwire_service),
    current_user: dict = Depends(get_current_user)
):
    """Get call quality metrics."""
    try:
        metrics = await signalwire.get_call_quality_metrics(call_id)
        if not metrics:
            raise HTTPException(status_code=404, detail="Call quality metrics not found")
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get call quality metrics for call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 