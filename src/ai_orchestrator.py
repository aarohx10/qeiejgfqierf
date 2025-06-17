import asyncio
import json
import logging
import uuid
import base64
import datetime
from typing import Dict, Optional, Any, List, AsyncGenerator, Set

import websockets
from fastapi import FastAPI, Request, Response, HTTPException, status, WebSocket, WebSocketDisconnect
import uvicorn # For running the app directly
from fastapi.middleware.cors import CORSMiddleware

# Import shared utilities and services
import config
from src.supabase_client import SupabaseClient
from src.redis_client import RedisClient
from src.signalwire_provisioning import SignalWireClient
from src.services.gemini_service import GeminiService
from src.services.elevenlabs_service import ElevenLabsService
from src.services.deepgram_service import DeepgramService

# Import existing ASR/VAD from the base repo (ensure correct paths)
from src.asr.asr_factory import ASRFactory
from src.vad.vad_factory import VADFactory
from src.audio_utils import save_audio_to_file # For debugging if needed

# Import Management API Router
from api.management_api import router as management_router

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format=config.LOG_FORMAT)

# Set httpx logging level lower to avoid verbosity
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

app = FastAPI(
    title="Sendora AI Voice Telephony Backend",
    description="Handles real-time phone calls via SignalWire, orchestrates AI, and provides management APIs.",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Clients Initialization (Singleton Pattern) ---
# These will be initialized once when the app starts
supabase_client_instance: Optional[SupabaseClient] = None
redis_client_instance: Optional[RedisClient] = None
signalwire_client_instance: Optional[SignalWireClient] = None
gemini_service_instance: Optional[GeminiService] = None
elevenlabs_service_instance: Optional[ElevenLabsService] = None
deepgram_service_instance: Optional[DeepgramService] = None

# Include Management API Router
app.include_router(management_router)

class AIOrchestrator:
    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient,
        signalwire_client: SignalWireClient,
        gemini_service: GeminiService,
        elevenlabs_service: ElevenLabsService,
        deepgram_service: DeepgramService
    ):
        self.supabase_client = supabase_client
        self.redis_client = redis_client
        self.signalwire_client = signalwire_client
        self.gemini_service = gemini_service
        self.elevenlabs_service = elevenlabs_service
        self.deepgram_service = deepgram_service
        self._shutdown_event = asyncio.Event()
        self._active_tasks: Set[asyncio.Task] = set()

    async def close(self):
        """Clean up resources and cancel active tasks."""
        self._shutdown_event.set()
        for task in self._active_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._active_tasks, return_exceptions=True)
        self._active_tasks.clear()

    def _create_task(self, coro):
        """Create and track a new task."""
        if self._shutdown_event.is_set():
            raise RuntimeError("Cannot create new tasks during shutdown")
        task = asyncio.create_task(coro)
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return task

    async def _handle_signalwire_media_stream(self, websocket: WebSocketClientProtocol, call_id: str):
        """
        Manages the real-time audio stream with SignalWire for a specific call.
        Orchestrates STT, LLM, TTS, and data logging.
        """
        logger.info("starting_media_stream", call_id=call_id)

        audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        is_ai_speaking: bool = False
        tts_task: Optional[asyncio.Task] = None

        try:
            # 1. Retrieve AI Agent Config and Conversation Memory
            agent_config = await self.redis_client.get_call_data(call_id, 'agent_config')
            if not agent_config:
                logger.error("no_agent_config", call_id=call_id)
                await websocket.close()
                return

            conversation_memory = await self.redis_client.get_call_data(call_id, 'conversation_memory') or []

            # 2. Initialize Deepgram Live Transcription
            async def audio_generator():
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break
                    yield chunk

            deepgram_stream = self.deepgram_service.connect_streaming_api(
                audio_generator(),
                language=agent_config.get('language', 'en'),
                model=agent_config.get('asr_model', 'nova-2'),
                punctuate=agent_config.get('punctuate', True),
                diarize=agent_config.get('diarize', False),
                vad_turnoff=agent_config.get('vad_turnoff_ms', 700)
            )

            # 3. Send initial greeting
            initial_greeting = agent_config.get('initial_greeting', config.DEFAULT_INITIAL_GREETING)
            await self._send_tts_response(websocket, initial_greeting, agent_config)

            # 4. Main processing loop
            while True:
                try:
                    # Receive message from SignalWire
                    message = await websocket.recv()
                    if isinstance(message, str):
                        msg = json.loads(message)
                        msg_type = msg.get("event")

                        if msg_type == "media":
                            payload = msg.get("media", {}).get("payload")
                            if payload:
                                audio_chunk = base64.b64decode(payload)
                                await audio_queue.put(audio_chunk)
                        elif msg_type == "stop":
                            logger.info("stream_stopped", call_id=call_id)
                            break
                        elif msg_type == "error":
                            logger.error("stream_error", call_id=call_id, error=msg.get("error"))
                            break

                    # Process Deepgram results
                    try:
                        async for dg_result in deepgram_stream:
                            if dg_result.get("event") == "speech_started":
                                is_ai_speaking = await self.redis_client.get_call_data(call_id, 'is_ai_speaking') or False
                                if is_ai_speaking and tts_task and not tts_task.done():
                                    tts_task.cancel()
                                    logger.info("barge_in_detected", call_id=call_id)
                                    await self.redis_client.set_call_data(call_id, 'is_ai_speaking', False)
                                    break

                            if dg_result.get("is_final", False):
                                transcript = dg_result.get("transcript", "").strip()
                                if transcript:
                                    # Log user message
                                    await self._log_user_message(call_id, transcript, dg_result.get('duration', 0))

                                    # Get AI response
                                    ai_response = await self._get_ai_response(
                                        call_id,
                                        transcript,
                                        agent_config,
                                        conversation_memory
                                    )

                                    if ai_response:
                                        # Send TTS response
                                        await self._send_tts_response(websocket, ai_response, agent_config)

                                        # Log AI response
                                        await self._log_ai_message(call_id, ai_response)

                    except asyncio.TimeoutError:
                        continue

                except websockets.exceptions.ConnectionClosed:
                    logger.info("websocket_closed", call_id=call_id)
                    break
                except Exception as e:
                    logger.error("processing_error", call_id=call_id, error=str(e), exc_info=True)
                    break

        except Exception as e:
            logger.error("stream_handler_error", call_id=call_id, error=str(e), exc_info=True)
        finally:
            await audio_queue.put(None)  # Signal end of stream
            await self._cleanup_call(call_id)

    async def _get_ai_response(
        self,
        call_id: str,
        user_message: str,
        agent_config: Dict[str, Any],
        conversation_memory: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Get AI response using Gemini."""
        try:
            # Update conversation memory
            conversation_memory.append({"role": "user", "parts": [{"text": user_message}]})

            # Get chat session
            chat = await self.gemini_service.start_chat(
                system_prompt=agent_config.get('system_prompt', 'You are a helpful AI assistant.'),
                conversation_history=conversation_memory[:-1]
            )

            # Get response
            response = await self.gemini_service.send_message(
                chat,
                user_message,
                temperature=agent_config.get('temperature', 0.7)
            )

            if response and response.get('text'):
                ai_message = response['text'].strip()
                conversation_memory.append({"role": "model", "parts": [{"text": ai_message}]})
                await self.redis_client.set_call_data(call_id, 'conversation_memory', conversation_memory)
                return ai_message

        except Exception as e:
            logger.error("ai_response_error", call_id=call_id, error=str(e), exc_info=True)
        return None

    async def _send_tts_response(
        self,
        websocket: WebSocketClientProtocol,
        text: str,
        agent_config: Dict[str, Any]
    ):
        """Send TTS response through WebSocket."""
        try:
            await self.redis_client.set_call_data(websocket.id, 'is_ai_speaking', True)

            tts_stream = self.elevenlabs_service.synthesize_speech_stream(
                text,
                agent_config.get('voice_id'),
                agent_config.get('voice_settings')
            )

            async for chunk in tts_stream:
                if websocket.closed:
                    break
                await websocket.send(json.dumps({
                    "event": "media",
                    "stream_sid": websocket.id,
                    "media": {
                        "payload": base64.b64encode(chunk).decode('utf-8')
                    }
                }))

        except Exception as e:
            logger.error("tts_error", error=str(e), exc_info=True)
        finally:
            await self.redis_client.set_call_data(websocket.id, 'is_ai_speaking', False)

    async def _log_user_message(self, call_id: str, text: str, duration: float):
        """Log user message to Supabase."""
        try:
            await self.supabase_client.create_call_segment({
                "call_id": call_id,
                "speaker": "user",
                "text_content": text,
                "asr_audio_seconds": duration
            })
        except Exception as e:
            logger.error("log_user_message_error", call_id=call_id, error=str(e), exc_info=True)

    async def _log_ai_message(self, call_id: str, text: str):
        """Log AI message to Supabase."""
        try:
            await self.supabase_client.create_call_segment({
                "call_id": call_id,
                "speaker": "ai",
                "text_content": text
            })
        except Exception as e:
            logger.error("log_ai_message_error", call_id=call_id, error=str(e), exc_info=True)

    async def _cleanup_call(self, call_id: str):
        """Clean up call resources."""
        try:
            # Update call status in Supabase
            await self.supabase_client.update_call_record(call_id, {
                "status": "completed",
                "end_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })

            # Clear Redis cache
            await self.redis_client.clear_call_cache(call_id)

        except Exception as e:
            logger.error("cleanup_error", call_id=call_id, error=str(e), exc_info=True)

@app.on_event("startup")
async def startup_event():
    """Initializes global clients when the FastAPI application starts."""
    global supabase_client_instance, redis_client_instance, signalwire_client_instance, \
           gemini_service_instance, elevenlabs_service_instance, deepgram_service_instance
    try:
        supabase_client_instance = SupabaseClient()
        redis_client_instance = RedisClient()
        signalwire_client_instance = SignalWireClient()
        gemini_service_instance = GeminiService()
        elevenlabs_service_instance = ElevenLabsService()
        deepgram_service_instance = DeepgramService()
        
        # --- Set the instances for dependency injection in other modules ---
        # This makes sure the management_api can get the same instances
        from api.management_api import get_supabase_client, get_signalwire_client
        get_supabase_client._instance = supabase_client_instance
        get_signalwire_client._instance = signalwire_client_instance

        logger.info("All shared clients and AI services initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize core services: {e}", exc_info=True)
        raise # Critical failure, prevent app startup if services fail

@app.on_event("shutdown")
async def shutdown_event():
    """Cleans up resources when the FastAPI application shuts down."""
    logger.info("Shutting down AI Orchestrator. Performing cleanup...")
    # Add logic to gracefully close any open WebSocket connections if managing them globally
    if supabase_client_instance._client: # Access httpx client
        await supabase_client_instance._client.aclose()
    if signalwire_client_instance._client:
        await signalwire_client_instance._client.aclose()
    if redis_client_instance._redis_client:
        await redis_client_instance._redis_client.aclose()
    logger.info("Resources cleaned up.")

# --- API Endpoints ---

# 1. SignalWire Webhook Endpoint
@app.post("/signalwire-webhook")
async def signalwire_webhook_handler(request: Request):
    """
    Receives call events from SignalWire.
    For inbound calls, it's the primary entry point to connect the call to your AI.
    For outbound calls, it receives progress updates and media stream URLs.
    """
    try:
        payload = await request.json()
        call_id = payload.get("call_id")
        from_number = payload.get("from_number")
        to_number = payload.get("to_number")
        media_url = payload.get("media_url")
        state = payload.get("state")
        direction = payload.get("direction")
        
        logger.info(f"Received SignalWire webhook: Call {call_id} - State: {state}, Direction: {direction}")

        if state == "answered" and media_url:
            logger.info(f"Call {call_id} answered. Establishing media stream to {media_url}")

            # AI Agent Selection (Inbound Calls)
            ai_agent_id = None
            if direction == "inbound":
                # Look up to_number in phone_numbers table to get ai_agent_id
                phone_number_record = await supabase_client_instance.get_phone_number(to_number, by_column='number')
                if phone_number_record and phone_number_record.get('ai_agent_id'):
                    ai_agent_id = phone_number_record['ai_agent_id']
                else:
                    logger.warning(f"No AI agent linked to inbound number {to_number} for call {call_id}.")
                    # Handle case: play fallback message or hang up
                    return Response(status_code=200, content=json.dumps({"message": "No agent found"}), media_type="application/json")
            elif direction == "outbound" and payload.get("client_state"):
                try:
                    client_state = json.loads(payload["client_state"])
                    ai_agent_id = client_state.get("ai_agent_id")
                except json.JSONDecodeError:
                    logger.warning(f"Invalid client_state for outbound call {call_id}.")

            if not ai_agent_id:
                logger.error(f"Could not determine AI agent for call {call_id}. State: {state}, Direction: {direction}")
                return Response(status_code=200, content=json.dumps({"message": "Agent not determined"}), media_type="application/json")

            # Fetch AI Agent Configuration
            ai_agent_config = await supabase_client_instance.get_ai_agent(ai_agent_id)
            if not ai_agent_config or not ai_agent_config.get('is_active'):
                logger.error(f"AI Agent {ai_agent_id} not found or inactive for call {call_id}.")
                return Response(status_code=200, content=json.dumps({"message": "Agent not found or inactive"}), media_type="application/json")

            # Create/Update calls record in Supabase
            initial_call_data = {
                "id": call_id,
                "call_provider": "signalwire",
                "provider_call_id": call_id, # SignalWire call_id is our provider_call_id
                "ai_agent_id": ai_agent_config['id'],
                "from_number": from_number,
                "to_number": to_number,
                "start_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "status": "in-progress",
                "call_settings": ai_agent_config.get('call_settings', {}),
                "voice_settings": ai_agent_config.get('voice_settings', {}),
                "model_settings": ai_agent_config.get('model_settings', {}),
                "conversation_settings": ai_agent_config.get('conversation_settings', {}),
                "custom_variables": payload.get("custom_variables", {}) # Pass any custom variables
            }
            # Check if call already exists (e.g., for outbound answered event)
            existing_call = await supabase_client_instance.get_call_record(call_id)
            if not existing_call:
                await supabase_client_instance.create_call_record(initial_call_data)
                logger.info(f"Created new call record for {call_id} in Supabase.")
            else:
                await supabase_client_instance.update_call_record(call_id, {"status": "in-progress"})
                logger.info(f"Updated existing call record for {call_id} to in-progress.")
            
            # Initialize Redis state for the call
            await redis_client_instance.set_call_data(call_id, 'agent_config', ai_agent_config, expire_seconds=3600*24) # Keep agent config for longer
            await redis_client_instance.set_call_data(call_id, 'conversation_memory', [], expire_seconds=3600)
            await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', False, expire_seconds=3600)
            await redis_client_instance.set_call_data(call_id, 'current_status', 'answered', expire_seconds=3600)

            # Initiate outbound WebSocket connection to SignalWire media
            asyncio.create_task(
                _connect_and_handle_media(media_url, call_id, ai_agent_config)
            )

        elif state == "ended":
            logger.info(f"Call {call_id} ended webhook received.")
            # Update call status in Supabase (final update will be from _handle_signalwire_media_stream's finally block)
            await supabase_client_instance.update_call_record(call_id, {
                "status": "ended",
                "end_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            # No need to clear redis here, _handle_signalwire_media_stream will do it.
        
        return Response(status_code=200, media_type="application/json")

    except Exception as e:
        logger.error(f"Error handling SignalWire webhook: {e}", exc_info=True)
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def _connect_and_handle_media(media_url: str, call_id: str, ai_agent_config: Dict):
    """Helper to connect to SignalWire media WS and then handle the stream."""
    try:
        async with websockets.connect(media_url) as ws:
            logger.info(f"WebSocket connected to SignalWire media for call_id: {call_id}")
            # Send initial 'connect' message to SignalWire
            await ws.send(json.dumps({
                "event": "connect",
                "protocol": "websocket", # Or "websocket" depending on SignalWire setup
                "codec": {
                    "name": config.AUDIO_FORMAT,
                    "sample_rate": config.AUDIO_SAMPLE_RATE,
                    "channels": 1
                }
            }))
            # Send initial greeting
            initial_greeting_text = ai_agent_config.get('initial_greeting', config.DEFAULT_INITIAL_GREETING) # Assuming DEFAULT_INITIAL_GREETING in config
            tts_stream = elevenlabs_service_instance.synthesize_speech_stream(
                initial_greeting_text,
                ai_agent_config.get('voice_id'),
                ai_agent_config.get('voice_settings')
            )
            await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', True)
            async for chunk in tts_stream:
                if ws.closed:
                    logger.warning(f"WS closed during initial greeting for call {call_id}")
                    break
                await ws.send(json.dumps({
                    "event": "media",
                    "stream_sid": call_id, # Use call_id as stream_sid for simplicity
                    "media": {
                        "payload": base64.b64encode(chunk).decode('utf-8')
                    }
                }))
                await asyncio.sleep(0.05) # Small delay for real-time feel
            await redis_client_instance.set_call_data(call_id, 'is_ai_speaking', False)
            logger.info(f"Initial greeting sent for call {call_id}.")

            # Start the main media stream handler
            await _handle_signalwire_media_stream(ws, call_id)

    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"Media WebSocket for call {call_id} closed gracefully.")
    except Exception as e:
        logger.error(f"Error connecting/handling media for call {call_id}: {e}", exc_info=True)
        # Ensure call status is updated to error if connection fails before stream starts
        await supabase_client_instance.update_call_record(call_id, {"status": "failed", "end_time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        await redis_client_instance.clear_call_cache(call_id)

# 2. Trigger Outbound Call Endpoint
@app.post("/trigger-call")
async def trigger_outbound_call(request_data: Dict):
    """
    Allows an external system (e.g., Sendora) to programmatically initiate an outbound phone call.
    """
    from_number = request_data.get("from_number")
    to_number = request_data.get("to_number")
    ai_agent_id = request_data.get("ai_agent_id")
    custom_variables = request_data.get("custom_variables", {})

    if not all([from_number, to_number, ai_agent_id]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: from_number, to_number, ai_agent_id"
        )
    
    try:
        # Verify AI Agent exists and is active
        ai_agent_config = await supabase_client_instance.get_ai_agent(ai_agent_id)
        if not ai_agent_config or not ai_agent_config.get('is_active'):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI Agent with ID {ai_agent_id} not found or is inactive."
            )
        
        # Prepare client_state to pass agent_id through SignalWire
        client_state_payload = {"ai_agent_id": ai_agent_id}
        if custom_variables:
            client_state_payload["custom_variables"] = custom_variables

        # Initiate call via SignalWire provisioning client
        # SignalWire will send webhooks for call events (including media) to this app's /signalwire-webhook
        signalwire_response = await signalwire_client_instance.initiate_call(
            from_number=from_number,
            to_number=to_number,
            webhook_url=f"{config.SIGNALWIRE_WEBHOOK_URL_BASE}/signalwire-webhook",
            client_state=client_state_payload
        )

        call_id = signalwire_response.get("call_id") # SignalWire's call ID
        logger.info(f"Outbound call initiated from {from_number} to {to_number} with agent {ai_agent_id}. SignalWire Call ID: {call_id}")

        return {"call_id": call_id, "status": "initiated", "message": "Outbound call initiated successfully."}

    except HTTPException:
        raise # Re-raise explicit HTTPExceptions
    except Exception as e:
        logger.error(f"Error initiating outbound call: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initiate call: {e}")

# Health check endpoint
@app.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz():
    """Provides a simple health check to indicate the application is running."""
    logger.debug("Health check requested")
    return {"status": "ok", "service": "ai_orchestrator"}

# --- Uvicorn Server Runner ---
if __name__ == "__main__":
    # For local development/testing, run with Uvicorn
    # This assumes your AI Orchestrator will be accessible at config.SIGNALWIRE_WEBHOOK_URL_BASE
    # when SignalWire tries to send webhooks. You might need Ngrok for public exposure.
    uvicorn.run(app, host="0.0.0.0", port=8000) 