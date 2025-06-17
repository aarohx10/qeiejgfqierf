import asyncio
import json
import logging
import structlog
import base64
import uuid
import datetime
from typing import AsyncGenerator, Dict, List, Optional, Any

from src.supabase_client import SupabaseClient
from src.redis_client import RedisClient
from src.services.gemini_service import GeminiService
from src.services.elevenlabs_service import ElevenLabsService
from src.services.deepgram_service import DeepgramService

logger = structlog.get_logger(__name__)

class CoreAIPipeline:
    """Shared AI pipeline logic for both WebSocket and telephony backends."""
    
    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient,
        gemini_service: GeminiService,
        elevenlabs_service: ElevenLabsService,
        deepgram_service: DeepgramService
    ):
        """Initialize the core AI pipeline with required services."""
        self.supabase_client = supabase_client
        self.redis_client = redis_client
        self.gemini_service = gemini_service
        self.elevenlabs_service = elevenlabs_service
        self.deepgram_service = deepgram_service
        logger.info("CoreAIPipeline initialized")

    async def process_audio_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        call_id: str,
        websocket: Any,  # WebSocketServerProtocol or WebSocketClientProtocol
        stream_sid: Optional[str] = None,
        ai_agent_config: Optional[Dict[str, Any]] = None,
        conversation_memory: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Process an audio stream through the AI pipeline.
        
        Args:
            audio_stream: AsyncGenerator yielding audio chunks
            call_id: Unique identifier for the call
            websocket: WebSocket connection for sending responses
            stream_sid: Optional stream ID for telephony backend
            ai_agent_config: Optional agent configuration
            conversation_memory: Optional conversation history
        """
        try:
            # Initialize or retrieve conversation memory
            if conversation_memory is None:
                conversation_memory = await self.redis_client.get_call_data(call_id, 'conversation_memory') or []

            # Get agent config if not provided
            if ai_agent_config is None:
                ai_agent_config = await self.redis_client.get_call_data(call_id, 'agent_config')
                if not ai_agent_config:
                    raise ValueError(f"No agent config found for call {call_id}")

            # Initialize Deepgram streaming
            deepgram_stream = self.deepgram_service.connect_streaming_api(
                audio_stream,
                language=ai_agent_config.get('language', 'en'),
                model=ai_agent_config.get('asr_model', 'nova-2'),
                punctuate=ai_agent_config.get('punctuate', True),
                diarize=ai_agent_config.get('diarize', False),
                vad_turnoff=ai_agent_config.get('vad_turnoff_ms', 700)
            )

            # Process Deepgram results
            async for result in deepgram_stream:
                if result.get('event') == 'speech_started':
                    # Handle barge-in if AI is speaking
                    is_ai_speaking = await self.redis_client.is_ai_speaking(call_id)
                    if is_ai_speaking:
                        logger.info(f"Barge-in detected for call {call_id}")
                        # Cancel any ongoing TTS
                        await self.redis_client.set_call_data(call_id, 'is_ai_speaking', False)
                        continue

                if result.get('is_final', False):
                    user_transcript = result.get('transcript', '').strip()
                    if not user_transcript:
                        continue

                    # Log user message
                    await self._log_user_message(call_id, user_transcript, result.get('duration', 0))

                    # Generate AI response
                    ai_response = await self._generate_ai_response(
                        call_id,
                        user_transcript,
                        ai_agent_config,
                        conversation_memory
                    )

                    if ai_response:
                        # Stream TTS response
                        await self._stream_tts_response(
                            call_id,
                            ai_response,
                            ai_agent_config,
                            websocket,
                            stream_sid
                        )

        except Exception as e:
            logger.error(f"Error in AI pipeline for call {call_id}: {e}", exc_info=True)
            raise

    async def _log_user_message(self, call_id: str, transcript: str, duration: float) -> None:
        """Log a user message to Supabase and Redis."""
        try:
            # Log to Supabase
            await self.supabase_client.create_call_segment({
                "call_id": call_id,
                "sequence_number": await self._get_next_sequence(call_id),
                "speaker": "user",
                "text_content": transcript,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "asr_audio_seconds": duration
            })

            # Log to Redis transcript history
            await self.redis_client.append_transcript_segment(call_id, transcript)
            logger.info(f"Logged user message for call {call_id}: {transcript[:50]}...")
        except Exception as e:
            logger.error(f"Error logging user message for call {call_id}: {e}", exc_info=True)
            raise

    async def _generate_ai_response(
        self,
        call_id: str,
        user_message: str,
        ai_agent_config: Dict[str, Any],
        conversation_memory: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Generate an AI response using Gemini."""
        try:
            # Prepare conversation history
            system_prompt = ai_agent_config.get('system_prompt', 'You are a helpful AI assistant.')
            history = [{"role": "system", "parts": [{"text": system_prompt}]}]
            history.extend(conversation_memory)

            # Start chat session
            chat = await self.gemini_service.start_chat(
                system_prompt=system_prompt,
                conversation_history=conversation_memory[:-1]  # Exclude last user message
            )

            # Generate response
            response = await self.gemini_service.send_message(
                chat,
                user_message,
                temperature=ai_agent_config.get('model_settings', {}).get('temperature', 0.9)
            )

            if response.get('tool_calls'):
                logger.info(f"Tool calls proposed for call {call_id}: {response['tool_calls']}")
                return response.get('text', 'I am sorry, I cannot perform that action yet.')

            return response.get('text', '').strip()

        except Exception as e:
            logger.error(f"Error generating AI response for call {call_id}: {e}", exc_info=True)
            return None

    async def _stream_tts_response(
        self,
        call_id: str,
        text: str,
        ai_agent_config: Dict[str, Any],
        websocket: Any,
        stream_sid: Optional[str] = None
    ) -> None:
        """Stream TTS response back to client."""
        try:
            # Set AI speaking state
            await self.redis_client.set_call_data(call_id, 'is_ai_speaking', True)

            # Get TTS stream
            tts_stream = self.elevenlabs_service.synthesize_speech_stream(
                text,
                voice_id=ai_agent_config.get('voice_id'),
                voice_settings=ai_agent_config.get('voice_settings')
            )

            # Stream audio chunks
            async for chunk in tts_stream:
                if websocket.closed:
                    logger.warning(f"WebSocket closed for call {call_id} during TTS streaming")
                    break

                # Prepare media message
                media_message = {
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(chunk).decode('utf-8')
                    }
                }

                # Add stream_sid for telephony backend
                if stream_sid:
                    media_message["stream_sid"] = stream_sid

                # Send chunk
                await websocket.send(json.dumps(media_message))

                # Send mark for real-time feel
                await websocket.send(json.dumps({
                    "event": "mark",
                    "name": f"tts-chunk-{uuid.uuid4()}"
                }))

            # Log AI response
            await self._log_ai_message(call_id, text)

            # Reset AI speaking state
            await self.redis_client.set_call_data(call_id, 'is_ai_speaking', False)

        except Exception as e:
            logger.error(f"Error streaming TTS response for call {call_id}: {e}", exc_info=True)
            await self.redis_client.set_call_data(call_id, 'is_ai_speaking', False)
            raise

    async def _log_ai_message(self, call_id: str, text: str) -> None:
        """Log an AI message to Supabase and Redis."""
        try:
            # Log to Supabase
            await self.supabase_client.create_call_segment({
                "call_id": call_id,
                "sequence_number": await self._get_next_sequence(call_id),
                "speaker": "ai",
                "text_content": text,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })

            # Log to Redis transcript history
            await self.redis_client.append_transcript_segment(call_id, text)
            logger.info(f"Logged AI message for call {call_id}: {text[:50]}...")
        except Exception as e:
            logger.error(f"Error logging AI message for call {call_id}: {e}", exc_info=True)
            raise

    async def _get_next_sequence(self, call_id: str) -> int:
        """Get the next sequence number for a call segment."""
        try:
            segments = await self.supabase_client.list_records(
                'call_segments',
                filters={'call_id': f'eq.{call_id}'},
                order_by='sequence_number.desc',
                limit=1
            )
            return (segments[0]['sequence_number'] + 1) if segments else 1
        except Exception as e:
            logger.error(f"Error getting next sequence for call {call_id}: {e}", exc_info=True)
            return 1  # Default to 1 if error 