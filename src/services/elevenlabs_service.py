import logging
import structlog
import httpx
import json
from typing import Dict, Any, Optional, AsyncGenerator, BinaryIO
from io import BytesIO
import asyncio
import elevenlabs
from elevenlabs import generate, stream, set_api_key, Voice, VoiceSettings
from src.config import ELEVENLABS_API_KEY, AUDIO_SAMPLE_RATE, AUDIO_CHUNK_SIZE

logger = structlog.get_logger(__name__)

class ElevenLabsService:
    """Service for interacting with ElevenLabs API."""
    
    def __init__(self, api_key: str = ELEVENLABS_API_KEY):
        """Initialize ElevenLabs service."""
        self._api_key = api_key
        set_api_key(api_key)
        self._client: Optional[httpx.AsyncClient] = None
        logger.info("ElevenLabs service initialized")

    async def connect(self) -> None:
        """Connect to ElevenLabs API."""
        try:
            # Test connection by getting available voices
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": self._api_key}
                )
                response.raise_for_status()
            logger.info("Successfully connected to ElevenLabs")
        except Exception as e:
            logger.error(f"Error connecting to ElevenLabs: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from ElevenLabs API."""
        try:
            # No explicit disconnect needed for ElevenLabs
            logger.info("Successfully disconnected from ElevenLabs")
        except Exception as e:
            logger.error(f"Error disconnecting from ElevenLabs: {e}", exc_info=True)

    def _ensure_connection(self) -> None:
        """Ensure client is connected."""
        if not self._client:
            raise RuntimeError("ElevenLabs client not connected")

    async def get_voices(self) -> Dict[str, Any]:
        """Get available voices."""
        self._ensure_connection()
        try:
            response = await self._client.get("/voices")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get voices: {e}", exc_info=True)
            raise

    async def get_voice(self, voice_id: str) -> Dict[str, Any]:
        """Get voice details."""
        self._ensure_connection()
        try:
            response = await self._client.get(f"/voices/{voice_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get voice {voice_id}: {e}", exc_info=True)
            raise

    async def synthesize_speech(
        self,
        text: str,
        voice_id: str,
        model_id: str = "eleven_monolingual_v1",
        voice_settings: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """Synthesize speech from text."""
        self._ensure_connection()
        try:
            data = {
                "text": text,
                "model_id": model_id,
                "voice_settings": voice_settings or {}
            }
            
            response = await self._client.post(
                f"/text-to-speech/{voice_id}",
                json=data
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to synthesize speech: {e}", exc_info=True)
            raise

    async def synthesize_speech_stream(
        self,
        text: str,
        voice_id: str,
        voice_settings: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesize speech and stream audio chunks.
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID to use
            voice_settings: Optional voice settings
            
        Yields:
            Audio chunks as bytes
        """
        try:
            # Configure voice settings
            settings = VoiceSettings(**voice_settings) if voice_settings else VoiceSettings()
            voice = Voice(voice_id=voice_id, settings=settings)
            
            # Generate audio stream
            audio_stream = generate(
                text=text,
                voice=voice,
                model="eleven_monolingual_v1",
                stream=True
            )
            
            # Stream audio chunks
            async for chunk in audio_stream:
                yield chunk
                
        except Exception as e:
            logger.error(f"Error synthesizing speech with ElevenLabs for text: '{text[:50]}...' voice_id: {voice_id}: {e}", exc_info=True)
            # Yield a small silent audio chunk (e.g., 200ms of silence for 16kHz linear16 mono)
            # 16000 samples/sec * 2 bytes/sample * 0.2 sec = 6400 bytes of silence
            silent_chunk_size = int(AUDIO_SAMPLE_RATE * (AUDIO_CHUNK_SIZE / (16000 * 2)) * 2)
            yield b'\x00' * silent_chunk_size
            logger.warning("Yielded silent audio chunk due to ElevenLabs error.")

    async def get_models(self) -> Dict[str, Any]:
        """Get available models."""
        self._ensure_connection()
        try:
            response = await self._client.get("/models")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get models: {e}", exc_info=True)
            raise

    async def get_user_info(self) -> Dict[str, Any]:
        """Get user information."""
        self._ensure_connection()
        try:
            response = await self._client.get("/user")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get user info: {e}", exc_info=True)
            raise

    async def get_subscription_info(self) -> Dict[str, Any]:
        """Get subscription information."""
        self._ensure_connection()
        try:
            response = await self._client.get("/user/subscription")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get subscription info: {e}", exc_info=True)
            raise

    async def get_usage_info(self) -> Dict[str, Any]:
        """Get usage information."""
        self._ensure_connection()
        try:
            response = await self._client.get("/user/usage")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get usage info: {e}", exc_info=True)
            raise

    async def create_voice(
        self,
        name: str,
        description: str,
        files: list[BinaryIO],
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a new voice."""
        self._ensure_connection()
        try:
            files_data = []
            for file in files:
                files_data.append(("files", file))
            
            data = {
                "name": name,
                "description": description,
                "labels": json.dumps(labels) if labels else "{}"
            }
            
            response = await self._client.post(
                "/voices/add",
                data=data,
                files=files_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create voice: {e}", exc_info=True)
            raise

    async def delete_voice(self, voice_id: str) -> None:
        """Delete a voice."""
        self._ensure_connection()
        try:
            response = await self._client.delete(f"/voices/{voice_id}")
            response.raise_for_status()
            logger.info(f"Deleted voice: {voice_id}")
        except Exception as e:
            logger.error(f"Failed to delete voice {voice_id}: {e}", exc_info=True)
            raise

    async def edit_voice(
        self,
        voice_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Edit voice settings."""
        self._ensure_connection()
        try:
            data = {}
            if name is not None:
                data["name"] = name
            if description is not None:
                data["description"] = description
            if labels is not None:
                data["labels"] = json.dumps(labels)
            
            response = await self._client.post(
                f"/voices/{voice_id}/edit",
                json=data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to edit voice {voice_id}: {e}", exc_info=True)
            raise

    async def synthesize_speech_elevenlabs(
        self,
        text: str,
        voice_id: str,
        voice_settings: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """Synthesize speech from text using ElevenLabs API."""
        try:
            audio = generate(
                text=text,
                voice=voice_id,
                model="eleven_multilingual_v2",
                voice_settings=voice_settings or {}
            )
            return audio
        except Exception as e:
            logger.error(f"Failed to synthesize speech: {e}", exc_info=True)
            raise

    async def synthesize_speech_stream_elevenlabs(
        self,
        text: str,
        voice_id: str,
        voice_settings: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesized speech from text using ElevenLabs API."""
        try:
            audio_stream = stream(
                text=text,
                voice=voice_id,
                model="eleven_multilingual_v2",
                voice_settings=voice_settings or {}
            )
            async for chunk in audio_stream:
                yield chunk
        except Exception as e:
            logger.error(f"Failed to stream synthesized speech: {e}", exc_info=True)
            raise

    async def get_voices_elevenlabs(self) -> list:
        """Get available voices using ElevenLabs API."""
        try:
            voices = elevenlabs.voices()
            return [{
                "voice_id": voice.voice_id,
                "name": voice.name,
                "category": voice.category,
                "labels": voice.labels,
                "preview_url": voice.preview_url
            } for voice in voices]
        except Exception as e:
            logger.error(f"Failed to get voices: {e}", exc_info=True)
            raise

    async def get_voice_elevenlabs(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """Get details for a specific voice using ElevenLabs API."""
        try:
            voice = elevenlabs.Voice(voice_id=voice_id)
            return {
                "voice_id": voice.voice_id,
                "name": voice.name,
                "category": voice.category,
                "labels": voice.labels,
                "preview_url": voice.preview_url,
                "settings": voice.settings
            }
        except Exception as e:
            logger.error(f"Failed to get voice {voice_id}: {e}", exc_info=True)
            return None

    async def create_voice_elevenlabs(
        self,
        name: str,
        description: Optional[str] = None,
        files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new voice using ElevenLabs API."""
        try:
            voice = elevenlabs.Voice(name=name, description=description, files=files or [])
            return {
                "voice_id": voice.voice_id,
                "name": voice.name,
                "description": voice.description,
                "files": voice.files,
                "category": voice.category,
                "labels": voice.labels,
                "preview_url": voice.preview_url
            }
        except Exception as e:
            logger.error(f"Failed to create voice: {e}", exc_info=True)
            raise

    async def delete_voice_elevenlabs(self, voice_id: str) -> bool:
        """Delete a voice using ElevenLabs API."""
        try:
            elevenlabs.delete_voice(voice_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete voice: {e}", exc_info=True)
            return False 