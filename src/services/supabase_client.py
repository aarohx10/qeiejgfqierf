from supabase import create_client, Client
from typing import Dict, Any, Optional, List
import structlog
import os
from datetime import datetime
import uuid

logger = structlog.get_logger(__name__)

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.client: Optional[Client] = None
        self._connect()

    def _connect(self):
        """Connect to Supabase."""
        try:
            self.client = create_client(self.url, self.key)
            logger.info("Connected to Supabase")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}", exc_info=True)
            raise

    # API Key Management
    async def create_api_key(self, user_id: str, name: str) -> Dict[str, Any]:
        """Create a new API key for a user."""
        try:
            api_key = str(uuid.uuid4())
            data = {
                "user_id": user_id,
                "name": name,
                "key": api_key,
                "created_at": datetime.utcnow().isoformat(),
                "last_used": None
            }
            
            result = await self.client.table("api_keys").insert(data).execute()
            if not result.data:
                raise Exception("Failed to create API key")
                
            return result.data[0]
        except Exception as e:
            logger.error(f"Error creating API key: {e}", exc_info=True)
            raise

    async def get_api_key_user(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get user data associated with an API key."""
        try:
            result = await self.client.table("api_keys").select(
                "*, users(*)"
            ).eq("key", api_key).single().execute()
            
            if not result.data:
                return None
                
            # Update last used timestamp
            await self.client.table("api_keys").update({
                "last_used": datetime.utcnow().isoformat()
            }).eq("key", api_key).execute()
            
            return result.data["users"]
        except Exception as e:
            logger.error(f"Error getting API key user: {e}", exc_info=True)
            return None

    async def list_api_keys(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List API keys, optionally filtered by user."""
        try:
            query = self.client.table("api_keys").select("*")
            if user_id:
                query = query.eq("user_id", user_id)
                
            result = await query.execute()
            return result.data
        except Exception as e:
            logger.error(f"Error listing API keys: {e}", exc_info=True)
            return []

    async def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key."""
        try:
            result = await self.client.table("api_keys").delete().eq("key", api_key).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error revoking API key: {e}", exc_info=True)
            return False

    # AI Agent Management
    async def create_ai_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new AI agent."""
        try:
            result = await self.client.table("ai_agents").insert(agent_data).execute()
            if not result.data:
                raise Exception("Failed to create AI agent")
            return result.data[0]
        except Exception as e:
            logger.error(f"Error creating AI agent: {e}", exc_info=True)
            raise

    async def get_ai_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get AI agent details."""
        try:
            result = await self.client.table("ai_agents").select("*").eq("id", agent_id).single().execute()
            return result.data
        except Exception as e:
            logger.error(f"Error getting AI agent: {e}", exc_info=True)
            return None

    async def list_ai_agents(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        """List AI agents, optionally filtered by enabled status."""
        try:
            query = self.client.table("ai_agents").select("*")
            if enabled is not None:
                query = query.eq("enabled", enabled)
            result = await query.execute()
            return result.data
        except Exception as e:
            logger.error(f"Error listing AI agents: {e}", exc_info=True)
            return []

    async def update_ai_agent(self, agent_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update AI agent details."""
        try:
            result = await self.client.table("ai_agents").update(updates).eq("id", agent_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating AI agent: {e}", exc_info=True)
            return None

    async def delete_ai_agent(self, agent_id: str) -> bool:
        """Delete an AI agent."""
        try:
            result = await self.client.table("ai_agents").delete().eq("id", agent_id).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error deleting AI agent: {e}", exc_info=True)
            return False

    # Call Management
    async def create_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new call record."""
        try:
            result = await self.client.table("calls").insert(call_data).execute()
            if not result.data:
                raise Exception("Failed to create call record")
            return result.data[0]
        except Exception as e:
            logger.error(f"Error creating call: {e}", exc_info=True)
            raise

    async def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call details."""
        try:
            result = await self.client.table("calls").select("*").eq("id", call_id).single().execute()
            return result.data
        except Exception as e:
            logger.error(f"Error getting call: {e}", exc_info=True)
            return None

    async def list_calls(self,
                        limit: int = 10,
                        offset: int = 0,
                        status_filter: Optional[str] = None,
                        ai_agent_id_filter: Optional[str] = None,
                        from_number_filter: Optional[str] = None,
                        to_number_filter: Optional[str] = None,
                        order_by: str = 'created_at',
                        order_direction: str = 'desc'
                       ) -> List[Dict]:
        """
        Retrieves a list of call records with optional filtering, pagination, and ordering.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            status_filter: Filter by call status
            ai_agent_id_filter: Filter by AI agent ID
            from_number_filter: Filter by from number
            to_number_filter: Filter by to number
            order_by: Field to order by
            order_direction: Order direction ('asc' or 'desc')
            
        Returns:
            List of call records matching the criteria
        """
        params = {
            'limit': limit,
            'offset': offset,
            'order': f'{order_by}.{order_direction}'
        }
        
        if status_filter:
            params['status'] = f'eq.{status_filter}'
        if ai_agent_id_filter:
            params['ai_agent_id'] = f'eq.{ai_agent_id_filter}'
        if from_number_filter:
            params['from_number'] = f'eq.{from_number_filter}'
        if to_number_filter:
            params['to_number'] = f'eq.{to_number_filter}'
            
        try:
            response = await self._make_request('GET', 'calls', params=params)
            return response
        except Exception as e:
            logger.error(f"Error listing calls from Supabase: {e}", exc_info=True)
            raise

    async def update_call(self, call_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update call details."""
        try:
            result = await self.client.table("calls").update(updates).eq("id", call_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating call: {e}", exc_info=True)
            return None

    # User Management
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user details."""
        try:
            result = await self.client.table("users").select("*").eq("id", user_id).single().execute()
            return result.data
        except Exception as e:
            logger.error(f"Error getting user: {e}", exc_info=True)
            return None

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user details."""
        try:
            result = await self.client.table("users").update(updates).eq("id", user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating user: {e}", exc_info=True)
            return None

    # System Configuration
    async def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration."""
        try:
            result = await self.client.table("system_config").select("*").single().execute()
            return result.data or {}
        except Exception as e:
            logger.error(f"Error getting system config: {e}", exc_info=True)
            return {}

    async def update_system_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update system configuration."""
        try:
            result = await self.client.table("system_config").upsert(config).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error updating system config: {e}", exc_info=True)
            return {} 