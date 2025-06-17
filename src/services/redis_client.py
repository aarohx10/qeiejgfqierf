from redis.asyncio import Redis
from typing import Dict, Any, Optional, List, Union
import structlog
import os
import json
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)

class RedisClient:
    def __init__(self):
        self.url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.client: Optional[Redis] = None
        self._connect()

    def _connect(self):
        """Connect to Redis."""
        try:
            self.client = Redis.from_url(self.url, decode_responses=True)
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
            raise

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            logger.info("Disconnected from Redis")

    # API Key Management
    async def set_api_key_data(self, api_key: str, user_data: Dict[str, Any], expiry: int = 3600) -> bool:
        """Cache API key data."""
        try:
            key = f"api_key:{api_key}"
            await self.client.setex(key, expiry, json.dumps(user_data))
            return True
        except Exception as e:
            logger.error(f"Error caching API key data: {e}", exc_info=True)
            return False

    async def get_api_key_data(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get cached API key data."""
        try:
            key = f"api_key:{api_key}"
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting API key data: {e}", exc_info=True)
            return None

    async def delete_api_key_data(self, api_key: str) -> bool:
        """Delete cached API key data."""
        try:
            key = f"api_key:{api_key}"
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting API key data: {e}", exc_info=True)
            return False

    # Call Data Management
    async def set_call_data(self, call_id: str, data: Dict[str, Any], expiry: int = 86400) -> bool:
        """Cache call data."""
        try:
            key = f"call:{call_id}"
            await self.client.setex(key, expiry, json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Error caching call data: {e}", exc_info=True)
            return False

    async def get_call_data(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get cached call data."""
        try:
            key = f"call:{call_id}"
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting call data: {e}", exc_info=True)
            return None

    async def update_call_data(self, call_id: str, updates: Dict[str, Any]) -> bool:
        """Update cached call data."""
        try:
            current_data = await self.get_call_data(call_id) or {}
            updated_data = {**current_data, **updates}
            return await self.set_call_data(call_id, updated_data)
        except Exception as e:
            logger.error(f"Error updating call data: {e}", exc_info=True)
            return False

    # Transcript Management
    async def append_transcript_segment(self, call_id: str, segment: Dict[str, Any]) -> bool:
        """Append a transcript segment."""
        try:
            key = f"transcript:{call_id}"
            await self.client.rpush(key, json.dumps(segment))
            return True
        except Exception as e:
            logger.error(f"Error appending transcript segment: {e}", exc_info=True)
            return False

    async def get_full_transcript(self, call_id: str) -> List[Dict[str, Any]]:
        """Get full transcript for a call."""
        try:
            key = f"transcript:{call_id}"
            segments = await self.client.lrange(key, 0, -1)
            return [json.loads(segment) for segment in segments]
        except Exception as e:
            logger.error(f"Error getting transcript: {e}", exc_info=True)
            return []

    # AI Speaking State
    async def set_ai_speaking(self, call_id: str, is_speaking: bool) -> bool:
        """Set AI speaking state."""
        try:
            key = f"ai_speaking:{call_id}"
            await self.client.set(key, "1" if is_speaking else "0")
            return True
        except Exception as e:
            logger.error(f"Error setting AI speaking state: {e}", exc_info=True)
            return False

    async def is_ai_speaking(self, call_id: str) -> bool:
        """Check if AI is speaking."""
        try:
            key = f"ai_speaking:{call_id}"
            return await self.client.get(key) == "1"
        except Exception as e:
            logger.error(f"Error checking AI speaking state: {e}", exc_info=True)
            return False

    # Conversation Memory
    async def set_conversation_memory(self, call_id: str, memory: Dict[str, Any]) -> bool:
        """Set conversation memory."""
        try:
            key = f"memory:{call_id}"
            await self.client.set(key, json.dumps(memory))
            return True
        except Exception as e:
            logger.error(f"Error setting conversation memory: {e}", exc_info=True)
            return False

    async def get_conversation_memory(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation memory."""
        try:
            key = f"memory:{call_id}"
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting conversation memory: {e}", exc_info=True)
            return None

    # Agent Configuration
    async def set_agent_config(self, agent_id: str, config: Dict[str, Any]) -> bool:
        """Cache agent configuration."""
        try:
            key = f"agent_config:{agent_id}"
            await self.client.set(key, json.dumps(config))
            return True
        except Exception as e:
            logger.error(f"Error caching agent config: {e}", exc_info=True)
            return False

    async def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get cached agent configuration."""
        try:
            key = f"agent_config:{agent_id}"
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error getting agent config: {e}", exc_info=True)
            return None

    # Call State Management
    async def set_call_state(self, call_id: str, state: str) -> bool:
        """Set call state."""
        try:
            key = f"call_state:{call_id}"
            await self.client.set(key, state)
            return True
        except Exception as e:
            logger.error(f"Error setting call state: {e}", exc_info=True)
            return False

    async def get_call_state(self, call_id: str) -> Optional[str]:
        """Get call state."""
        try:
            key = f"call_state:{call_id}"
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Error getting call state: {e}", exc_info=True)
            return None

    # Cache Management
    async def clear_call_cache(self, call_id: str) -> bool:
        """Clear all cached data for a call."""
        try:
            keys = [
                f"call:{call_id}",
                f"transcript:{call_id}",
                f"ai_speaking:{call_id}",
                f"memory:{call_id}",
                f"call_state:{call_id}"
            ]
            await self.client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Error clearing call cache: {e}", exc_info=True)
            return False

    # System Configuration
    async def set_system_config(self, config: Dict[str, Any]) -> bool:
        """Cache system configuration."""
        try:
            key = "system_config"
            await self.client.set(key, json.dumps(config))
            return True
        except Exception as e:
            logger.error(f"Error caching system config: {e}", exc_info=True)
            return False

    async def get_system_config(self) -> Dict[str, Any]:
        """Get cached system configuration."""
        try:
            key = "system_config"
            data = await self.client.get(key)
            return json.loads(data) if data else {}
        except Exception as e:
            logger.error(f"Error getting system config: {e}", exc_info=True)
            return {}

    # Health Check
    async def set_health_check(self, service: str, status: str) -> bool:
        """Set service health check status."""
        try:
            key = f"health:{service}"
            await self.client.setex(key, 60, status)
            return True
        except Exception as e:
            logger.error(f"Error setting health check: {e}", exc_info=True)
            return False

    async def get_health_check(self, service: str) -> Optional[str]:
        """Get service health check status."""
        try:
            key = f"health:{service}"
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Error getting health check: {e}", exc_info=True)
            return None 