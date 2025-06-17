from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Redis Configuration
    REDIS_URL: str
    REDIS_PASSWORD: str
    REDIS_CALL_DATA_EXPIRY: int = 3600  # 1 hour
    REDIS_TRANSCRIPT_EXPIRY: int = 86400  # 24 hours

    # SignalWire Configuration
    SIGNALWIRE_PROJECT_ID: str
    SIGNALWIRE_API_TOKEN: str
    SIGNALWIRE_SPACE_URL: str
    SIGNALWIRE_WEBHOOK_SECRET: str
    SIGNALWIRE_SIGNING_SECRET: str
    SIGNALWIRE_WEBHOOK_URL_BASE: str

    # AI Services Configuration
    GEMINI_API_KEY: str
    ELEVENLABS_API_KEY: str
    DEEPGRAM_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-pro"
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Default voice ID

    # Audio Configuration
    AUDIO_FORMAT: str = "wav"
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    AUDIO_CHUNK_SIZE: int = 3200

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Default Values
    DEFAULT_INITIAL_GREETING: str = "Hello! How can I help you today?"
    DEFAULT_AI_AGENT_ID: str = "default"

    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Export settings as module-level variables
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
REDIS_URL = settings.REDIS_URL
REDIS_PASSWORD = settings.REDIS_PASSWORD
REDIS_CALL_DATA_EXPIRY = settings.REDIS_CALL_DATA_EXPIRY
REDIS_TRANSCRIPT_EXPIRY = settings.REDIS_TRANSCRIPT_EXPIRY
SIGNALWIRE_PROJECT_ID = settings.SIGNALWIRE_PROJECT_ID
SIGNALWIRE_API_TOKEN = settings.SIGNALWIRE_API_TOKEN
SIGNALWIRE_SPACE_URL = settings.SIGNALWIRE_SPACE_URL
SIGNALWIRE_WEBHOOK_SECRET = settings.SIGNALWIRE_WEBHOOK_SECRET
SIGNALWIRE_SIGNING_SECRET = settings.SIGNALWIRE_SIGNING_SECRET
SIGNALWIRE_WEBHOOK_URL_BASE = settings.SIGNALWIRE_WEBHOOK_URL_BASE
GEMINI_API_KEY = settings.GEMINI_API_KEY
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
DEEPGRAM_API_KEY = settings.DEEPGRAM_API_KEY
GEMINI_MODEL_NAME = settings.GEMINI_MODEL_NAME
ELEVENLABS_VOICE_ID = settings.ELEVENLABS_VOICE_ID
AUDIO_FORMAT = settings.AUDIO_FORMAT
AUDIO_SAMPLE_RATE = settings.AUDIO_SAMPLE_RATE
AUDIO_CHANNELS = settings.AUDIO_CHANNELS
AUDIO_CHUNK_SIZE = settings.AUDIO_CHUNK_SIZE
LOG_LEVEL = settings.LOG_LEVEL
LOG_FORMAT = settings.LOG_FORMAT
DEFAULT_INITIAL_GREETING = settings.DEFAULT_INITIAL_GREETING
DEFAULT_AI_AGENT_ID = settings.DEFAULT_AI_AGENT_ID 