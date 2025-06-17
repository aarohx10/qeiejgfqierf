import logging
from typing import Dict, List, Optional, Any
import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Security, Response, Query, Path
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, validator

# Import shared clients and config
import config
from src.supabase_client import SupabaseClient
from src.signalwire_provisioning import SignalWireClient
from src.services.redis_client import RedisClient
from src.services.signalwire_service import SignalWireService
from src.middleware.auth_middleware import get_current_user

logger = logging.getLogger(__name__)

# --- Dependency Injection for Clients ---
# These functions provide singleton instances of our clients for FastAPI's Dependency Injection system
def get_supabase_client() -> SupabaseClient:
    # Assumes client is initialized globally in ai_orchestrator.py's startup event
    # This is a placeholder, actual implementation might retrieve from app.state or a global variable
    if not hasattr(get_supabase_client, "_instance") or get_supabase_client._instance is None:
        get_supabase_client._instance = SupabaseClient()
    return get_supabase_client._instance

def get_signalwire_client() -> SignalWireClient:
    # Assumes client is initialized globally in ai_orchestrator.py's startup event
    if not hasattr(get_signalwire_client, "_instance") or get_signalwire_client._instance is None:
        get_signalwire_client._instance = SignalWireClient()
    return get_signalwire_client._instance

# --- API Key Security ---
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(x_api_key: str = Security(api_key_header)) -> str:
    """Dependency to validate the incoming API key against the configured management key."""
    if x_api_key == config.MANAGEMENT_API_KEY:
        return x_api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key. Access denied."
    )

# --- Pydantic Models (Based on your provided Database Schema) ---

# Base Response Model
class APIResponse(BaseModel):
    message: str = "Success"
    data: Optional[Any] = None

# AI Agents Models
class AIAgentBase(BaseModel):
    name: str = Field(..., description="Name of the AI agent")
    description: Optional[str] = Field(None, description="Description of the AI agent")
    voice_id: str = Field(..., description="ElevenLabs voice ID")
    initial_greeting: str = Field(..., description="Initial greeting message")
    system_prompt: str = Field(..., description="System prompt for the AI")
    temperature: float = Field(0.7, description="Temperature for AI responses")
    max_tokens: int = Field(1000, description="Maximum tokens for AI responses")
    enabled: bool = Field(True, description="Whether the agent is enabled")

class AIAgentCreate(AIAgentBase):
    pass

class AIAgentUpdate(AIAgentBase):
    name: Optional[str] = None
    voice_id: Optional[str] = None
    initial_greeting: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    enabled: Optional[bool] = None

class AIAgent(AIAgentBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Phone Numbers Models
class PhoneNumberCreate(BaseModel):
    user_id: str
    provider: str = "SignalWire"
    number: str = Field(..., description="Phone number in E.164 format (e.g., +15551234567).")
    country_code: str
    is_toll_free: bool = False
    is_active: bool = True
    ai_agent_id: str = Field(..., description="ID of the AI agent this number is linked to for inbound calls.")
    # Other optional fields from schema
    is_verified_external: Optional[bool] = False
    verification_status: Optional[str] = None
    verification_date: Optional[datetime.datetime] = None
    monthly_cost: Optional[float] = None
    capabilities: Optional[Dict] = Field(default_factory=dict)
    metadata: Optional[Dict] = Field(default_factory=dict)

class PhoneNumberUpdate(BaseModel):
    is_active: Optional[bool] = None
    ai_agent_id: Optional[str] = None
    metadata: Optional[Dict] = None
    # Add other updatable fields as needed

class PhoneNumberResponse(PhoneNumberCreate):
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        orm_mode = True

# SIP Trunks Models
class SIPTrunkCreate(BaseModel):
    user_id: str
    name: str
    provider: str = "SignalWire"
    credentials: Dict = Field(..., description="SIP trunk credentials (e.g., username, password, host).")
    status: str = "active"
    is_byoc: bool = True
    max_concurrent_calls: Optional[int] = None
    failover_trunk_id: Optional[str] = None
    health_check_url: Optional[str] = None
    # Add other fields as per schema

class SIPTrunkResponse(SIPTrunkCreate):
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        orm_mode = True

# Call Records Models
class CallRecordResponse(BaseModel):
    id: str
    call_provider: str
    provider_call_id: str
    ai_agent_id: str
    from_number: str
    to_number: str
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime] = None
    duration_seconds: Optional[int] = None
    status: str
    call_cost: Optional[float] = None
    stream_cost: Optional[float] = None
    total_cost: Optional[float] = None
    transcript: Optional[str] = None
    recording_url: Optional[str] = None
    recording_duration: Optional[int] = None
    recording_size_bytes: Optional[int] = None
    amd_result: Optional[Dict] = None
    sentiment_analysis: Optional[Dict] = None
    metadata: Optional[Dict] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    call_settings: Optional[Dict] = None
    voice_settings: Optional[Dict] = None
    model_settings: Optional[Dict] = None
    custom_variables: Optional[Dict] = None

    class Config:
        orm_mode = True

class CallSegmentResponse(BaseModel):
    id: str
    call_id: str
    sequence_number: int
    speaker: str
    text_content: str
    audio_duration_ms: Optional[int] = None
    timestamp: datetime.datetime
    llm_tokens_used: Optional[int] = None
    tts_characters_used: Optional[int] = None
    asr_audio_seconds: Optional[int] = None
    sentiment_score: Optional[float] = None
    confidence_score: Optional[float] = None
    tool_calls: Optional[List[Dict]] = None
    tool_results: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None

    class Config:
        orm_mode = True

class CallFilter(BaseModel):
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    agent_id: Optional[str] = None
    phone_number: Optional[str] = None

# --- API Router ---
router = APIRouter(prefix="/manage", tags=["Management API"])

# --- API Endpoints ---

# 1. AI Agent Management
@router.post("/agents", response_model=AIAgent)
async def create_agent(
    agent: AIAgentCreate,
    supabase: SupabaseClient = Depends(get_current_user)
):
    """Create a new AI agent."""
    try:
        agent_data = await supabase.create_ai_agent(agent.dict())
        return agent_data
    except Exception as e:
        logger.error(f"Failed to create AI agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/agents", response_model=List[AIAgent])
async def list_agents(
    enabled: Optional[bool] = None,
    supabase: SupabaseClient = Depends(get_current_user)
):
    """List all AI agents."""
    try:
        agents = await supabase.list_ai_agents(enabled=enabled)
        return agents
    except Exception as e:
        logger.error(f"Failed to list AI agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/agents/{agent_id}", response_model=AIAgent)
async def get_agent(
    agent_id: str = Path(..., description="ID of the AI agent"),
    supabase: SupabaseClient = Depends(get_current_user)
):
    """Get AI agent details."""
    try:
        agent = await supabase.get_ai_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get AI agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/agents/{agent_id}", response_model=AIAgent)
async def update_agent(
    agent: AIAgentUpdate,
    agent_id: str = Path(..., description="ID of the AI agent"),
    supabase: SupabaseClient = Depends(get_current_user)
):
    """Update AI agent details."""
    try:
        agent_data = await supabase.update_ai_agent(agent_id, agent.dict(exclude_unset=True))
        if not agent_data:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update AI agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str = Path(..., description="ID of the AI agent"),
    supabase: SupabaseClient = Depends(get_current_user)
):
    """Delete an AI agent."""
    try:
        success = await supabase.delete_ai_agent(agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"status": "success", "message": f"Agent {agent_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete AI agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# 2. Phone Number Management
@router.post("/phone_numbers", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
async def create_phone_number_endpoint(
    number_data: PhoneNumberCreate,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client),
    signalwire: SignalWireClient = Depends(get_signalwire_client)
):
    """
    Creates/provisions a new phone number and links it to an AI agent.
    Does NOT actually provision via SignalWire in this endpoint (handled by separate process).
    """
    if not await supabase.get_ai_agent(number_data.ai_agent_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Linked AI Agent not found.")

    created_number = await supabase.create_phone_number(number_data.dict())
    logger.info(f"Phone number created: {created_number.get('id')} - {created_number.get('number')}")
    return created_number

@router.get("/phone_numbers/{number_id}", response_model=PhoneNumberResponse)
async def get_phone_number_endpoint(
    number_id: str,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client)
):
    """Retrieves a specific phone number by ID."""
    number = await supabase.get_phone_number(number_id, by_column='id')
    if not number:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found.")
    return number

@router.patch("/phone_numbers/{number_id}", response_model=PhoneNumberResponse)
async def update_phone_number_endpoint(
    number_id: str,
    updates: PhoneNumberUpdate,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client)
):
    """Updates an existing phone number's details."""
    updated_number = await supabase.update_phone_number(number_id, updates.dict(exclude_unset=True))
    if not updated_number:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found or no changes applied.")
    logger.info(f"Phone number updated: {updated_number.get('id')}")
    return updated_number

@router.delete("/phone_numbers/{number_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phone_number_endpoint(
    number_id: str,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client)
):
    """Deletes a phone number."""
    success = await supabase.delete_phone_number(number_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found.")
    logger.info(f"Phone number deleted: {number_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# 3. SIP Trunk Management
@router.post("/sip_trunks", response_model=SIPTrunkResponse, status_code=status.HTTP_201_CREATED)
async def create_sip_trunk_endpoint(
    trunk_data: SIPTrunkCreate,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client),
    signalwire: SignalWireClient = Depends(get_signalwire_client)
):
    """Creates a new SIP trunk record."""
    created_trunk = await supabase.create_sip_trunk(trunk_data.dict())
    logger.info(f"SIP Trunk created: {created_trunk.get('id')} - {created_trunk.get('name')}")
    return created_trunk

@router.get("/sip_trunks/{trunk_id}", response_model=SIPTrunkResponse)
async def get_sip_trunk_endpoint(
    trunk_id: str,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client)
):
    """Retrieves a specific SIP trunk by ID."""
    trunk = await supabase.get_sip_trunk(trunk_id)
    if not trunk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SIP Trunk not found.")
    return trunk

# 4. Call Data Access
@router.get("/calls/{call_id}", response_model=CallRecordResponse)
async def get_call_record_endpoint(
    call_id: str,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client)
):
    """Retrieves a specific call record by ID."""
    call_record = await supabase.get_call_record(call_id)
    if not call_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call record not found.")
    return call_record

@router.get("/calls/{call_id}/segments", response_model=List[CallSegmentResponse])
async def get_call_segments_endpoint(
    call_id: str,
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client)
):
    """Retrieves all call segments for a given call ID."""
    segments = await supabase.get_call_segments(call_id)
    if not segments:
        # Return empty list if no segments found, not 404 for call itself
        return [] 
    return segments

@router.get("/calls", response_model=List[CallRecordResponse])
async def list_calls_endpoint(
    api_key: str = Depends(get_api_key),
    supabase: SupabaseClient = Depends(get_supabase_client),
    limit: int = 10,
    offset: int = 0,
    status_filter: Optional[str] = None,
    ai_agent_id_filter: Optional[str] = None,
    from_number_filter: Optional[str] = None,
    to_number_filter: Optional[str] = None,
    order_by: str = 'created_at',
    order_direction: str = 'desc'
):
    """
    Lists recent call records with optional filtering and pagination.
    
    Args:
        limit: Maximum number of records to return
        offset: Number of records to skip
        status_filter: Filter by call status
        ai_agent_id_filter: Filter by AI agent ID
        from_number_filter: Filter by from number
        to_number_filter: Filter by to number
        order_by: Field to order by
        order_direction: Order direction ('asc' or 'desc')
    """
    try:
        calls = await supabase.list_calls(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            ai_agent_id_filter=ai_agent_id_filter,
            from_number_filter=from_number_filter,
            to_number_filter=to_number_filter,
            order_by=order_by,
            order_direction=order_direction
        )
        return calls
    except Exception as e:
        logger.error(f"Error listing calls in API endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list calls: {e}"
        )

@router.post("/calls")
async def create_call(
    to_number: str = Query(..., description="Destination phone number"),
    agent_id: str = Query(..., description="ID of the AI agent to use"),
    from_number: Optional[str] = Query(None, description="Source phone number"),
    signalwire: SignalWireService = Depends(get_current_user)
):
    """Create a new outbound call."""
    try:
        call = await signalwire.make_call(
            to_number=to_number,
            agent_id=agent_id,
            from_number=from_number
        )
        return call
    except Exception as e:
        logger.error(f"Failed to create call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls", response_model=List[Dict[str, Any]])
async def list_calls(
    filter: CallFilter = Depends(),
    limit: int = Query(20, description="Maximum number of calls to return"),
    signalwire: SignalWireService = Depends(get_current_user)
):
    """List calls with optional filters."""
    try:
        calls = await signalwire.list_calls(
            status=filter.status,
            start_time=filter.start_time.isoformat() if filter.start_time else None,
            end_time=filter.end_time.isoformat() if filter.end_time else None,
            limit=limit
        )
        return calls
    except Exception as e:
        logger.error(f"Failed to list calls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/calls/{call_id}", response_model=Dict[str, Any])
async def get_call(
    call_id: str = Path(..., description="ID of the call"),
    signalwire: SignalWireService = Depends(get_current_user),
    redis: RedisClient = Depends(get_current_user)
):
    """Get call details including transcript and metadata."""
    try:
        # Get call data from SignalWire
        call_data = await signalwire.get_call(call_id)
        
        # Get call data from Redis
        redis_data = await redis.get_call_data(call_id)
        
        # Get transcript
        transcript = await redis.get_full_transcript(call_id)
        
        return {
            **call_data,
            "transcript": transcript,
            "redis_data": redis_data
        }
    except Exception as e:
        logger.error(f"Failed to get call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calls/{call_id}/end")
async def end_call(
    call_id: str = Path(..., description="ID of the call"),
    signalwire: SignalWireService = Depends(get_current_user),
    redis: RedisClient = Depends(get_current_user)
):
    """End an active call."""
    try:
        # End call in SignalWire
        await signalwire.end_call(call_id)
        
        # Clear call data from Redis
        await redis.clear_call_cache(call_id)
        
        return {"status": "success", "message": f"Call {call_id} ended"}
    except Exception as e:
        logger.error(f"Failed to end call {call_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# System Configuration Endpoints
@router.get("/config")
async def get_system_config(
    redis: RedisClient = Depends(get_current_user)
):
    """Get system configuration."""
    try:
        config = await redis.get_system_config()
        return config
    except Exception as e:
        logger.error(f"Failed to get system configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/config")
async def update_system_config(
    config: Dict[str, Any],
    redis: RedisClient = Depends(get_current_user)
):
    """Update system configuration."""
    try:
        await redis.set_system_config(config)
        return {"status": "success", "message": "System configuration updated"}
    except Exception as e:
        logger.error(f"Failed to update system configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Health Check Endpoints
@router.get("/health/agents")
async def check_agents_health(
    supabase: SupabaseClient = Depends(get_current_user)
):
    """Check health of AI agents."""
    try:
        agents = await supabase.list_ai_agents()
        return {
            "status": "healthy",
            "agent_count": len(agents),
            "agents": agents
        }
    except Exception as e:
        logger.error(f"Failed to check agents health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health/calls")
async def check_calls_health(
    signalwire: SignalWireService = Depends(get_current_user)
):
    """Check health of active calls."""
    try:
        active_calls = await signalwire.list_calls(status="in-progress")
        return {
            "status": "healthy",
            "active_calls": len(active_calls),
            "calls": active_calls
        }
    except Exception as e:
        logger.error(f"Failed to check calls health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Metrics Endpoints
@router.get("/metrics/calls")
async def get_call_metrics(
    start_time: datetime = Query(..., description="Start time for metrics"),
    end_time: datetime = Query(..., description="End time for metrics"),
    signalwire: SignalWireService = Depends(get_current_user)
):
    """Get call metrics for a time period."""
    try:
        calls = await signalwire.list_calls(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        
        # Calculate metrics
        total_calls = len(calls)
        completed_calls = len([c for c in calls if c["status"] == "completed"])
        failed_calls = len([c for c in calls if c["status"] == "failed"])
        total_duration = sum(c.get("duration", 0) for c in calls)
        
        return {
            "total_calls": total_calls,
            "completed_calls": completed_calls,
            "failed_calls": failed_calls,
            "success_rate": (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            "total_duration": total_duration,
            "average_duration": total_duration / total_calls if total_calls > 0 else 0
        }
    except Exception as e:
        logger.error(f"Failed to get call metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/agents")
async def get_agent_metrics(
    start_time: datetime = Query(..., description="Start time for metrics"),
    end_time: datetime = Query(..., description="End time for metrics"),
    supabase: SupabaseClient = Depends(get_current_user)
):
    """Get agent metrics for a time period."""
    try:
        agents = await supabase.list_ai_agents()
        calls = await supabase.list_calls(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        
        # Calculate metrics per agent
        agent_metrics = {}
        for agent in agents:
            agent_calls = [c for c in calls if c["agent_id"] == agent["id"]]
            total_calls = len(agent_calls)
            completed_calls = len([c for c in agent_calls if c["status"] == "completed"])
            
            agent_metrics[agent["id"]] = {
                "agent_name": agent["name"],
                "total_calls": total_calls,
                "completed_calls": completed_calls,
                "success_rate": (completed_calls / total_calls * 100) if total_calls > 0 else 0,
                "total_duration": sum(c.get("duration", 0) for c in agent_calls),
                "average_duration": sum(c.get("duration", 0) for c in agent_calls) / total_calls if total_calls > 0 else 0
            }
        
        return agent_metrics
    except Exception as e:
        logger.error(f"Failed to get agent metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 