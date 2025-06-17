from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Optional, Dict, Any
import structlog
from src.config import JWT_SECRET_KEY, JWT_ALGORITHM
from src.redis_client import RedisClient
from src.config import REDIS_URL

logger = structlog.get_logger()
security = HTTPBearer()

class AuthMiddleware:
    def __init__(self, redis_url: str = REDIS_URL):
        """Initialize auth middleware.
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.redis_client = None
        logger.info("Auth middleware initialized")

    async def initialize(self):
        """Initialize Redis client."""
        try:
            self.redis_client = RedisClient(url=self.redis_url)
            await self.redis_client.initialize()
            logger.info("Auth Redis client connected")
        except Exception as e:
            logger.error(f"Failed to initialize auth Redis client: {e}", exc_info=True)
            raise

    async def close(self):
        """Close Redis client."""
        try:
            if self.redis_client:
                await self.redis_client.close()
                self.redis_client = None
            logger.info("Auth Redis client closed")
        except Exception as e:
            logger.error(f"Error closing auth Redis client: {e}", exc_info=True)

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token.
        
        Args:
            token: JWT token
            
        Returns:
            Decoded token payload
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Decode token
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM]
            )

            # Check if token is blacklisted
            if not self.redis_client:
                await self.initialize()

            is_blacklisted = await self.redis_client.exists(f"token_blacklist:{token}")
            if is_blacklisted:
                raise HTTPException(
                    status_code=401,
                    detail="Token has been revoked"
                )

            return payload

        except JWTError as e:
            logger.error(f"Token verification failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token"
            )
        except Exception as e:
            logger.error(f"Token verification error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Internal server error"
            )

    async def blacklist_token(self, token: str, expire_seconds: int = 86400):
        """Add token to blacklist.
        
        Args:
            token: JWT token to blacklist
            expire_seconds: Blacklist expiration time in seconds
        """
        try:
            if not self.redis_client:
                await self.initialize()

            await self.redis_client.set(
                f"token_blacklist:{token}",
                "1",
                expire=expire_seconds
            )
            logger.info(f"Token blacklisted for {expire_seconds} seconds")

        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to blacklist token"
            )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Get current user from JWT token.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        User data from token payload
        
    Raises:
        HTTPException: If token is invalid
    """
    try:
        # Initialize auth middleware
        auth = AuthMiddleware()
        await auth.initialize()

        try:
            # Verify token
            payload = await auth.verify_token(credentials.credentials)
            return payload
        finally:
            await auth.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get current user: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current active user.
    
    Args:
        current_user: Current user data
        
    Returns:
        Active user data
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Inactive user"
        )
    return current_user

async def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current admin user.
    
    Args:
        current_user: Current user data
        
    Returns:
        Admin user data
        
    Raises:
        HTTPException: If user is not admin
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions"
        )
    return current_user 