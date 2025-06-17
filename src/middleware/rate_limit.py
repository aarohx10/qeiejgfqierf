import time
import logging
from typing import Callable, Optional, Dict, Tuple
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from src.redis_client import RedisClient
from src.config import REDIS_URL, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW
import structlog
import asyncio

logger = structlog.get_logger()

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        redis_url: str = REDIS_URL,
        default_limit: int = 100,
        default_window: int = 60,
        rate_limits: Optional[Dict[str, Dict[str, int]]] = None
    ):
        """Initialize rate limiting middleware.
        
        Args:
            app: FastAPI application
            redis_url: Redis connection URL
            default_limit: Default requests per window
            default_window: Default time window in seconds
            rate_limits: Optional dict of endpoint-specific limits
        """
        super().__init__(app)
        self.redis_url = redis_url
        self.default_limit = default_limit
        self.default_window = default_window
        self.rate_limits = rate_limits or {}
        self.redis_client = None
        logger.info("Rate limiting middleware initialized")

    async def initialize(self):
        """Initialize Redis client."""
        try:
            self.redis_client = RedisClient(url=self.redis_url)
            await self.redis_client.initialize()
            logger.info("Rate limiting Redis client connected")
        except Exception as e:
            logger.error(f"Failed to initialize rate limiting Redis client: {e}", exc_info=True)
            raise

    async def close(self):
        """Close Redis client."""
        try:
            if self.redis_client:
                await self.redis_client.close()
                self.redis_client = None
            logger.info("Rate limiting Redis client closed")
        except Exception as e:
            logger.error(f"Error closing rate limiting Redis client: {e}", exc_info=True)

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and apply rate limiting.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response from next handler or rate limit error
        """
        # Skip rate limiting for certain paths
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Get rate limit config for endpoint
        endpoint = request.url.path
        limit_config = self.rate_limits.get(endpoint, {
            "limit": self.default_limit,
            "window": self.default_window
        })
        limit = limit_config["limit"]
        window = limit_config["window"]

        # Get client identifier (IP or API key)
        client_id = self._get_client_id(request)
        if not client_id:
            return await call_next(request)

        # Check rate limit
        try:
            if not self.redis_client:
                await self.initialize()

            key = f"rate_limit:{endpoint}:{client_id}"
            allowed = await self.redis_client.set_rate_limit(key, limit, window)

            if not allowed:
                logger.warning(
                    "Rate limit exceeded",
                    endpoint=endpoint,
                    client_id=client_id,
                    limit=limit,
                    window=window
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too many requests",
                        "retry_after": window
                    }
                )

            # Add rate limit headers
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Window"] = str(window)
            return response

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}", exc_info=True)
            # On error, allow request to proceed
            return await call_next(request)

    def _get_client_id(self, request: Request) -> Optional[str]:
        """Get client identifier from request.
        
        Args:
            request: FastAPI request
            
        Returns:
            Client identifier (IP or API key) or None
        """
        # Try to get API key from header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"

        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        
        client_host = request.client.host if request.client else None
        if client_host:
            return f"ip:{client_host}"

        return None

    async def _check_rate_limit(self, client_id: str) -> bool:
        """Check if client has exceeded rate limit."""
        key = f"rate_limit:{client_id}"
        current = int(time.time())
        window_start = current - RATE_LIMIT_WINDOW

        # Get current count
        count = await self.redis_client.get(key)
        if count is None:
            # First request in window
            await self.redis_client.set(key, 1, RATE_LIMIT_WINDOW)
            return True

        count = int(count)
        if count >= RATE_LIMIT_REQUESTS:
            return False

        # Increment counter
        await self.redis_client.incr(key)
        return True 