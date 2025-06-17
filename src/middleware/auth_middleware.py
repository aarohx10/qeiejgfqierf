from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from typing import Optional, Dict, Any
import structlog
import os
from datetime import datetime, timedelta
import jwt
from functools import lru_cache

from src.services.supabase_client import SupabaseClient
from src.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

# API Key header and query parameter
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY = timedelta(hours=24)

class AuthMiddleware:
    def __init__(self, supabase: SupabaseClient, redis: RedisClient):
        self.supabase = supabase
        self.redis = redis
        self._api_keys: Dict[str, Dict[str, Any]] = {}
        self._last_api_key_refresh = datetime.min

    async def get_api_key(
        self,
        api_key_header: Optional[str] = Security(API_KEY_HEADER),
        api_key_query: Optional[str] = Security(API_KEY_QUERY)
    ) -> str:
        """Get API key from header or query parameter."""
        api_key = api_key_header or api_key_query
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is required"
            )
        return api_key

    async def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        """Validate API key and return associated user data."""
        # Check cache first
        if api_key in self._api_keys:
            return self._api_keys[api_key]

        # Check Redis cache
        cached_data = await self.redis.get_api_key_data(api_key)
        if cached_data:
            self._api_keys[api_key] = cached_data
            return cached_data

        # Check database
        try:
            user_data = await self.supabase.get_api_key_user(api_key)
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key"
                )

            # Cache the result
            await self.redis.set_api_key_data(api_key, user_data)
            self._api_keys[api_key] = user_data
            return user_data

        except Exception as e:
            logger.error(f"Error validating API key: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

    async def refresh_api_keys(self):
        """Refresh API keys cache from database."""
        try:
            api_keys = await self.supabase.list_api_keys()
            for key_data in api_keys:
                self._api_keys[key_data["key"]] = key_data
                await self.redis.set_api_key_data(key_data["key"], key_data)
            self._last_api_key_refresh = datetime.now()
        except Exception as e:
            logger.error(f"Error refreshing API keys: {e}", exc_info=True)

    def create_jwt_token(self, user_data: Dict[str, Any]) -> str:
        """Create JWT token for user."""
        try:
            payload = {
                "sub": user_data["id"],
                "email": user_data["email"],
                "exp": datetime.utcnow() + JWT_EXPIRY
            }
            return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        except Exception as e:
            logger.error(f"Error creating JWT token: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating authentication token"
            )

    def validate_jwt_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token and return user data."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.JWTError as e:
            logger.error(f"Error validating JWT token: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    async def get_current_user(
        self,
        api_key: str = Depends(get_api_key)
    ) -> Dict[str, Any]:
        """Get current user from API key."""
        # Refresh API keys if needed
        if datetime.now() - self._last_api_key_refresh > timedelta(minutes=5):
            await self.refresh_api_keys()

        # Validate API key
        user_data = await self.validate_api_key(api_key)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

        return user_data

    async def get_current_active_user(
        self,
        current_user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """Get current active user."""
        if not current_user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user"
            )
        return current_user

    async def get_current_admin_user(
        self,
        current_user: Dict[str, Any] = Depends(get_current_active_user)
    ) -> Dict[str, Any]:
        """Get current admin user."""
        if not current_user.get("is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user

# Create singleton instance
@lru_cache()
def get_auth_middleware(
    supabase: SupabaseClient = Depends(),
    redis: RedisClient = Depends()
) -> AuthMiddleware:
    """Get singleton instance of AuthMiddleware."""
    return AuthMiddleware(supabase, redis)

# Export dependencies
get_current_user = get_auth_middleware().get_current_user
get_current_active_user = get_auth_middleware().get_current_active_user
get_current_admin_user = get_auth_middleware().get_current_admin_user 