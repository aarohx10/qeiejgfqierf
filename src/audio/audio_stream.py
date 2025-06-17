import asyncio
import logging
from typing import Optional, Callable, Dict, Any
import numpy as np
from .audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

class AudioStream:
    """
    Handles streaming of audio data with buffering and processing capabilities.
    """
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        buffer_size: int = 8192,
        processor: Optional[AudioProcessor] = None
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size
        self.processor = processor or AudioProcessor()
        
        # Initialize buffers
        self.input_buffer = asyncio.Queue(maxsize=buffer_size)
        self.output_buffer = asyncio.Queue(maxsize=buffer_size)
        
        # Stream state
        self.is_running = False
        self.is_processing = False
        self.total_samples = 0
        
        logger.info(f"AudioStream initialized with sample_rate={sample_rate}, channels={channels}")

    async def start(self):
        """Starts the audio stream processing."""
        if self.is_running:
            return
        
        self.is_running = True
        self.is_processing = True
        
        # Start processing tasks
        self.process_task = asyncio.create_task(self._process_stream())
        logger.info("AudioStream started")

    async def stop(self):
        """Stops the audio stream processing."""
        if not self.is_running:
            return
        
        self.is_running = False
        self.is_processing = False
        
        # Cancel processing task
        if hasattr(self, 'process_task'):
            self.process_task.cancel()
            try:
                await self.process_task
            except asyncio.CancelledError:
                pass
        
        # Clear buffers
        while not self.input_buffer.empty():
            self.input_buffer.get_nowait()
        while not self.output_buffer.empty():
            self.output_buffer.get_nowait()
        
        logger.info("AudioStream stopped")

    async def write(self, data: bytes):
        """
        Writes audio data to the input buffer.
        Args:
            data: Raw audio data to write
        """
        if not self.is_running:
            raise RuntimeError("AudioStream is not running")
        
        try:
            await self.input_buffer.put(data)
            self.total_samples += len(data) // (self.channels * 2)  # 2 bytes per sample
        except asyncio.QueueFull:
            logger.warning("Input buffer is full, dropping data")
            raise

    async def read(self) -> bytes:
        """
        Reads processed audio data from the output buffer.
        Returns:
            bytes: Processed audio data
        """
        if not self.is_running:
            raise RuntimeError("AudioStream is not running")
        
        try:
            return await self.output_buffer.get()
        except asyncio.QueueEmpty:
            logger.warning("Output buffer is empty")
            raise

    async def _process_stream(self):
        """Internal method to process the audio stream."""
        try:
            while self.is_processing:
                # Get data from input buffer
                try:
                    data = await asyncio.wait_for(
                        self.input_buffer.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process the data
                try:
                    # Convert to WAV for processing
                    wav_data = self.processor.convert_to_wav(
                        data,
                        input_format="raw",
                        sample_rate=self.sample_rate,
                        channels=self.channels
                    )
                    
                    # Normalize audio
                    normalized_data = self.processor.normalize_audio(
                        wav_data,
                        input_format="wav"
                    )
                    
                    # Put processed data in output buffer
                    await self.output_buffer.put(normalized_data)
                    
                except Exception as e:
                    logger.error(f"Error processing audio data: {e}")
                    continue
                
                finally:
                    self.input_buffer.task_done()
        
        except asyncio.CancelledError:
            logger.info("Audio stream processing cancelled")
        except Exception as e:
            logger.error(f"Error in audio stream processing: {e}")
        finally:
            self.is_processing = False

    async def apply_effect(
        self,
        effect_func: Callable[[bytes], bytes],
        effect_params: Optional[Dict[str, Any]] = None
    ):
        """
        Applies an effect to the audio stream.
        Args:
            effect_func: Function to apply the effect
            effect_params: Parameters for the effect function
        """
        if not self.is_running:
            raise RuntimeError("AudioStream is not running")
        
        try:
            # Get data from input buffer
            data = await self.input_buffer.get()
            
            # Apply effect
            processed_data = effect_func(data, **(effect_params or {}))
            
            # Put processed data in output buffer
            await self.output_buffer.put(processed_data)
            
        except Exception as e:
            logger.error(f"Error applying effect: {e}")
            raise
        finally:
            self.input_buffer.task_done()

    def get_stats(self) -> Dict[str, Any]:
        """
        Gets statistics about the audio stream.
        Returns:
            dict: Stream statistics
        """
        return {
            "is_running": self.is_running,
            "is_processing": self.is_processing,
            "input_buffer_size": self.input_buffer.qsize(),
            "output_buffer_size": self.output_buffer.qsize(),
            "total_samples": self.total_samples,
            "total_duration": self.total_samples / self.sample_rate
        } 