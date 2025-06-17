import asyncio
import logging
import structlog
import numpy as np
from typing import Optional, List, Dict, Any, AsyncGenerator
import soundfile as sf
from scipy import signal
import webrtcvad
from src.config import (
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    AUDIO_FORMAT,
    VAD_FRAME_DURATION_MS,
    VAD_MODE
)

logger = structlog.get_logger()

class AudioProcessor:
    def __init__(self):
        """Initialize audio processor with VAD."""
        self.vad = webrtcvad.Vad(VAD_MODE)
        self.sample_rate = AUDIO_SAMPLE_RATE
        self.channels = AUDIO_CHANNELS
        self.frame_duration_ms = VAD_FRAME_DURATION_MS
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        
    async def process_audio_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        vad_threshold: float = 0.5,
        silence_threshold: float = 0.1,
        min_speech_duration: float = 0.5,
        max_speech_duration: float = 10.0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process audio stream with VAD and return speech segments.
        
        Args:
            audio_stream: Async generator yielding audio chunks
            vad_threshold: VAD threshold (0-1)
            silence_threshold: Silence threshold (0-1)
            min_speech_duration: Minimum speech duration in seconds
            max_speech_duration: Maximum speech duration in seconds
        """
        buffer = bytearray()
        is_speaking = False
        speech_start = None
        silence_frames = 0
        required_silence_frames = int(0.5 * self.sample_rate / self.frame_size)  # 0.5s of silence
        
        try:
            async for chunk in audio_stream:
                buffer.extend(chunk)
                
                # Process complete frames
                while len(buffer) >= self.frame_size * 2:  # 2 bytes per sample
                    frame = buffer[:self.frame_size * 2]
                    buffer = buffer[self.frame_size * 2:]
                    
                    # Check if frame contains speech
                    try:
                        is_speech = self.vad.is_speech(frame, self.sample_rate)
                    except Exception as e:
                        logger.error("vad_processing_error", error=str(e), exc_info=True)
                        continue
                    
                    if is_speech and not is_speaking:
                        # Speech started
                        is_speaking = True
                        speech_start = len(buffer) - self.frame_size * 2
                        silence_frames = 0
                    elif not is_speech and is_speaking:
                        silence_frames += 1
                        if silence_frames >= required_silence_frames:
                            # Speech ended
                            is_speaking = False
                            speech_end = len(buffer) - (silence_frames * self.frame_size * 2)
                            
                            # Extract speech segment
                            speech_segment = buffer[speech_start:speech_end]
                            duration = len(speech_segment) / (self.sample_rate * 2)  # 2 bytes per sample
                            
                            if min_speech_duration <= duration <= max_speech_duration:
                                yield {
                                    "audio": bytes(speech_segment),
                                    "duration": duration,
                                    "start_time": speech_start / (self.sample_rate * 2),
                                    "end_time": speech_end / (self.sample_rate * 2)
                                }
                            
                            # Clear processed speech
                            buffer = buffer[speech_end:]
                            speech_start = None
                            silence_frames = 0
                    
        except Exception as e:
            logger.error("audio_processing_error", error=str(e), exc_info=True)
            raise
    
    async def normalize_audio(self, audio_data: bytes) -> bytes:
        """
        Normalize audio data to ensure consistent volume levels.
        
        Args:
            audio_data: Raw audio data
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize to float between -1 and 1
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Apply normalization
            max_value = np.max(np.abs(audio_float))
            if max_value > 0:
                normalized = audio_float / max_value
            else:
                normalized = audio_float
            
            # Convert back to int16
            normalized_int16 = (normalized * 32767).astype(np.int16)
            
            return normalized_int16.tobytes()
        except Exception as e:
            logger.error("audio_normalization_error", error=str(e), exc_info=True)
            raise
    
    async def resample_audio(
        self,
        audio_data: bytes,
        target_sample_rate: int = AUDIO_SAMPLE_RATE
    ) -> bytes:
        """
        Resample audio data to target sample rate.
        
        Args:
            audio_data: Raw audio data
            target_sample_rate: Target sample rate
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Resample
            number_of_samples = round(len(audio_array) * target_sample_rate / self.sample_rate)
            resampled = signal.resample(audio_array, number_of_samples)
            
            # Convert back to int16
            resampled_int16 = (resampled * 32767).astype(np.int16)
            
            return resampled_int16.tobytes()
        except Exception as e:
            logger.error("audio_resampling_error", error=str(e), exc_info=True)
            raise
    
    async def save_audio(
        self,
        audio_data: bytes,
        filepath: str,
        format: str = AUDIO_FORMAT
    ) -> None:
        """
        Save audio data to file.
        
        Args:
            audio_data: Raw audio data
            filepath: Output file path
            format: Audio format
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Save to file
            sf.write(
                filepath,
                audio_array,
                self.sample_rate,
                format=format
            )
        except Exception as e:
            logger.error(
                "audio_save_error",
                filepath=filepath,
                format=format,
                error=str(e),
                exc_info=True
            )
            raise
    
    async def load_audio(
        self,
        filepath: str,
        target_sample_rate: Optional[int] = None
    ) -> bytes:
        """
        Load audio from file.
        
        Args:
            filepath: Input file path
            target_sample_rate: Optional target sample rate for resampling
        """
        try:
            # Load audio file
            audio_array, sample_rate = sf.read(filepath)
            
            # Convert to int16
            audio_int16 = (audio_array * 32767).astype(np.int16)
            
            # Resample if needed
            if target_sample_rate and target_sample_rate != sample_rate:
                number_of_samples = round(len(audio_int16) * target_sample_rate / sample_rate)
                resampled = signal.resample(audio_int16, number_of_samples)
                audio_int16 = (resampled * 32767).astype(np.int16)
            
            return audio_int16.tobytes()
        except Exception as e:
            logger.error(
                "audio_load_error",
                filepath=filepath,
                error=str(e),
                exc_info=True
            )
            raise 