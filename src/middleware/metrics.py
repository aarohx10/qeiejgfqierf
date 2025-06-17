import time
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import structlog

logger = structlog.get_logger()

# Define metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint']
)

ERROR_COUNT = Counter(
    'http_errors_total',
    'Total number of HTTP errors',
    ['method', 'endpoint', 'error_type']
)

class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        exclude_paths: Optional[list] = None,
        include_paths: Optional[list] = None
    ):
        """Initialize metrics middleware.
        
        Args:
            app: FastAPI application
            exclude_paths: List of paths to exclude from metrics
            include_paths: List of paths to include in metrics (if None, all paths included)
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/metrics", "/docs", "/redoc", "/openapi.json"]
        self.include_paths = include_paths
        logger.info("Metrics middleware initialized")

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and collect metrics.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response from next handler
        """
        # Skip metrics for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Skip metrics for non-included paths if include_paths is set
        if self.include_paths and request.url.path not in self.include_paths:
            return await call_next(request)

        # Get endpoint name
        endpoint = request.url.path
        method = request.method

        # Record request start time
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)
            
            # Record request metrics
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status=response.status_code
            ).inc()
            
            REQUEST_LATENCY.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            # Log request
            logger.info(
                "Request processed",
                method=method,
                endpoint=endpoint,
                status=response.status_code,
                duration=duration
            )

            return response

        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            ERROR_COUNT.labels(
                method=method,
                endpoint=endpoint,
                error_type=type(e).__name__
            ).inc()

            # Log error
            logger.error(
                "Request failed",
                method=method,
                endpoint=endpoint,
                error=str(e),
                duration=duration,
                exc_info=True
            )

            raise

class MetricsEndpoint:
    """FastAPI endpoint for exposing Prometheus metrics."""

    async def __call__(self, request: Request) -> Response:
        """Handle metrics endpoint request.
        
        Args:
            request: FastAPI request
            
        Returns:
            Prometheus metrics response
        """
        try:
            metrics = generate_latest()
            return Response(
                content=metrics,
                media_type=CONTENT_TYPE_LATEST
            )
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}", exc_info=True)
            return Response(
                content=str(e),
                status_code=500
            ) 