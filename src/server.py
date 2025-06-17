import asyncio
import json
import logging
import structlog
import websockets
from typing import Optional, Dict, Any
from websockets.server import WebSocketServerProtocol

from src.core_ai_pipeline import CoreAIPipeline
from src.config import DEFAULT_INITIAL_GREETING

logger = structlog.get_logger(__name__)

class WebSocketServer:
    """WebSocket server for browser-based voice calls."""

    def __init__(
        self,
        core_ai_pipeline: CoreAIPipeline,
        host: str = "localhost",
        port: int = 8765
    ):
        """Initialize WebSocket server."""
        self.core_ai_pipeline = core_ai_pipeline
        self.host = host
        self.port = port
        logger.info(f"WebSocket server initialized on {host}:{port}")

    async def start(self):
        """Start the WebSocket server."""
        try:
            async with websockets.serve(
                self.handle_websocket,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=20
            ):
                logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
                await asyncio.Future()  # Run forever
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}", exc_info=True)
            raise

    async def handle_websocket(self, websocket: WebSocketServerProtocol, path: str):
        """
        Handle incoming WebSocket connections.
        
        Args:
            websocket: WebSocket connection
            path: Request path (expected format: /ws/{call_id})
        """
        try:
            # Extract call_id from path
            call_id = path.split('/')[-1]
            if not call_id:
                logger.error("No call_id provided in WebSocket path")
                await websocket.close(1008, "No call_id provided")
                return

            logger.info(f"New WebSocket connection for call {call_id}")

            # Get agent configuration
            agent_config = await self.core_ai_pipeline.redis_client.get_call_data(call_id, 'agent_config')
            if not agent_config:
                logger.error(f"No agent configuration found for call {call_id}")
                await websocket.close(1008, "No agent configuration found")
                return

            # Send initial greeting
            await self._send_initial_greeting(call_id, websocket, agent_config)

            # Process audio stream
            await self._process_audio_stream(call_id, websocket, agent_config)

        except websockets.exceptions.ConnectionClosedOK:
            logger.info(f"WebSocket connection closed normally for call {call_id}")
        except Exception as e:
            logger.error(f"Error handling WebSocket connection for call {call_id}: {e}", exc_info=True)
            try:
                await websocket.close(1011, "Internal server error")
            except:
                pass
        finally:
            # Clean up resources
            await self.core_ai_pipeline.redis_client.clear_call_cache(call_id)

    async def _send_initial_greeting(self, call_id: str, websocket: WebSocketServerProtocol, agent_config: Dict[str, Any]):
        """Send initial greeting to the client."""
        try:
            # Get greeting text from agent config or use default
            greeting_text = agent_config.get('initial_greeting', DEFAULT_INITIAL_GREETING)

            # Set AI speaking state
            await self.core_ai_pipeline.redis_client.set_call_data(call_id, 'is_ai_speaking', True)

            # Get TTS stream
            tts_stream = self.core_ai_pipeline.elevenlabs_service.synthesize_speech_stream(
                greeting_text,
                voice_id=agent_config.get('voice_id'),
                voice_settings=agent_config.get('voice_settings')
            )

            # Stream greeting
            async for chunk in tts_stream:
                if websocket.closed:
                    break
                await websocket.send(chunk)

            # Reset AI speaking state
            await self.core_ai_pipeline.redis_client.set_call_data(call_id, 'is_ai_speaking', False)
            logger.info(f"Sent initial greeting for call {call_id}")

        except Exception as e:
            logger.error(f"Error sending initial greeting for call {call_id}: {e}", exc_info=True)
            await self.core_ai_pipeline.redis_client.set_call_data(call_id, 'is_ai_speaking', False)
            raise

    async def _process_audio_stream(self, call_id: str, websocket: WebSocketServerProtocol, agent_config: Dict[str, Any]):
        """Process audio stream from client."""
        try:
            async def audio_stream():
                """Yield audio chunks from WebSocket messages."""
                try:
                    async for message in websocket:
                        if isinstance(message, bytes):
                            yield message
                        elif isinstance(message, str):
                            # Handle control messages
                            try:
                                msg_dict = json.loads(message)
                                if msg_dict.get('type') == 'event' and msg_dict.get('event') == 'disconnect':
                                    break
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON message from client: {message[:50]}...")
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"Client WebSocket closed for call {call_id}")
                finally:
                    logger.info(f"Audio stream ended for call {call_id}")

            # Process audio stream through core AI pipeline
            await self.core_ai_pipeline.process_audio_stream(
                audio_stream=audio_stream(),
                call_id=call_id,
                websocket=websocket,
                ai_agent_config=agent_config
            )

        except Exception as e:
            logger.error(f"Error processing audio stream for call {call_id}: {e}", exc_info=True)
            raise 