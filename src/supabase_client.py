import os
import logging
import httpx
from typing import Dict, List, Optional, Any, Union
import json
import backoff  # Import here to avoid circular imports
import structlog
from datetime import datetime, timezone
from supabase import create_client, Client

import config
from src.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_ANON_KEY,
    HTTP_TIMEOUT
)

logger = structlog.get_logger(__name__)

class SupabaseClient:
    """Client for interacting with Supabase database."""
    
    def __init__(self, url: str, key: str):
        """Initialize Supabase client."""
        self._url = url
        self._key = key
        self._client: Optional[Client] = None
        logger.info("Supabase client initialized")

    async def connect(self) -> None:
        """Connect to Supabase."""
        try:
            self._client = create_client(self._url, self._key)
            logger.info("Connected to Supabase")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from Supabase."""
        self._client = None
        logger.info("Disconnected from Supabase")

    def _ensure_connection(self) -> None:
        """Ensure client is connected."""
        if not self._client:
            raise RuntimeError("Supabase client not connected")

    # AI Agents
    async def create_ai_agent(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new AI agent."""
        self._ensure_connection()
        try:
            result = self._client.table("ai_agents").insert(data).execute()
            logger.info(f"Created AI agent: {result.data[0]['id']}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create AI agent: {e}", exc_info=True)
            raise

    async def get_ai_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get AI agent by ID."""
        self._ensure_connection()
        try:
            result = self._client.table("ai_agents").select("*").eq("id", agent_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get AI agent {agent_id}: {e}", exc_info=True)
            raise

    async def update_ai_agent(self, agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update AI agent."""
        self._ensure_connection()
        try:
            result = self._client.table("ai_agents").update(data).eq("id", agent_id).execute()
            logger.info(f"Updated AI agent: {agent_id}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to update AI agent {agent_id}: {e}", exc_info=True)
            raise

    async def delete_ai_agent(self, agent_id: str) -> None:
        """Delete AI agent."""
        self._ensure_connection()
        try:
            self._client.table("ai_agents").delete().eq("id", agent_id).execute()
            logger.info(f"Deleted AI agent: {agent_id}")
        except Exception as e:
            logger.error(f"Failed to delete AI agent {agent_id}: {e}", exc_info=True)
            raise

    # Call Records
    async def create_call_record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new call record."""
        self._ensure_connection()
        try:
            result = self._client.table("calls").insert(data).execute()
            logger.info(f"Created call record: {result.data[0]['id']}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create call record: {e}", exc_info=True)
            raise

    async def get_call_record(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call record by ID."""
        self._ensure_connection()
        try:
            result = self._client.table("calls").select("*").eq("id", call_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get call record {call_id}: {e}", exc_info=True)
            raise

    async def update_call_record(self, call_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update call record."""
        self._ensure_connection()
        try:
            result = self._client.table("calls").update(data).eq("id", call_id).execute()
            logger.info(f"Updated call record: {call_id}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to update call record {call_id}: {e}", exc_info=True)
            raise

    # Call Segments
    async def create_call_segment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new call segment."""
        self._ensure_connection()
        try:
            result = self._client.table("call_segments").insert(data).execute()
            logger.info(f"Created call segment: {result.data[0]['id']}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create call segment: {e}", exc_info=True)
            raise

    async def get_call_segments(self, call_id: str) -> List[Dict[str, Any]]:
        """Get all segments for a call."""
        self._ensure_connection()
        try:
            result = self._client.table("call_segments").select("*").eq("call_id", call_id).order("sequence_number").execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to get call segments for {call_id}: {e}", exc_info=True)
            raise

    # Phone Numbers
    async def get_phone_number(self, number_id: str) -> Optional[Dict[str, Any]]:
        """Get phone number by ID."""
        self._ensure_connection()
        try:
            result = self._client.table("phone_numbers").select("*").eq("id", number_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get phone number {number_id}: {e}", exc_info=True)
            raise

    async def list_phone_numbers(self, user_id: str) -> List[Dict[str, Any]]:
        """List phone numbers for a user."""
        self._ensure_connection()
        try:
            result = self._client.table("phone_numbers").select("*").eq("user_id", user_id).execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to list phone numbers for user {user_id}: {e}", exc_info=True)
            raise

    # SIP Trunks
    async def create_sip_trunk(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new SIP trunk."""
        self._ensure_connection()
        try:
            result = self._client.table("sip_trunks").insert(data).execute()
            logger.info(f"Created SIP trunk: {result.data[0]['id']}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create SIP trunk: {e}", exc_info=True)
            raise

    async def get_sip_trunk(self, trunk_id: str) -> Optional[Dict[str, Any]]:
        """Get SIP trunk by ID."""
        self._ensure_connection()
        try:
            result = self._client.table("sip_trunks").select("*").eq("id", trunk_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get SIP trunk {trunk_id}: {e}", exc_info=True)
            raise

    async def update_sip_trunk(self, trunk_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update SIP trunk."""
        self._ensure_connection()
        try:
            result = self._client.table("sip_trunks").update(data).eq("id", trunk_id).execute()
            logger.info(f"Updated SIP trunk: {trunk_id}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to update SIP trunk {trunk_id}: {e}", exc_info=True)
            raise

    async def delete_sip_trunk(self, trunk_id: str) -> None:
        """Delete SIP trunk."""
        self._ensure_connection()
        try:
            self._client.table("sip_trunks").delete().eq("id", trunk_id).execute()
            logger.info(f"Deleted SIP trunk: {trunk_id}")
        except Exception as e:
            logger.error(f"Failed to delete SIP trunk {trunk_id}: {e}", exc_info=True)
            raise

    # Cal.com Integrations
    async def create_cal_com_integration(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Cal.com integration."""
        self._ensure_connection()
        try:
            result = self._client.table("cal_com_integrations").insert(data).execute()
            logger.info(f"Created Cal.com integration: {result.data[0]['id']}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create Cal.com integration: {e}", exc_info=True)
            raise

    async def get_cal_com_integration(self, integration_id: str) -> Optional[Dict[str, Any]]:
        """Get Cal.com integration by ID."""
        self._ensure_connection()
        try:
            result = self._client.table("cal_com_integrations").select("*").eq("id", integration_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get Cal.com integration {integration_id}: {e}", exc_info=True)
            raise

    # Health Checks
    async def create_health_check(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new health check record."""
        self._ensure_connection()
        try:
            result = self._client.table("health_check").insert(data).execute()
            logger.info(f"Created health check: {result.data[0]['id']}")
            return result.data[0]
        except Exception as e:
            logger.error(f"Failed to create health check: {e}", exc_info=True)
            raise

    # Generic List Records Method
    async def list_records(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generic method to list records from any table with filtering and pagination."""
        self._ensure_connection()
        try:
            query = self._client.table(table).select("*")
            
            # Apply filters
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            # Apply ordering
            if order_by:
                query = query.order(order_by)
            
            # Apply pagination
            if limit:
                query = query.limit(limit)
            if offset:
                query = query.offset(offset)
            
            result = query.execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to list records from {table}: {e}", exc_info=True)
            raise

    async def create_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new AI agent.
        
        Args:
            agent_data: Agent data including name, description, etc.
            
        Returns:
            Created agent data
        """
        try:
            response = await self._client.table("agents").insert(agent_data).execute()
            return response.data[0]
        except Exception as e:
            logger.error(f"Failed to create agent: {e}", exc_info=True)
            raise

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent data if found, None otherwise
        """
        try:
            response = await self._client.table("agents").select("*").eq("id", agent_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}", exc_info=True)
            raise

    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents.
        
        Returns:
            List of agent data
        """
        try:
            response = await self._client.table("agents").select("*").execute()
            return response.data
        except Exception as e:
            logger.error(f"Failed to list agents: {e}", exc_info=True)
            raise

    async def update_agent(self, agent_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update agent data.
        
        Args:
            agent_id: Agent ID
            update_data: Data to update
            
        Returns:
            Updated agent data if found, None otherwise
        """
        try:
            response = await self._client.table("agents").update(update_data).eq("id", agent_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to update agent {agent_id}: {e}", exc_info=True)
            raise

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            response = await self._client.table("agents").delete().eq("id", agent_id).execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Failed to delete agent {agent_id}: {e}", exc_info=True)
            raise

    async def create_phone_number(self, number_data: Dict) -> Dict:
        """Create a new phone number record."""
        return await self._client.table('phone_numbers').insert(number_data).execute().data[0]

    async def update_phone_number(self, number_id: str, updates: Dict) -> Optional[Dict]:
        """Update a phone number's details."""
        try:
            return await self._client.table('phone_numbers').update(updates).eq('id', number_id).execute().data[0]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def delete_phone_number(self, number_id: str) -> bool:
        """Delete a phone number."""
        try:
            response = await self._client.table('phone_numbers').delete().eq('id', number_id).execute()
            return bool(response.data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    async def create_transcript_segment(
        self,
        call_id: str,
        segment_number: int,
        speaker: str,
        text: str,
        start_time: float,
        end_time: float
    ) -> Dict[str, Any]:
        """Create a new transcript segment in the database."""
        data = {
            "call_id": call_id,
            "segment_number": segment_number,
            "speaker": speaker,
            "text": text,
            "start_time": start_time,
            "end_time": end_time
        }
        return await self._client.table('transcript_segments').insert(data).execute().data[0]

    async def get_call_transcript(self, call_id: str) -> List[Dict[str, Any]]:
        """Get all transcript segments for a call."""
        return await self._client.table('transcript_segments').select('*').eq('call_id', call_id).execute().data

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request to the Supabase API with proper error handling and retries.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request body data
            params: Query parameters
            
        Returns:
            Dict containing the API response
            
        Raises:
            Exception: If the request fails after retries
        """
        @backoff.on_exception(
            backoff.expo,
            (httpx.NetworkError, httpx.TimeoutException),
            max_tries=3,
            max_time=30
        )
        async def _make_request_with_retry():
            await self._ensure_connection()
            url = f"{self._url}/{endpoint}"
            
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(
                    f"Supabase API request failed: {str(e)}",
                    exc_info=True,
                    extra={
                        "method": method,
                        "endpoint": endpoint,
                        "status_code": e.response.status_code if hasattr(e, 'response') else None
                    }
                )
                raise
            except Exception as e:
                logger.error(
                    f"Unexpected error in Supabase API request: {str(e)}",
                    exc_info=True,
                    extra={
                        "method": method,
                        "endpoint": endpoint
                    }
                )
                raise

        return await _make_request_with_retry()

    async def list_records(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List records from a table with optional filtering and pagination."""
        params = {}
        
        if filters:
            for key, value in filters.items():
                params[key] = f"eq.{value}"
                
        if order_by:
            params["order"] = order_by
            
        if limit:
            params["limit"] = limit
            
        if offset:
            params["offset"] = offset
            
        return await self._make_request("GET", table, params=params)

    async def create_ai_agent(
        self,
        name: str,
        description: str,
        system_prompt: str,
        voice_id: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Create a new AI agent configuration."""
        data = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "voice_id": voice_id,
            "language": language
        }
        return await self._make_request("POST", "ai_agents", data=data)

    async def get_ai_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get AI agent configuration."""
        try:
            return await self._make_request("GET", f"ai_agents/{agent_id}")
        except Exception as e:
            logger.error(f"Error getting AI agent {agent_id}: {str(e)}")
            return None

    async def update_ai_agent(
        self,
        agent_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update AI agent configuration."""
        return await self._make_request(
            "PATCH",
            f"ai_agents/{agent_id}",
            data=updates
        )

    async def delete_ai_agent(self, agent_id: str) -> bool:
        """Delete an AI agent configuration."""
        try:
            await self._make_request("DELETE", f"ai_agents/{agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting AI agent {agent_id}: {str(e)}")
            return False

    async def create_phone_number(self, number_data: Dict) -> Dict:
        """Create a new phone number record."""
        return await self._make_request('POST', 'phone_numbers', json=number_data)

    async def get_phone_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get phone number details from the database."""
        try:
            return await self._make_request(
                "GET",
                "phone_numbers",
                params={"number": f"eq.{phone_number}"}
            )
        except Exception as e:
            logger.error(f"Error getting phone number {phone_number}: {str(e)}")
            return None

    async def update_phone_number(self, number_id: str, updates: Dict) -> Optional[Dict]:
        """Update a phone number's details."""
        try:
            return await self._make_request('PATCH', f'phone_numbers?id=eq.{number_id}', json=updates)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def delete_phone_number(self, number_id: str) -> bool:
        """Delete a phone number."""
        try:
            await self._make_request('DELETE', f'phone_numbers?id=eq.{number_id}')
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    async def create_sip_trunk(self, trunk_data: Dict) -> Dict:
        """Create a new SIP trunk record."""
        return await self._make_request('POST', 'sip_trunks', json=trunk_data)

    async def get_sip_trunk(self, trunk_id: str) -> Optional[Dict[str, Any]]:
        """Get SIP trunk details from the database."""
        try:
            return await self._make_request(
                "GET",
                f"sip_trunks/{trunk_id}"
            )
        except Exception as e:
            logger.error(f"Error getting SIP trunk {trunk_id}: {str(e)}")
            return None

    async def create_call_record(
        self,
        call_id: str,
        from_number: str,
        to_number: str,
        agent_id: str,
        status: str = "initiated"
    ) -> Dict[str, Any]:
        """Create a new call record in the database."""
        data = {
            "call_id": call_id,
            "from_number": from_number,
            "to_number": to_number,
            "agent_id": agent_id,
            "status": status,
            "start_time": "now()"
        }
        return await self._make_request("POST", "call_records", data=data)

    async def get_call_record(self, call_id: str) -> Optional[Dict]:
        """Get a call record by ID."""
        try:
            return await self._make_request('GET', f'calls?id=eq.{call_id}')
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def create_transcript_segment(
        self,
        call_id: str,
        segment_number: int,
        speaker: str,
        text: str,
        start_time: float,
        end_time: float
    ) -> Dict[str, Any]:
        """Create a new transcript segment in the database."""
        data = {
            "call_id": call_id,
            "segment_number": segment_number,
            "speaker": speaker,
            "text": text,
            "start_time": start_time,
            "end_time": end_time
        }
        return await self._make_request("POST", "transcript_segments", data=data)

    async def get_call_transcript(self, call_id: str) -> List[Dict[str, Any]]:
        """Get all transcript segments for a call."""
        return await self._make_request(
            "GET",
            "transcript_segments",
            params={
                "call_id": f"eq.{call_id}",
                "order": "segment_number.asc"
            }
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure httpx client is initialized."""
        if self._client is None:
            self._client = create_client(self._url, self._key)
        return self._client

    async def create_call_segment(self, segment_data: Dict) -> Dict:
        """Create a new call segment."""
        return await self._make_request('POST', 'call_segments', json=segment_data)

    async def get_call_segments(self, call_id: str) -> List[Dict]:
        """Get all segments for a call."""
        try:
            return await self._make_request('GET', f'call_segments?call_id=eq.{call_id}')
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

    async def update_call_record(
        self,
        call_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a call record in the database."""
        return await self._make_request(
            "PATCH",
            f"call_records/{call_id}",
            data=updates
        )

    async def create_transcript_segment(
        self,
        call_id: str,
        segment_number: int,
        speaker: str,
        text: str,
        start_time: float,
        end_time: float
    ) -> Dict[str, Any]:
        """Create a new transcript segment in the database."""
        data = {
            "call_id": call_id,
            "segment_number": segment_number,
            "speaker": speaker,
            "text": text,
            "start_time": start_time,
            "end_time": end_time
        }
        return await self._make_request("POST", "transcript_segments", data=data)

    async def get_call_transcript(self, call_id: str) -> List[Dict[str, Any]]:
        """Get all transcript segments for a call."""
        return await self._make_request(
            "GET",
            "transcript_segments",
            params={
                "call_id": f"eq.{call_id}",
                "order": "segment_number.asc"
            }
        ) 