import numpy as np
import soundfile as sf
import logging
from typing import Tuple, Optional, Union
import io
import wave
import struct

logger = logging.getLogger(__name__)

class AudioProcessor:
    """
    Utility class for audio format conversion and processing.
    """
    def __init__(self):
        self.sample_rate = 16000  # Default sample rate
        self.channels = 1  # Default to mono
        self.dtype = np.float32  # Default data type
        logger.info("AudioProcessor initialized")

    def convert_to_wav(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_format: str = "raw",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None
    ) -> bytes:
        """
        Converts audio data to WAV format.
        Args:
            audio_data: Input audio data (bytes or numpy array)
            input_format: Format of input data ('raw', 'wav', 'mp3')
            sample_rate: Sample rate of input data (if None, uses default)
            channels: Number of channels (if None, uses default)
        Returns:
            bytes: WAV format audio data
        """
        try:
            if input_format == "raw":
                if isinstance(audio_data, bytes):
                    # Convert bytes to numpy array
                    audio_array = np.frombuffer(audio_data, dtype=self.dtype)
                else:
                    audio_array = audio_data

                # Reshape if stereo
                if channels == 2:
                    audio_array = audio_array.reshape(-1, 2)

                # Convert to WAV
                with io.BytesIO() as wav_buffer:
                    sf.write(
                        wav_buffer,
                        audio_array,
                        sample_rate or self.sample_rate,
                        format="WAV"
                    )
                    return wav_buffer.getvalue()

            elif input_format == "wav":
                # Already in WAV format
                return audio_data

            else:
                raise ValueError(f"Unsupported input format: {input_format}")

        except Exception as e:
            logger.error(f"Error converting audio to WAV: {e}")
            raise

    def convert_to_raw(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_format: str = "wav",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None
    ) -> bytes:
        """
        Converts audio data to raw PCM format.
        Args:
            audio_data: Input audio data (bytes or numpy array)
            input_format: Format of input data ('raw', 'wav', 'mp3')
            sample_rate: Sample rate of input data (if None, uses default)
            channels: Number of channels (if None, uses default)
        Returns:
            bytes: Raw PCM audio data
        """
        try:
            if input_format == "wav":
                if isinstance(audio_data, bytes):
                    # Read WAV file
                    with io.BytesIO(audio_data) as wav_buffer:
                        with wave.open(wav_buffer, 'rb') as wav_file:
                            audio_array = np.frombuffer(
                                wav_file.readframes(wav_file.getnframes()),
                                dtype=np.int16
                            )
                else:
                    audio_array = audio_data

                # Convert to float32
                audio_array = audio_array.astype(np.float32) / 32768.0

                # Reshape if stereo
                if channels == 2:
                    audio_array = audio_array.reshape(-1, 2)

                return audio_array.tobytes()

            elif input_format == "raw":
                # Already in raw format
                return audio_data

            else:
                raise ValueError(f"Unsupported input format: {input_format}")

        except Exception as e:
            logger.error(f"Error converting audio to raw: {e}")
            raise

    def resample_audio(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_format: str = "wav",
        target_sample_rate: int = 16000,
        input_sample_rate: Optional[int] = None
    ) -> bytes:
        """
        Resamples audio data to target sample rate.
        Args:
            audio_data: Input audio data (bytes or numpy array)
            input_format: Format of input data ('raw', 'wav', 'mp3')
            target_sample_rate: Target sample rate
            input_sample_rate: Input sample rate (if None, uses default)
        Returns:
            bytes: Resampled audio data in WAV format
        """
        try:
            # Convert to numpy array if needed
            if isinstance(audio_data, bytes):
                if input_format == "wav":
                    with io.BytesIO(audio_data) as wav_buffer:
                        with wave.open(wav_buffer, 'rb') as wav_file:
                            audio_array = np.frombuffer(
                                wav_file.readframes(wav_file.getnframes()),
                                dtype=np.int16
                            )
                            input_sample_rate = wav_file.getframerate()
                else:
                    audio_array = np.frombuffer(audio_data, dtype=self.dtype)
            else:
                audio_array = audio_data

            # Resample using scipy
            from scipy import signal
            if input_sample_rate != target_sample_rate:
                samples = len(audio_array)
                new_samples = int(samples * target_sample_rate / input_sample_rate)
                audio_array = signal.resample(audio_array, new_samples)

            # Convert to WAV
            with io.BytesIO() as wav_buffer:
                sf.write(
                    wav_buffer,
                    audio_array,
                    target_sample_rate,
                    format="WAV"
                )
                return wav_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error resampling audio: {e}")
            raise

    def normalize_audio(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_format: str = "wav",
        target_level: float = -3.0
    ) -> bytes:
        """
        Normalizes audio to target level in dB.
        Args:
            audio_data: Input audio data (bytes or numpy array)
            input_format: Format of input data ('raw', 'wav', 'mp3')
            target_level: Target level in dB
        Returns:
            bytes: Normalized audio data in WAV format
        """
        try:
            # Convert to numpy array if needed
            if isinstance(audio_data, bytes):
                if input_format == "wav":
                    with io.BytesIO(audio_data) as wav_buffer:
                        with wave.open(wav_buffer, 'rb') as wav_file:
                            audio_array = np.frombuffer(
                                wav_file.readframes(wav_file.getnframes()),
                                dtype=np.int16
                            )
                            sample_rate = wav_file.getframerate()
                else:
                    audio_array = np.frombuffer(audio_data, dtype=self.dtype)
                    sample_rate = self.sample_rate
            else:
                audio_array = audio_data
                sample_rate = self.sample_rate

            # Convert to float32
            audio_array = audio_array.astype(np.float32) / 32768.0

            # Calculate current level
            current_level = 20 * np.log10(np.max(np.abs(audio_array)))
            
            # Calculate gain
            gain = target_level - current_level
            
            # Apply gain
            audio_array = audio_array * (10 ** (gain / 20))
            
            # Clip to prevent overflow
            audio_array = np.clip(audio_array, -1.0, 1.0)

            # Convert back to WAV
            with io.BytesIO() as wav_buffer:
                sf.write(
                    wav_buffer,
                    audio_array,
                    sample_rate,
                    format="WAV"
                )
                return wav_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            raise

    def get_audio_info(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_format: str = "wav"
    ) -> dict:
        """
        Gets information about audio data.
        Args:
            audio_data: Input audio data (bytes or numpy array)
            input_format: Format of input data ('raw', 'wav', 'mp3')
        Returns:
            dict: Audio information including duration, sample rate, etc.
        """
        try:
            if isinstance(audio_data, bytes):
                if input_format == "wav":
                    with io.BytesIO(audio_data) as wav_buffer:
                        with wave.open(wav_buffer, 'rb') as wav_file:
                            channels = wav_file.getnchannels()
                            sample_rate = wav_file.getframerate()
                            sample_width = wav_file.getsampwidth()
                            frames = wav_file.getnframes()
                            duration = frames / sample_rate
                else:
                    # For raw data, use default values
                    channels = self.channels
                    sample_rate = self.sample_rate
                    sample_width = 2  # 16-bit
                    frames = len(audio_data) // (channels * sample_width)
                    duration = frames / sample_rate
            else:
                # For numpy array
                channels = 1 if len(audio_data.shape) == 1 else audio_data.shape[1]
                sample_rate = self.sample_rate
                sample_width = 2  # 16-bit
                frames = len(audio_data)
                duration = frames / sample_rate

            return {
                "channels": channels,
                "sample_rate": sample_rate,
                "sample_width": sample_width,
                "frames": frames,
                "duration": duration
            }

        except Exception as e:
            logger.error(f"Error getting audio info: {e}")
            raise 