import logging
import json
import structlog
from typing import Dict, Any, Optional, List, Union
import redis.asyncio as redis
from config import REDIS_URL, REDIS_PASSWORD, REDIS_CALL_DATA_EXPIRY, REDIS_TRANSCRIPT_EXPIRY
from datetime import datetime, timedelta, timezone

logger = structlog.get_logger(__name__)

class RedisClient:
    """Client for interacting with Redis cache."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        """Initialize Redis client."""
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._client: Optional[redis.Redis] = None
        logger.info("Redis client initialized")

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._client = redis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                decode_responses=True
            )
            await self._client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Disconnected from Redis")

    def _ensure_connection(self) -> None:
        """Ensure client is connected."""
        if not self._client:
            raise RuntimeError("Redis client not connected")

    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis.
        
        Args:
            key: Redis key
            value: Value to store (will be JSON serialized)
            expire: Optional expiration time in seconds
            
        Returns:
            True if successful
        """
        try:
            serialized = json.dumps(value)
            if expire:
                return await self._client.set(key, serialized, ex=expire)
            return await self._client.set(key, serialized)
        except Exception as e:
            logger.error(f"Failed to set Redis key {key}: {e}", exc_info=True)
            raise

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis.
        
        Args:
            key: Redis key
            
        Returns:
            Deserialized value if found, None otherwise
        """
        try:
            value = await self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Failed to get Redis key {key}: {e}", exc_info=True)
            raise

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis.
        
        Args:
            key: Redis key
            
        Returns:
            True if deleted, False if key didn't exist
        """
        try:
            return bool(await self._client.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete Redis key {key}: {e}", exc_info=True)
            raise

    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis.
        
        Args:
            key: Redis key
            
        Returns:
            True if key exists
        """
        try:
            return bool(await self._client.exists(key))
        except Exception as e:
            logger.error(f"Failed to check Redis key {key}: {e}", exc_info=True)
            raise

    async def set_session(self, session_id: str, data: Dict[str, Any], expire: int = 3600) -> bool:
        """Set session data in Redis.
        
        Args:
            session_id: Session ID
            data: Session data
            expire: Session expiration time in seconds
            
        Returns:
            True if successful
        """
        try:
            key = f"session:{session_id}"
            return await self.set(key, data, expire=expire)
        except Exception as e:
            logger.error(f"Failed to set session {session_id}: {e}", exc_info=True)
            raise

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data from Redis.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session data if found, None otherwise
        """
        try:
            key = f"session:{session_id}"
            return await self.get(key)
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}", exc_info=True)
            raise

    async def delete_session(self, session_id: str) -> bool:
        """Delete session data from Redis.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if deleted, False if session didn't exist
        """
        try:
            key = f"session:{session_id}"
            return await self.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}", exc_info=True)
            raise

    async def set_call_state(self, call_id: str, state: Dict[str, Any]) -> None:
        """Set call state."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:state"
            await self._client.set(redis_key, json.dumps(state), ex=3600)
            logger.debug(f"Set call state for call {call_id}")
        except Exception as e:
            logger.error(f"Failed to set call state for call {call_id}: {e}", exc_info=True)
            raise

    async def get_call_state(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call state."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:state"
            value = await self._client.get(redis_key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Failed to get call state for call {call_id}: {e}", exc_info=True)
            raise

    async def delete_call_state(self, call_id: str) -> bool:
        """Delete call state from Redis.
        
        Args:
            call_id: Call ID
            
        Returns:
            True if deleted, False if state didn't exist
        """
        try:
            redis_key = f"call:{call_id}:state"
            return bool(await self._client.delete(redis_key))
        except Exception as e:
            logger.error(f"Failed to delete call state for {call_id}: {e}", exc_info=True)
            raise

    async def set_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """Set rate limit in Redis.
        
        Args:
            key: Rate limit key
            limit: Maximum number of requests
            window: Time window in seconds
            
        Returns:
            True if successful
        """
        try:
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=window)
            
            # Clean old requests
            await self._client.zremrangebyscore(key, 0, window_start.timestamp())
            
            # Add current request
            await self._client.zadd(key, {str(now.timestamp()): now.timestamp()})
            
            # Set expiration
            await self._client.expire(key, window)
            
            # Check if limit exceeded
            count = await self._client.zcard(key)
            return count <= limit
        except Exception as e:
            logger.error(f"Failed to set rate limit for {key}: {e}", exc_info=True)
            raise

    async def set_call_data(self, call_id: str, key: str, value: Any, expiry: int = 3600) -> None:
        """Set call data with expiry."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:{key}"
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await self._client.set(redis_key, value, ex=expiry)
            logger.debug(f"Set call data for {call_id}:{key}")
        except Exception as e:
            logger.error(f"Failed to set call data for {call_id}:{key}: {e}", exc_info=True)
            raise

    async def get_call_data(self, call_id: str, key: str) -> Any:
        """Get call data."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:{key}"
            value = await self._client.get(redis_key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Failed to get call data for {call_id}:{key}: {e}", exc_info=True)
            raise

    async def append_transcript_segment(self, call_id: str, segment: Dict[str, Any]) -> None:
        """Append a transcript segment to the call's transcript history."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:transcript_history"
            await self._client.rpush(redis_key, json.dumps(segment))
            logger.debug(f"Appended transcript segment for call {call_id}")
        except Exception as e:
            logger.error(f"Failed to append transcript segment for call {call_id}: {e}", exc_info=True)
            raise

    async def get_full_transcript(self, call_id: str) -> List[Dict[str, Any]]:
        """Get the full transcript history for a call."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:transcript_history"
            segments = await self._client.lrange(redis_key, 0, -1)
            return [json.loads(segment) for segment in segments]
        except Exception as e:
            logger.error(f"Failed to get full transcript for call {call_id}: {e}", exc_info=True)
            raise

    async def clear_call_cache(self, call_id: str) -> None:
        """Clear all cached data for a call."""
        self._ensure_connection()
        try:
            pattern = f"call:{call_id}:*"
            keys = await self._client.keys(pattern)
            if keys:
                await self._client.delete(*keys)
            logger.info(f"Cleared cache for call {call_id}")
        except Exception as e:
            logger.error(f"Failed to clear cache for call {call_id}: {e}", exc_info=True)
            raise

    async def set_ai_speaking(self, call_id: str, is_speaking: bool) -> None:
        """Set AI speaking state."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:is_ai_speaking"
            await self._client.set(redis_key, str(is_speaking).lower(), ex=3600)
            logger.debug(f"Set AI speaking state for call {call_id}: {is_speaking}")
        except Exception as e:
            logger.error(f"Failed to set AI speaking state for call {call_id}: {e}", exc_info=True)
            raise

    async def is_ai_speaking(self, call_id: str) -> bool:
        """Check if AI is currently speaking."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:is_ai_speaking"
            value = await self._client.get(redis_key)
            return value == "true"
        except Exception as e:
            logger.error(f"Failed to check AI speaking state for call {call_id}: {e}", exc_info=True)
            raise

    async def set_call_quality_metrics(
        self,
        call_id: str,
        metrics: Dict[str, Any]
    ) -> None:
        """Set call quality metrics."""
        self._ensure_connection()
        key = f"call:{call_id}:quality"
        await self._client.set(key, json.dumps(metrics))
        await self._client.expire(key, self.transcript_expire_seconds)

    async def get_call_quality_metrics(
        self,
        call_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get call quality metrics."""
        self._ensure_connection()
        key = f"call:{call_id}:quality"
        data = await self._client.get(key)
        return json.loads(data) if data else None

    async def set_call_analytics(
        self,
        call_id: str,
        analytics: Dict[str, Any]
    ) -> None:
        """Set call analytics."""
        self._ensure_connection()
        key = f"call:{call_id}:analytics"
        await self._client.set(key, json.dumps(analytics))
        await self._client.expire(key, self.transcript_expire_seconds)

    async def get_call_analytics(
        self,
        call_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get call analytics."""
        self._ensure_connection()
        key = f"call:{call_id}:analytics"
        data = await self._client.get(key)
        return json.loads(data) if data else None

    async def delete_call_data(self, call_id: str) -> None:
        """Delete all Redis data for a call."""
        self._ensure_connection()
        keys = await self._client.keys(f"call:{call_id}:*")
        if keys:
            await self._client.delete(*keys)
            logger.info(f"Deleted Redis data for call {call_id}")

    async def set_agent_config(self, call_id: str, config: Dict[str, Any]) -> None:
        """Set agent configuration for a call."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:agent_config"
            await self._client.set(redis_key, json.dumps(config), ex=3600)
            logger.debug(f"Set agent config for call {call_id}")
        except Exception as e:
            logger.error(f"Failed to set agent config for call {call_id}: {e}", exc_info=True)
            raise

    async def get_agent_config(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get agent configuration for a call."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:agent_config"
            value = await self._client.get(redis_key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Failed to get agent config for call {call_id}: {e}", exc_info=True)
            raise

    async def set_conversation_memory(self, call_id: str, memory: List[Dict[str, Any]]) -> None:
        """Set conversation memory for a call."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:conversation_memory"
            await self._client.set(redis_key, json.dumps(memory), ex=3600)
            logger.debug(f"Set conversation memory for call {call_id}")
        except Exception as e:
            logger.error(f"Failed to set conversation memory for call {call_id}: {e}", exc_info=True)
            raise

    async def get_conversation_memory(self, call_id: str) -> List[Dict[str, Any]]:
        """Get conversation memory for a call."""
        self._ensure_connection()
        try:
            redis_key = f"call:{call_id}:conversation_memory"
            value = await self._client.get(redis_key)
            return json.loads(value) if value else []
        except Exception as e:
            logger.error(f"Failed to get conversation memory for call {call_id}: {e}", exc_info=True)
            raise

    async def set_health_check(self, service: str, status: Dict[str, Any]) -> None:
        """Set health check status for a service."""
        self._ensure_connection()
        try:
            redis_key = f"health:{service}"
            await self._client.set(redis_key, json.dumps(status), ex=300)  # 5 minutes expiry
            logger.debug(f"Set health check for service {service}")
        except Exception as e:
            logger.error(f"Failed to set health check for service {service}: {e}", exc_info=True)
            raise

    async def get_health_check(self, service: str) -> Optional[Dict[str, Any]]:
        """Get health check status for a service."""
        self._ensure_connection()
        try:
            redis_key = f"health:{service}"
            value = await self._client.get(redis_key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Failed to get health check for service {service}: {e}", exc_info=True)
            raise 