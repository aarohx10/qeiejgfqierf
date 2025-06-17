import asyncio
import logging
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    """
    def __init__(self):
        # Active connections
        self.active_connections: Dict[str, WebSocket] = {}
        # Connection metadata
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        # Connection groups
        self.groups: Dict[str, Set[str]] = {}
        logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, client_id: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Accepts a new WebSocket connection.
        Args:
            websocket: WebSocket connection
            client_id: Unique identifier for the client
            metadata: Additional metadata for the connection
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_metadata[client_id] = {
            "connected_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            **(metadata or {})
        }
        logger.info(f"Client {client_id} connected")

    async def disconnect(self, client_id: str):
        """
        Closes a WebSocket connection.
        Args:
            client_id: ID of the client to disconnect
        """
        if client_id in self.active_connections:
            # Remove from all groups
            for group_id, members in self.groups.items():
                if client_id in members:
                    members.remove(client_id)
                    if not members:
                        del self.groups[group_id]
            
            # Close connection
            await self.active_connections[client_id].close()
            del self.active_connections[client_id]
            del self.connection_metadata[client_id]
            logger.info(f"Client {client_id} disconnected")

    async def send_personal_message(self, message: Any, client_id: str):
        """
        Sends a message to a specific client.
        Args:
            message: Message to send
            client_id: ID of the target client
        """
        if client_id in self.active_connections:
            try:
                if isinstance(message, (dict, list)):
                    message = json.dumps(message)
                await self.active_connections[client_id].send_text(message)
                self.connection_metadata[client_id]["last_activity"] = datetime.utcnow().isoformat()
            except Exception as e:
                logger.error(f"Error sending message to client {client_id}: {e}")
                await self.disconnect(client_id)

    async def broadcast(self, message: Any, exclude: Optional[Set[str]] = None):
        """
        Broadcasts a message to all connected clients.
        Args:
            message: Message to broadcast
            exclude: Set of client IDs to exclude
        """
        if isinstance(message, (dict, list)):
            message = json.dumps(message)
        
        for client_id, connection in self.active_connections.items():
            if exclude and client_id in exclude:
                continue
            try:
                await connection.send_text(message)
                self.connection_metadata[client_id]["last_activity"] = datetime.utcnow().isoformat()
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                await self.disconnect(client_id)

    async def broadcast_to_group(self, group_id: str, message: Any, exclude: Optional[Set[str]] = None):
        """
        Broadcasts a message to all clients in a group.
        Args:
            group_id: ID of the target group
            message: Message to broadcast
            exclude: Set of client IDs to exclude
        """
        if group_id not in self.groups:
            return
        
        if isinstance(message, (dict, list)):
            message = json.dumps(message)
        
        for client_id in self.groups[group_id]:
            if exclude and client_id in exclude:
                continue
            try:
                await self.active_connections[client_id].send_text(message)
                self.connection_metadata[client_id]["last_activity"] = datetime.utcnow().isoformat()
            except Exception as e:
                logger.error(f"Error broadcasting to group {group_id} client {client_id}: {e}")
                await self.disconnect(client_id)

    def add_to_group(self, client_id: str, group_id: str):
        """
        Adds a client to a group.
        Args:
            client_id: ID of the client to add
            group_id: ID of the target group
        """
        if client_id not in self.active_connections:
            return
        
        if group_id not in self.groups:
            self.groups[group_id] = set()
        
        self.groups[group_id].add(client_id)
        logger.info(f"Client {client_id} added to group {group_id}")

    def remove_from_group(self, client_id: str, group_id: str):
        """
        Removes a client from a group.
        Args:
            client_id: ID of the client to remove
            group_id: ID of the target group
        """
        if group_id in self.groups and client_id in self.groups[group_id]:
            self.groups[group_id].remove(client_id)
            if not self.groups[group_id]:
                del self.groups[group_id]
            logger.info(f"Client {client_id} removed from group {group_id}")

    def get_client_metadata(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets metadata for a specific client.
        Args:
            client_id: ID of the client
        Returns:
            Optional[Dict]: Client metadata if available
        """
        return self.connection_metadata.get(client_id)

    def get_group_members(self, group_id: str) -> Set[str]:
        """
        Gets all members of a group.
        Args:
            group_id: ID of the group
        Returns:
            Set[str]: Set of client IDs in the group
        """
        return self.groups.get(group_id, set())

    def get_active_connections(self) -> Dict[str, Dict[str, Any]]:
        """
        Gets information about all active connections.
        Returns:
            Dict: Dictionary of client IDs and their metadata
        """
        return {
            client_id: {
                "metadata": metadata,
                "groups": [
                    group_id
                    for group_id, members in self.groups.items()
                    if client_id in members
                ]
            }
            for client_id, metadata in self.connection_metadata.items()
        } 