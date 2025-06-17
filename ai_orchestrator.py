import asyncio
import json
import logging
import structlog
import uuid
import base64
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
from fastapi import FastAPI, WebSocket, HTTPException, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry

from src.services.supabase_client import SupabaseClient
from src.services.redis_client import RedisClient
from src.services.signalwire_service import SignalWireService
from src.services.gemini_service import GeminiService
from src.services.elevenlabs_service import ElevenLabsService
from src.services.deepgram_service import DeepgramService
from src.config import (
    SUPABASE_URL, SUPABASE_KEY, REDIS_URL, REDIS_PASSWORD,
    SIGNALWIRE_PROJECT_ID, SIGNALWIRE_TOKEN, SIGNALWIRE_SPACE_URL,
    GEMINI_API_KEY, ELEVENLABS_API_KEY, DEEPGRAM_API_KEY
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AI Call Center Orchestrator",
    description="Orchestrates AI-powered call center operations",
    version="1.0.0"
)

# --- Prometheus Metrics ---
registry = CollectorRegistry()

# Counters for total events
CALLS_TOTAL = Counter('sendora_calls_total', 'Total number of calls initiated/received', 
                     ['call_provider', 'direction', 'status'], registry=registry)
API_REQUESTS_TOTAL = Counter('sendora_api_requests_total', 'Total API requests to external services', 
                           ['service', 'endpoint', 'status'], registry=registry)
TTS_CHARACTERS_TOTAL = Counter('sendora_tts_characters_total', 'Total characters synthesized by TTS', 
                             ['voice_id'], registry=registry)
LLM_TOKENS_TOTAL = Counter('sendora_llm_tokens_total', 'Total LLM tokens used', 
                         ['model_name', 'token_type'], registry=registry)
BARGE_INS_TOTAL = Counter('sendora_barge_ins_total', 'Total number of barge-ins detected', 
                         registry=registry)

# Histograms for latency/duration
CALL_DURATION_SECONDS = Histogram('sendora_call_duration_seconds', 'Call duration in seconds', 
                                registry=registry)
API_LATENCY_SECONDS = Histogram('sendora_api_latency_seconds', 'Latency of external API calls in seconds', 
                              ['service', 'endpoint'], registry=registry)

# Gauges for current state
ACTIVE_CALLS_GAUGE = Gauge('sendora_active_calls', 'Current number of active calls', 
                          registry=registry)

# Global service instances
supabase_client_instance: Optional[SupabaseClient] = None
redis_client_instance: Optional[RedisClient] = None
signalwire_client_instance: Optional[SignalWireService] = None
gemini_service_instance: Optional[GeminiService] = None
elevenlabs_service_instance: Optional[ElevenLabsService] = None
deepgram_service_instance: Optional[DeepgramService] = None

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global supabase_client_instance, redis_client_instance, signalwire_client_instance
    global gemini_service_instance, elevenlabs_service_instance, deepgram_service_instance
    
    try:
        # Initialize service instances
        supabase_client_instance = SupabaseClient()
        redis_client_instance = RedisClient()
        signalwire_client_instance = SignalWireService(
            project_id=SIGNALWIRE_PROJECT_ID,
            token=SIGNALWIRE_TOKEN,
            space_url=SIGNALWIRE_SPACE_URL
        )
        gemini_service_instance = GeminiService(api_key=GEMINI_API_KEY)
        elevenlabs_service_instance = ElevenLabsService(api_key=ELEVENLABS_API_KEY)
        deepgram_service_instance = DeepgramService(api_key=DEEPGRAM_API_KEY)
        
        # Connect to services
        await redis_client_instance._connect()
        await signalwire_client_instance.connect()
        await gemini_service_instance.connect()
        await elevenlabs_service_instance.connect()
        await deepgram_service_instance.connect()
        
        # Set initial health check status
        await redis_client_instance.set_health_check("redis", "healthy")
        await redis_client_instance.set_health_check("signalwire", "healthy")
        await redis_client_instance.set_health_check("gemini", "healthy")
        await redis_client_instance.set_health_check("elevenlabs", "healthy")
        await redis_client_instance.set_health_check("deepgram", "healthy")
        
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup services on shutdown."""
    try:
        # Disconnect from services
        await redis_client_instance.disconnect()
        await signalwire_client_instance.disconnect()
        await gemini_service_instance.disconnect()
        await elevenlabs_service_instance.disconnect()
        await deepgram_service_instance.disconnect()
        
        logger.info("All services disconnected successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

@app.get("/metrics")
async def metrics():
    """Exposes Prometheus metrics."""
    return Response(content=generate_latest(registry).decode('utf-8'), 
                   media_type="text/plain; version=0.0.4; charset=utf-8")

async def _handle_signalwire_media_stream(ws: WebSocket, call_id: str, msg: Dict[str, Any]):
    """Handle media stream from SignalWire."""
    try:
        # Increment active calls gauge
        ACTIVE_CALLS_GAUGE.inc()
        CALLS_TOTAL.labels(call_provider='signalwire', direction='inbound', status='started').inc()
        
        # Get call data and agent config
        call_data = await redis_client_instance.get_call_data(call_id)
        if not call_data:
            raise HTTPException(status_code=404, detail="Call not found")
            
        agent_config = await redis_client_instance.get_agent_config(call_data["agent_id"])
        if not agent_config:
            raise HTTPException(status_code=404, detail="Agent configuration not found")
            
        # Initialize TTS task tracking
        current_tts_task: Optional[asyncio.Task] = None
        
        # Create audio chunk producer
        async def audio_chunk_producer() -> AsyncGenerator[bytes, None]:
            while True:
                try:
                    data = await ws.receive_text()
                    msg = json.loads(data)
                    if msg.get("event") == "media":
                        audio_data = base64.b64decode(msg["media"]["payload"])
                        yield audio_data
                except Exception as e:
                    logger.error(f"Error in audio chunk producer: {e}", exc_info=True)
                    break
        
        # Process audio stream
        deepgram_stream_generator = deepgram_service_instance.process_audio_stream(audio_chunk_producer())
        
        async for dg_result in deepgram_stream_generator:
            # Handle barge-in
            if dg_result.get("event") == "speech_started":
                logger.debug(f"Deepgram: Speech started for call {call_id}")
                is_ai_speaking = await redis_client_instance.get_call_data(call_id, 'is_ai_speaking') or False
                if is_ai_speaking and current_tts_task and not current_tts_task.done():
                    logger.info(f"Barge-in detected by Deepgram for call {call_id}. Cancelling AI TTS task.")
                    current_tts_task.cancel()
                    BARGE_INS_TOTAL.inc()
            
            # Handle transcription
            if dg_result.get("is_final"):
                transcript = dg_result.get("transcript", "")
                if transcript:
                    # Append to transcript
                    await redis_client_instance.append_transcript_segment(call_id, {
                        "text": transcript,
                        "timestamp": datetime.utcnow().isoformat(),
                        "speaker": "user"
                    })
                    
                    # Get AI response
                    start_time = datetime.utcnow()
                    response = await gemini_service_instance.generate_response(
                        prompt=transcript,
                        context=await redis_client_instance.get_conversation_memory(call_id)
                    )
                    latency = (datetime.utcnow() - start_time).total_seconds()
                    API_LATENCY_SECONDS.labels(service='gemini', endpoint='generate_response').observe(latency)
                    
                    if response:
                        # Update conversation memory
                        await redis_client_instance.set_conversation_memory(call_id, {
                            "last_user_input": transcript,
                            "last_ai_response": response,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        # Synthesize and stream response
                        await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', True)
                        
                        async def _tts_playback_coroutine():
                            nonlocal current_tts_task
                            try:
                                tts_stream = elevenlabs_service_instance.synthesize_speech_stream(
                                    response,
                                    agent_config.get('voice_id'),
                                    agent_config.get('voice_settings')
                                )
                                
                                async for tts_chunk in tts_stream:
                                    if ws.closed:
                                        logger.warning(f"WebSocket closed for call {call_id} during TTS streaming.")
                                        break
                                    await ws.send(json.dumps({
                                        "event": "media",
                                        "stream_sid": msg.get("stream_sid"),
                                        "media": {
                                            "payload": base64.b64encode(tts_chunk).decode('utf-8')
                                        }
                                    }))
                                    await ws.send(json.dumps({
                                        "event": "mark",
                                        "stream_sid": msg.get("stream_sid"),
                                        "name": f"tts-chunk-{uuid.uuid4()}"
                                    }))
                                
                                TTS_CHARACTERS_TOTAL.labels(voice_id=agent_config.get('voice_id')).inc(len(response))
                                logger.info(f"TTS playback completed for call {call_id}.")
                            except asyncio.CancelledError:
                                logger.info(f"TTS playback for call {call_id} was cancelled (barge-in).")
                            except Exception as e:
                                logger.error(f"Error during TTS playback for call {call_id}: {e}", exc_info=True)
                            finally:
                                await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', False)
                                current_tts_task = None
                        
                        current_tts_task = asyncio.create_task(_tts_playback_coroutine())
                        
                        # Append AI response to transcript
                        await redis_client_instance.append_transcript_segment(call_id, {
                            "text": response,
                            "timestamp": datetime.utcnow().isoformat(),
                            "speaker": "ai"
                        })
            
            # Handle errors
            elif dg_result.get("event") == "error":
                logger.error(f"Deepgram error received for call {call_id}: {dg_result.get('message')}. Sending fallback.")
                fallback_text = "I'm having trouble with my audio connection. Can you try speaking clearly again?"
                await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', True)
                fallback_tts_stream = elevenlabs_service_instance.synthesize_speech_stream(
                    fallback_text,
                    agent_config.get('voice_id'),
                    agent_config.get('voice_settings')
                )
                async for fallback_chunk in fallback_tts_stream:
                    if ws.closed:
                        break
                    await ws.send(json.dumps({
                        "event": "media",
                        "stream_sid": msg.get("stream_sid"),
                        "media": {"payload": base64.b64encode(fallback_chunk).decode('utf-8')}
                    }))
                await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', False)
                continue
    
    except Exception as e:
        logger.error(f"Error in media stream handler: {e}", exc_info=True)
        raise
    finally:
        # Cleanup
        if current_tts_task and not current_tts_task.done():
            current_tts_task.cancel()
        await redis_client_instance.clear_call_cache(call_id)
        ACTIVE_CALLS_GAUGE.dec()
        CALLS_TOTAL.labels(call_provider='signalwire', direction='inbound', status='completed').inc()
        CALL_DURATION_SECONDS.observe((datetime.utcnow() - datetime.fromisoformat(call_data["start_time"])).total_seconds())
        logger.info(f"Call {call_id} cleanup completed")

@app.websocket("/ws/{call_id}")
async def signalwire_webhook_handler(websocket: WebSocket, call_id: str):
    """Handle SignalWire WebSocket connections."""
    try:
        await websocket.accept()
        logger.info(f"WebSocket connection established for call {call_id}")
        
        # Track webhook receipt
        CALLS_TOTAL.labels(call_provider='signalwire', direction='inbound', status='webhook_received').inc()
        
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)
                
                if msg.get("event") == "media":
                    await _handle_signalwire_media_stream(websocket, call_id, msg)
                
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}", exc_info=True)
                break
                
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
    finally:
        await websocket.close()

@app.post("/calls/outbound")
async def trigger_outbound_call(
    to_number: str,
    agent_id: str,
    from_number: Optional[str] = None
):
    """Trigger an outbound call."""
    try:
        # Track outbound call initiation
        CALLS_TOTAL.labels(call_provider='signalwire', direction='outbound', status='initiated').inc()
        
        # Create call record
        call_data = {
            "agent_id": agent_id,
            "to_number": to_number,
            "from_number": from_number,
            "direction": "outbound",
            "status": "initiated",
            "start_time": datetime.utcnow().isoformat()
        }
        
        call_record = await supabase_client_instance.create_call_record(call_data)
        
        # Initiate call
        await signalwire_client_instance.initiate_call(
            to_number=to_number,
            from_number=from_number,
            call_id=call_record["id"]
        )
        
        return {"status": "success", "call_id": call_record["id"]}
        
    except Exception as e:
        logger.error(f"Error triggering outbound call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 