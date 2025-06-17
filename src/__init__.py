"""
Sendora AI Voice Infrastructure - Core Package

This package provides the core functionality for both web-based and telephony voice calls,
including AI service integrations, audio processing, and real-time communication.
"""

from .services import GeminiService, ElevenLabsService, DeepgramService
from .audio import AudioStream, AudioProcessor
from .websocket import ConnectionManager, MessageHandler

__version__ = "1.0.0"

__all__ = [
    # Services
    'GeminiService',
    'ElevenLabsService',
    'DeepgramService',
    
    # Audio
    'AudioStream',
    'AudioProcessor',
    
    # WebSocket
    'ConnectionManager',
    'MessageHandler'
] 