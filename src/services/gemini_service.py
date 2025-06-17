import logging
import structlog
from typing import Dict, Any, Optional, List
import google.generativeai as genai
from src.config import GEMINI_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

class GeminiService:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        """Initialize Gemini service.
        
        Args:
            api_key: Gemini API key
        """
        self._client = genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel('gemini-pro')
        logger.info("Gemini service initialized")

    async def connect(self):
        """Connect to Gemini service."""
        try:
            # Test connection with a simple prompt
            response = await self._model.generate_content_async("Test connection")
            logger.info("Successfully connected to Gemini")
        except Exception as e:
            logger.error(f"Error connecting to Gemini: {e}", exc_info=True)
            raise
            
    async def disconnect(self):
        """Disconnect from Gemini service."""
        try:
            # No explicit disconnect needed for Gemini
            logger.info("Successfully disconnected from Gemini")
        except Exception as e:
            logger.error(f"Error disconnecting from Gemini: {e}", exc_info=True)
            
    async def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None, call_id: Optional[str] = None) -> Optional[str]:
        """
        Generate a response using Gemini.
        
        Args:
            prompt: The user's input prompt
            context: Optional conversation context
            call_id: Optional call ID for logging
            
        Returns:
            Generated response text or None if generation fails
        """
        try:
            # Prepare context if available
            if context:
                full_prompt = f"Context: {context}\nUser: {prompt}"
            else:
                full_prompt = prompt
                
            # Generate response
            response = await self._model.generate_content_async(full_prompt)
            return response.text
            
        except genai.types.BlockedPromptException as e:
            logger.error(f"Gemini prompt blocked for call {call_id}: {e}")
            return "I'm sorry, I cannot process that request due to content policy. Can I help with something else?"
            
        except genai.types.StopCandidateException as e:
            logger.error(f"Gemini stop candidate exception for call {call_id}: {e}")
            return "I'm sorry, I'm having trouble understanding. Could you please rephrase?"
            
        except Exception as e:
            logger.error(f"Error generating Gemini response for call {call_id}: {e}", exc_info=True)
            return "I apologize, I encountered an internal error with my brain. Please try again later."

    async def start_chat(
        self,
        system_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Any:
        """Start a new chat session.
        
        Args:
            system_prompt: System prompt to set context
            conversation_history: Optional conversation history
            
        Returns:
            Chat session
        """
        try:
            chat = self._model.start_chat(history=conversation_history or [])
            if system_prompt:
                await chat.send_message(system_prompt)
            return chat
        except Exception as e:
            logger.error(f"Failed to start chat: {e}", exc_info=True)
            raise

    async def send_message(
        self,
        chat: Any,
        message: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Send a message to the chat.
        
        Args:
            chat: Chat session
            message: Message to send
            temperature: Response temperature (0-1)
            max_tokens: Maximum tokens in response
            
        Returns:
            Response from Gemini
        """
        try:
            response = await chat.send_message(
                message,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )
            return {
                "text": response.text,
                "candidates": [
                    {
                        "text": candidate.text,
                        "safety_ratings": [
                            {
                                "category": rating.category,
                                "probability": rating.probability
                            }
                            for rating in candidate.safety_ratings
                        ]
                    }
                    for candidate in response.candidates
                ]
            }
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            raise

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate text from a prompt.
        
        Args:
            prompt: Text prompt
            temperature: Response temperature (0-1)
            max_tokens: Maximum tokens in response
            
        Returns:
            Generated text
        """
        try:
            response = await self._model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"Failed to generate text: {e}", exc_info=True)
            raise 