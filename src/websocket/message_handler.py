import logging
from typing import Dict, Any, Optional, Callable, Awaitable
import json
from .connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class MessageHandler:
    """
    Handles WebSocket messages and routes them to appropriate handlers.
    """
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.message_handlers: Dict[str, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {}
        self.error_handlers: Dict[str, Callable[[str, Exception], Awaitable[None]]] = {}
        logger.info("MessageHandler initialized")

    def register_handler(
        self,
        message_type: str,
        handler: Callable[[str, Dict[str, Any]], Awaitable[None]]
    ):
        """
        Registers a handler for a specific message type.
        Args:
            message_type: Type of message to handle
            handler: Async function to handle the message
        """
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")

    def register_error_handler(
        self,
        error_type: str,
        handler: Callable[[str, Exception], Awaitable[None]]
    ):
        """
        Registers a handler for a specific error type.
        Args:
            error_type: Type of error to handle
            handler: Async function to handle the error
        """
        self.error_handlers[error_type] = handler
        logger.info(f"Registered error handler for type: {error_type}")

    async def handle_message(self, client_id: str, message: str):
        """
        Handles an incoming WebSocket message.
        Args:
            client_id: ID of the client sending the message
            message: Raw message string
        """
        try:
            # Parse message
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON message from client {client_id}")
                await self._handle_error(client_id, "invalid_message", ValueError("Invalid JSON message"))
                return

            # Validate message format
            if not isinstance(data, dict) or "type" not in data:
                logger.error(f"Invalid message format from client {client_id}")
                await self._handle_error(client_id, "invalid_format", ValueError("Invalid message format"))
                return

            message_type = data["type"]
            message_data = data.get("data", {})

            # Route to appropriate handler
            if message_type in self.message_handlers:
                try:
                    await self.message_handlers[message_type](client_id, message_data)
                except Exception as e:
                    logger.error(f"Error handling message type {message_type} from client {client_id}: {e}")
                    await self._handle_error(client_id, "handler_error", e)
            else:
                logger.warning(f"No handler registered for message type: {message_type}")
                await self._handle_error(client_id, "unknown_type", ValueError(f"Unknown message type: {message_type}"))

        except Exception as e:
            logger.error(f"Unexpected error handling message from client {client_id}: {e}")
            await self._handle_error(client_id, "unexpected_error", e)

    async def _handle_error(self, client_id: str, error_type: str, error: Exception):
        """
        Handles an error that occurred during message processing.
        Args:
            client_id: ID of the client that caused the error
            error_type: Type of error that occurred
            error: Exception that was raised
        """
        try:
            # Send error message to client
            error_message = {
                "type": "error",
                "data": {
                    "error_type": error_type,
                    "message": str(error)
                }
            }
            await self.connection_manager.send_personal_message(error_message, client_id)

            # Call error handler if registered
            if error_type in self.error_handlers:
                await self.error_handlers[error_type](client_id, error)

        except Exception as e:
            logger.error(f"Error handling error for client {client_id}: {e}")

    async def send_message(
        self,
        client_id: str,
        message_type: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Sends a message to a specific client.
        Args:
            client_id: ID of the target client
            message_type: Type of message to send
            data: Optional message data
        """
        try:
            message = {
                "type": message_type,
                "data": data or {}
            }
            await self.connection_manager.send_personal_message(message, client_id)
        except Exception as e:
            logger.error(f"Error sending message to client {client_id}: {e}")
            await self._handle_error(client_id, "send_error", e)

    async def broadcast_message(
        self,
        message_type: str,
        data: Optional[Dict[str, Any]] = None,
        exclude: Optional[set] = None
    ):
        """
        Broadcasts a message to all connected clients.
        Args:
            message_type: Type of message to broadcast
            data: Optional message data
            exclude: Set of client IDs to exclude
        """
        try:
            message = {
                "type": message_type,
                "data": data or {}
            }
            await self.connection_manager.broadcast(message, exclude)
        except Exception as e:
            logger.error(f"Error broadcasting message: {e}")

    async def broadcast_to_group(
        self,
        group_id: str,
        message_type: str,
        data: Optional[Dict[str, Any]] = None,
        exclude: Optional[set] = None
    ):
        """
        Broadcasts a message to all clients in a group.
        Args:
            group_id: ID of the target group
            message_type: Type of message to broadcast
            data: Optional message data
            exclude: Set of client IDs to exclude
        """
        try:
            message = {
                "type": message_type,
                "data": data or {}
            }
            await self.connection_manager.broadcast_to_group(group_id, message, exclude)
        except Exception as e:
            logger.error(f"Error broadcasting to group {group_id}: {e}") 