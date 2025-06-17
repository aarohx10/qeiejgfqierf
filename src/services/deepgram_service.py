import logging
import structlog
import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, Callable
from deepgram import Deepgram
from deepgram.transcription import LiveTranscriptionEvents, LiveOptions

logger = structlog.get_logger(__name__)

class DeepgramService:
    """Service for interacting with Deepgram API."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str = "en",
        sample_rate: int = 16000,
        channels: int = 1,
        encoding: str = "linear16",
        punctuate: bool = True,
        diarize: bool = True,
        vad_turnoff_ms: int = 1000,
        vad_events: bool = True,
        endpointing: int = 300,
        smart_format: bool = True,
        filler_words: bool = False,
        profanity_filter: bool = False,
        alternatives: int = 0,
        numerals: bool = False,
        detect_language: bool = False,
        search: Optional[list[str]] = None,
        replace: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
        callback_url: Optional[str] = None
    ):
        """Initialize Deepgram service with configurable settings."""
        self._api_key = api_key
        self._client = Deepgram(api_key)
        
        # Audio configuration
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        self._channels = channels
        self._encoding = encoding
        
        # Transcription options
        self._punctuate = punctuate
        self._diarize = diarize
        self._vad_turnoff_ms = vad_turnoff_ms
        self._vad_events = vad_events
        self._endpointing = endpointing
        self._smart_format = smart_format
        self._filler_words = filler_words
        self._profanity_filter = profanity_filter
        self._alternatives = alternatives
        self._numerals = numerals
        self._detect_language = detect_language
        
        # Additional features
        self._search = search
        self._replace = replace
        self._keywords = keywords
        self._callback_url = callback_url
        
        logger.info("Deepgram service initialized with configurable settings")

    async def connect(self) -> None:
        """Connect to Deepgram API."""
        try:
            # Test connection with a simple request
            await self._client.get_balance()
            logger.info("Connected to Deepgram API")
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram API: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from Deepgram API."""
        # Deepgram client doesn't require explicit disconnection
        logger.info("Disconnected from Deepgram API")

    def _get_live_options(self) -> LiveOptions:
        """Get configured live transcription options."""
        return LiveOptions(
            model=self._model,
            language=self._language,
            encoding=self._encoding,
            channels=self._channels,
            sample_rate=self._sample_rate,
            punctuate=self._punctuate,
            diarize=self._diarize,
            vad_turnoff_ms=self._vad_turnoff_ms,
            vad_events=self._vad_events,
            endpointing=self._endpointing,
            smart_format=self._smart_format,
            filler_words=self._filler_words,
            profanity_filter=self._profanity_filter,
            alternatives=self._alternatives,
            numerals=self._numerals,
            detect_language=self._detect_language,
            search=self._search,
            replace=self._replace,
            keywords=self._keywords,
            callback_url=self._callback_url
        )

    async def transcribe_audio_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        on_transcript: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_metadata: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_close: Optional[Callable[[], None]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Transcribe an audio stream with configurable settings.
        
        Args:
            audio_stream: Async generator yielding audio chunks
            on_transcript: Optional callback for transcript events
            on_metadata: Optional callback for metadata events
            on_error: Optional callback for error events
            on_close: Optional callback for close events
            
        Yields:
            Transcription results as they become available
        """
        try:
            # Create live transcription connection
            dg_connection = self._client.listen.live.v(self._get_live_options())
            
            # Set up event handlers
            if on_transcript:
                dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
            if on_metadata:
                dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
            if on_error:
                dg_connection.on(LiveTranscriptionEvents.Error, on_error)
            if on_close:
                dg_connection.on(LiveTranscriptionEvents.Close, on_close)
            
            # Start the connection
            await dg_connection.start()
            
            # Process audio stream
            async for chunk in audio_stream:
                if chunk:
                    await dg_connection.send(chunk)
            
            # Finish the connection
            await dg_connection.finish()
            
            # Yield final results
            async for result in dg_connection:
                yield result
                
        except Exception as e:
            logger.error(f"Error in audio stream transcription: {e}", exc_info=True)
            if on_error:
                on_error(e)
            raise

    async def transcribe_file(
        self,
        file_path: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Transcribe an audio file with configurable settings."""
        try:
            with open(file_path, "rb") as audio:
                source = {"buffer": audio, "mimetype": "audio/wav"}
                response = await self._client.transcription.prerecorded(
                    source,
                    self._get_live_options().__dict__
                )
                return response
        except Exception as e:
            logger.error(f"Failed to transcribe file {file_path}: {e}", exc_info=True)
            raise

    async def get_models(self) -> Dict[str, Any]:
        """Get available Deepgram models."""
        try:
            response = await self._client.manage.v("models")
            return response
        except Exception as e:
            logger.error(f"Failed to get Deepgram models: {e}", exc_info=True)
            raise

    async def get_usage(self) -> Dict[str, Any]:
        """Get usage information."""
        try:
            response = await self._client.manage.v("usage")
            return response
        except Exception as e:
            logger.error(f"Failed to get usage information: {e}", exc_info=True)
            raise

    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        try:
            response = await self._client.manage.v("balance")
            return response
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}", exc_info=True)
            raise

    def update_settings(
        self,
        model: Optional[str] = None,
        language: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        encoding: Optional[str] = None,
        punctuate: Optional[bool] = None,
        diarize: Optional[bool] = None,
        vad_turnoff_ms: Optional[int] = None,
        vad_events: Optional[bool] = None,
        endpointing: Optional[int] = None,
        smart_format: Optional[bool] = None,
        filler_words: Optional[bool] = None,
        profanity_filter: Optional[bool] = None,
        alternatives: Optional[int] = None,
        numerals: Optional[bool] = None,
        detect_language: Optional[bool] = None,
        search: Optional[list[str]] = None,
        replace: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
        callback_url: Optional[str] = None
    ) -> None:
        """Update service settings."""
        if model is not None:
            self._model = model
        if language is not None:
            self._language = language
        if sample_rate is not None:
            self._sample_rate = sample_rate
        if channels is not None:
            self._channels = channels
        if encoding is not None:
            self._encoding = encoding
        if punctuate is not None:
            self._punctuate = punctuate
        if diarize is not None:
            self._diarize = diarize
        if vad_turnoff_ms is not None:
            self._vad_turnoff_ms = vad_turnoff_ms
        if vad_events is not None:
            self._vad_events = vad_events
        if endpointing is not None:
            self._endpointing = endpointing
        if smart_format is not None:
            self._smart_format = smart_format
        if filler_words is not None:
            self._filler_words = filler_words
        if profanity_filter is not None:
            self._profanity_filter = profanity_filter
        if alternatives is not None:
            self._alternatives = alternatives
        if numerals is not None:
            self._numerals = numerals
        if detect_language is not None:
            self._detect_language = detect_language
        if search is not None:
            self._search = search
        if replace is not None:
            self._replace = replace
        if keywords is not None:
            self._keywords = keywords
        if callback_url is not None:
            self._callback_url = callback_url
            
        logger.info("Updated Deepgram service settings")

    async def process_audio_stream(self, audio_chunk_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[Dict, None]:
        """
        Establishes a live transcription session with Deepgram and processes audio chunks.
        Yields dictionaries containing transcription results (final or interim) and events.
        """
        self.results_queue = asyncio.Queue()
        dg_connection = None
        
        try:
            options = LiveOptions(
                encoding="linear16",
                sample_rate=16000,
                channels=1,
                punctuate=True,
                interim_results=True,
                utterance_end_ms=1000,
            )
            
            dg_connection = self._client.listen.asynclive.v("1")
            
            async def on_message(self, result, **kwargs):
                if result.is_final:
                    await self.results_queue.put({
                        "is_final": True,
                        "transcript": result.channel.alternatives[0].transcript,
                        "speech_final": True
                    })
                else:
                    await self.results_queue.put({
                        "is_final": False,
                        "transcript": result.channel.alternatives[0].transcript,
                        "speech_final": False
                    })
                    
            async def on_speech_started(self, **kwargs):
                await self.results_queue.put({"event": "speech_started"})
                
            async def on_error(self, error, **kwargs):
                logger.error(f"Deepgram stream error: {error}")
                await self.results_queue.put({"event": "error", "message": str(error)})
                
            async def on_close(self, **kwargs):
                logger.info("Deepgram stream closed.")
                await self.results_queue.put({"event": "close"})
                await self.results_queue.put(None)  # Sentinel to stop the generator loop
                
            dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
            dg_connection.on(LiveTranscriptionEvents.Error, on_error)
            dg_connection.on(LiveTranscriptionEvents.Close, on_close)
            
            await dg_connection.start(options)
            logger.info("Deepgram connection started.")
            
            # Task to send audio chunks to Deepgram
            send_audio_task = asyncio.create_task(self._send_audio_to_deepgram(dg_connection, audio_chunk_generator))
            
            # Main loop to yield results from the queue
            while True:
                result = await self.results_queue.get()
                if result is None:  # Sentinel received
                    break
                yield result
                
        except Exception as e:
            logger.error(f"Error in Deepgram process_audio_stream: {e}", exc_info=True)
            await self.results_queue.put({"event": "error", "message": f"Deepgram streaming failed: {e}"})
        finally:
            if dg_connection and dg_connection.get_state() == 1:
                await dg_connection.finish()
            if 'send_audio_task' in locals() and not send_audio_task.done():
                send_audio_task.cancel()
                try:
                    await send_audio_task
                except asyncio.CancelledError:
                    pass  # Task was intentionally cancelled
            logger.info("Deepgram stream handler cleaned up.")
            
    async def _send_audio_to_deepgram(self, dg_connection, audio_chunk_generator: AsyncGenerator[bytes, None]):
        """Internal helper to send audio chunks from a generator to Deepgram."""
        try:
            async for chunk in audio_chunk_generator:
                if dg_connection.get_state() == 1:  # Check if connection is open
                    await dg_connection.send(chunk)
                else:
                    logger.warning("Deepgram connection not open, stopping audio send.")
                    break
            logger.info("Finished sending audio chunks to Deepgram.")
        except asyncio.CancelledError:
            logger.info("Audio sending to Deepgram was cancelled.")
        except Exception as e:
            logger.error(f"Error sending audio to Deepgram: {e}", exc_info=True)
        finally:
            # Signal to the main generator that audio sending is done
            await self.results_queue.put({"event": "close"}) 