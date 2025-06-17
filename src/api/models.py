from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import re

class PhoneNumberCreate(BaseModel):
    """Model for creating a phone number."""
    number: str = Field(..., description="Phone number in E.164 format")
    friendly_name: Optional[str] = Field(None, description="Friendly name for the number")
    region: Optional[str] = Field(None, description="Region code")
    
    @validator("number")
    def validate_phone_number(cls, v):
        """Validate phone number format."""
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("Phone number must be in E.164 format (e.g., +1234567890)")
        return v

class SIPTrunkCreate(BaseModel):
    """Model for creating a SIP trunk."""
    name: str = Field(..., description="Name of the SIP trunk")
    host: str = Field(..., description="Host address")
    port: int = Field(..., ge=1, le=65535, description="Port number")
    username: str = Field(..., description="Username for authentication")
    password: str = Field(..., min_length=8, description="Password for authentication")
    
    @validator("host")
    def validate_host(cls, v):
        """Validate host format."""
        if not re.match(r"^[a-zA-Z0-9.-]+$", v):
            raise ValueError("Invalid host format")
        return v

class CallCreate(BaseModel):
    """Model for creating a call."""
    to: str = Field(..., description="Destination phone number")
    from_: str = Field(..., alias="from", description="Source phone number")
    agent_id: Optional[str] = Field(None, description="AI agent ID to use")
    
    @validator("to", "from_")
    def validate_phone_number(cls, v):
        """Validate phone number format."""
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("Phone number must be in E.164 format (e.g., +1234567890)")
        return v

class AIAgentCreate(BaseModel):
    """Model for creating an AI agent."""
    name: str = Field(..., description="Name of the AI agent")
    system_prompt: str = Field(..., description="System prompt for the agent")
    voice_id: str = Field(..., description="Voice ID for TTS")
    language: str = Field(..., description="Language code")
    model: str = Field(..., description="Model to use")
    temperature: float = Field(..., ge=0.0, le=1.0, description="Temperature for generation")
    
    @validator("language")
    def validate_language(cls, v):
        """Validate language code."""
        if not re.match(r"^[a-z]{2}(-[A-Z]{2})?$", v):
            raise ValueError("Invalid language code format (e.g., en, en-US)")
        return v

class CallRecord(BaseModel):
    """Model for call record."""
    call_id: str = Field(..., description="Unique call identifier")
    from_number: str = Field(..., description="Source phone number")
    to_number: str = Field(..., description="Destination phone number")
    start_time: str = Field(..., description="Call start time")
    end_time: Optional[str] = Field(None, description="Call end time")
    duration: Optional[int] = Field(None, ge=0, description="Call duration in seconds")
    status: str = Field(..., description="Call status")
    agent_id: Optional[str] = Field(None, description="AI agent ID used")
    transcript: Optional[List[Dict[str, Any]]] = Field(None, description="Call transcript")
    
    @validator("status")
    def validate_status(cls, v):
        """Validate call status."""
        valid_statuses = ["initiated", "in-progress", "completed", "failed"]
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {', '.join(valid_statuses)}")
        return v 