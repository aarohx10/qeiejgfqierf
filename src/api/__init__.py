"""API package for Sendora AI Voice Infrastructure.""" 

from fastapi import APIRouter
from src.api.management import router as management_router

# Create main API router
api_router = APIRouter()

# Include management router
api_router.include_router(management_router) 