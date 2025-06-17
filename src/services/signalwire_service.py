import logging
import structlog
import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, Callable
from signalwire.rest import Client as SignalWireClient
from signalwire.voice_response import VoiceResponse, Gather, Say, Play, Record, Dial, Connect, Stream
from signalwire.messages_response import MessagesResponse

logger = structlog.get_logger(__name__)

class SignalWireService:
    """Service for interacting with SignalWire API."""
    
    def __init__(
        self,
        project_id: str,
        token: str,
        space_url: str,
        default_from_number: Optional[str] = None,
        default_to_number: Optional[str] = None,
        default_agent_id: Optional[str] = None
    ):
        """Initialize SignalWire service with configurable settings."""
        self._project_id = project_id
        self._token = token
        self._space_url = space_url
        self._default_from_number = default_from_number
        self._default_to_number = default_to_number
        self._default_agent_id = default_agent_id
        
        # Initialize SignalWire client
        self._client = SignalWireClient(
            project_id,
            token,
            signalwire_space_url=space_url
        )
        
        logger.info("SignalWire service initialized with configurable settings")

    async def connect(self) -> None:
        """Connect to SignalWire API."""
        try:
            # Test connection with a simple request
            await self._client.api.accounts(self._project_id).fetch()
            logger.info("Connected to SignalWire API")
        except Exception as e:
            logger.error(f"Failed to connect to SignalWire API: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from SignalWire API."""
        # SignalWire client doesn't require explicit disconnection
        logger.info("Disconnected from SignalWire API")

    async def make_call(
        self,
        to_number: str,
        from_number: Optional[str] = None,
        agent_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        status_callback: Optional[str] = None,
        timeout: int = 30,
        record: bool = False,
        recording_status_callback: Optional[str] = None,
        recording_track: str = "both",
        machine_detection: str = "Enable",
        machine_detection_timeout: int = 30,
        machine_detection_speech_threshold: int = 3000,
        machine_detection_speech_end_threshold: int = 1000,
        machine_detection_silence_timeout: int = 10000,
        async_amd: bool = True,
        async_amd_status_callback: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make a phone call with configurable settings."""
        try:
            # Use default values if not provided
            from_number = from_number or self._default_from_number
            agent_id = agent_id or self._default_agent_id
            
            if not from_number:
                raise ValueError("From number is required")
            
            # Create call parameters
            params = {
                "to": to_number,
                "from_": from_number,
                "timeout": timeout,
                "record": record,
                "machine_detection": machine_detection,
                "machine_detection_timeout": machine_detection_timeout,
                "machine_detection_speech_threshold": machine_detection_speech_threshold,
                "machine_detection_speech_end_threshold": machine_detection_speech_end_threshold,
                "machine_detection_silence_timeout": machine_detection_silence_timeout,
                "async_amd": async_amd
            }
            
            # Add optional parameters
            if webhook_url:
                params["url"] = webhook_url
            if status_callback:
                params["status_callback"] = status_callback
            if recording_status_callback:
                params["recording_status_callback"] = recording_status_callback
            if recording_track:
                params["recording_track"] = recording_track
            if async_amd_status_callback:
                params["async_amd_status_callback"] = async_amd_status_callback
            if agent_id:
                params["agent_id"] = agent_id
            
            # Make the call
            call = await self._client.calls.create(**params)
            logger.info(f"Call initiated to {to_number} with SID: {call.sid}")
            return call.to_dict()
            
        except Exception as e:
            logger.error(f"Failed to make call to {to_number}: {e}", exc_info=True)
            raise

    async def end_call(self, call_sid: str) -> Dict[str, Any]:
        """End an active call."""
        try:
            call = await self._client.calls(call_sid).update(status="completed")
            logger.info(f"Call {call_sid} ended")
            return call.to_dict()
        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}", exc_info=True)
            raise

    async def get_call(self, call_sid: str) -> Dict[str, Any]:
        """Get call details."""
        try:
            call = await self._client.calls(call_sid).fetch()
            return call.to_dict()
        except Exception as e:
            logger.error(f"Failed to get call {call_sid}: {e}", exc_info=True)
            raise

    async def list_calls(
        self,
        status: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        from_number: Optional[str] = None,
        to_number: Optional[str] = None,
        limit: int = 20
    ) -> list[Dict[str, Any]]:
        """List calls with optional filters."""
        try:
            params = {"limit": limit}
            if status:
                params["status"] = status
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time
            if from_number:
                params["from_"] = from_number
            if to_number:
                params["to"] = to_number
            
            calls = await self._client.calls.list(**params)
            return [call.to_dict() for call in calls]
        except Exception as e:
            logger.error(f"Failed to list calls: {e}", exc_info=True)
            raise

    def create_voice_response(
        self,
        say_text: Optional[str] = None,
        play_url: Optional[str] = None,
        gather_input: Optional[str] = None,
        record: bool = False,
        dial_number: Optional[str] = None,
        connect_stream: Optional[Dict[str, Any]] = None,
        stream_url: Optional[str] = None
    ) -> str:
        """Create a VoiceResponse with configurable actions."""
        try:
            response = VoiceResponse()
            
            if say_text:
                response.say(say_text)
            if play_url:
                response.play(play_url)
            if gather_input:
                gather = Gather(input=gather_input)
                response.append(gather)
            if record:
                response.record()
            if dial_number:
                response.dial(dial_number)
            if connect_stream:
                response.connect(connect_stream)
            if stream_url:
                response.stream(url=stream_url)
            
            return str(response)
        except Exception as e:
            logger.error(f"Failed to create voice response: {e}", exc_info=True)
            raise

    async def send_sms(
        self,
        to_number: str,
        body: str,
        from_number: Optional[str] = None,
        media_url: Optional[list[str]] = None,
        status_callback: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send an SMS message."""
        try:
            from_number = from_number or self._default_from_number
            if not from_number:
                raise ValueError("From number is required")
            
            params = {
                "to": to_number,
                "from_": from_number,
                "body": body
            }
            
            if media_url:
                params["media_url"] = media_url
            if status_callback:
                params["status_callback"] = status_callback
            
            message = await self._client.messages.create(**params)
            logger.info(f"SMS sent to {to_number} with SID: {message.sid}")
            return message.to_dict()
        except Exception as e:
            logger.error(f"Failed to send SMS to {to_number}: {e}", exc_info=True)
            raise

    async def get_message(self, message_sid: str) -> Dict[str, Any]:
        """Get message details."""
        try:
            message = await self._client.messages(message_sid).fetch()
            return message.to_dict()
        except Exception as e:
            logger.error(f"Failed to get message {message_sid}: {e}", exc_info=True)
            raise

    async def list_messages(
        self,
        to_number: Optional[str] = None,
        from_number: Optional[str] = None,
        date_sent: Optional[str] = None,
        limit: int = 20
    ) -> list[Dict[str, Any]]:
        """List messages with optional filters."""
        try:
            params = {"limit": limit}
            if to_number:
                params["to"] = to_number
            if from_number:
                params["from_"] = from_number
            if date_sent:
                params["date_sent"] = date_sent
            
            messages = await self._client.messages.list(**params)
            return [message.to_dict() for message in messages]
        except Exception as e:
            logger.error(f"Failed to list messages: {e}", exc_info=True)
            raise

    async def handle_media_stream(
        self,
        call_sid: str,
        stream_url: str,
        stream_name: str,
        stream_parameters: Optional[Dict[str, Any]] = None,
        on_stream_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_stream_end: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_stream_error: Optional[Callable[[Exception], None]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle a media stream for a call.
        
        Args:
            call_sid: The call SID to stream media for
            stream_url: The URL to stream media from
            stream_name: Name of the stream
            stream_parameters: Optional parameters for the stream
            on_stream_start: Optional callback for stream start events
            on_stream_end: Optional callback for stream end events
            on_stream_error: Optional callback for stream error events
            
        Yields:
            Stream events as they occur
        """
        try:
            # Create stream parameters
            params = {
                "url": stream_url,
                "name": stream_name
            }
            if stream_parameters:
                params.update(stream_parameters)
            
            # Create stream
            stream = await self._client.calls(call_sid).streams.create(**params)
            
            # Set up event handlers
            if on_stream_start:
                stream.on("start", on_stream_start)
            if on_stream_end:
                stream.on("end", on_stream_end)
            if on_stream_error:
                stream.on("error", on_stream_error)
            
            # Start the stream
            await stream.start()
            
            # Yield stream events
            async for event in stream.events():
                yield event
                
        except Exception as e:
            logger.error(f"Failed to handle media stream for call {call_sid}: {e}", exc_info=True)
            if on_stream_error:
                on_stream_error(e)
            raise

    async def stop_media_stream(self, call_sid: str, stream_sid: str) -> None:
        """Stop a media stream."""
        try:
            await self._client.calls(call_sid).streams(stream_sid).update(status="stopped")
            logger.info(f"Stopped media stream {stream_sid} for call {call_sid}")
        except Exception as e:
            logger.error(f"Failed to stop media stream {stream_sid} for call {call_sid}: {e}", exc_info=True)
            raise

    async def get_media_stream(self, call_sid: str, stream_sid: str) -> Dict[str, Any]:
        """Get media stream details."""
        try:
            stream = await self._client.calls(call_sid).streams(stream_sid).fetch()
            return stream.to_dict()
        except Exception as e:
            logger.error(f"Failed to get media stream {stream_sid} for call {call_sid}: {e}", exc_info=True)
            raise

    async def list_media_streams(
        self,
        call_sid: str,
        status: Optional[str] = None,
        limit: int = 20
    ) -> list[Dict[str, Any]]:
        """List media streams for a call."""
        try:
            params = {"limit": limit}
            if status:
                params["status"] = status
            
            streams = await self._client.calls(call_sid).streams.list(**params)
            return [stream.to_dict() for stream in streams]
        except Exception as e:
            logger.error(f"Failed to list media streams for call {call_sid}: {e}", exc_info=True)
            raise

    async def update_media_stream(
        self,
        call_sid: str,
        stream_sid: str,
        status: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Update media stream settings."""
        try:
            params = {}
            if status:
                params["status"] = status
            if parameters:
                params.update(parameters)
            
            stream = await self._client.calls(call_sid).streams(stream_sid).update(**params)
            return stream.to_dict()
        except Exception as e:
            logger.error(f"Failed to update media stream {stream_sid} for call {call_sid}: {e}", exc_info=True)
            raise

    async def handle_audio_stream(
        self,
        call_sid: str,
        audio_stream: AsyncGenerator[bytes, None],
        stream_name: str = "audio_stream",
        on_stream_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_stream_end: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_stream_error: Optional[Callable[[Exception], None]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle an audio stream for a call.
        
        Args:
            call_sid: The call SID to stream audio for
            audio_stream: Async generator yielding audio chunks
            stream_name: Name of the stream
            on_stream_start: Optional callback for stream start events
            on_stream_end: Optional callback for stream end events
            on_stream_error: Optional callback for stream error events
            
        Yields:
            Stream events as they occur
        """
        try:
            # Create stream parameters for audio
            params = {
                "name": stream_name,
                "track": "inbound_track",
                "media_format": "audio/x-raw",
                "sample_rate": 16000,
                "channels": 1,
                "encoding": "linear16"
            }
            
            # Create and start stream
            stream = await self._client.calls(call_sid).streams.create(**params)
            
            # Set up event handlers
            if on_stream_start:
                stream.on("start", on_stream_start)
            if on_stream_end:
                stream.on("end", on_stream_end)
            if on_stream_error:
                stream.on("error", on_stream_error)
            
            # Start the stream
            await stream.start()
            
            # Process audio stream
            async for chunk in audio_stream:
                if chunk:
                    await stream.write(chunk)
            
            # Stop the stream
            await stream.stop()
            
            # Yield stream events
            async for event in stream.events():
                yield event
                
        except Exception as e:
            logger.error(f"Failed to handle audio stream for call {call_sid}: {e}", exc_info=True)
            if on_stream_error:
                on_stream_error(e)
            raise 