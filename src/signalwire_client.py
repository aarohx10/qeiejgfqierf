import logging
import json
from typing import Dict, Any, Optional, List
import httpx
from config import (
    SIGNALWIRE_PROJECT_ID,
    SIGNALWIRE_TOKEN,
    SIGNALWIRE_SPACE_URL
)

logger = logging.getLogger(__name__)

class SignalWireClient:
    def __init__(self):
        self.project_id = SIGNALWIRE_PROJECT_ID
        self.token = SIGNALWIRE_TOKEN
        self.space_url = SIGNALWIRE_SPACE_URL
        self._client = None
        self._headers = {
            "Authorization": f"Basic {self.project_id}:{self.token}",
            "Content-Type": "application/json"
        }

    async def _ensure_client(self):
        """Ensure httpx client is initialized."""
        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers=self._headers,
                base_url=self.space_url
            )

    async def close(self):
        """Close httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request to the SignalWire API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request body data
            params: Query parameters
            
        Returns:
            Dict containing API response
        """
        await self._ensure_client()
        
        try:
            response = await self._client.request(
                method,
                endpoint,
                json=data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"SignalWire API error: {e}")
            raise

    async def create_call(
        self,
        to: str,
        from_: str,
        url: str,
        status_callback: Optional[str] = None,
        status_callback_method: str = "POST",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new call.
        
        Args:
            to: Destination phone number
            from_: Source phone number
            url: Webhook URL for call control
            status_callback: URL for call status updates
            status_callback_method: HTTP method for status updates
            **kwargs: Additional call parameters
            
        Returns:
            Dict containing call details
        """
        data = {
            "to": to,
            "from": from_,
            "url": url,
            "status_callback": status_callback,
            "status_callback_method": status_callback_method,
            **kwargs
        }
        
        return await self._make_request("POST", "/api/laml/2010-04-01/Accounts/{self.project_id}/Calls.json", data=data)

    async def get_call(self, call_sid: str) -> Dict[str, Any]:
        """
        Get call details.
        
        Args:
            call_sid: Call SID
            
        Returns:
            Dict containing call details
        """
        return await self._make_request(
            "GET",
            f"/api/laml/2010-04-01/Accounts/{self.project_id}/Calls/{call_sid}.json"
        )

    async def update_call(
        self,
        call_sid: str,
        status: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update call status.
        
        Args:
            call_sid: Call SID
            status: New call status
            **kwargs: Additional update parameters
            
        Returns:
            Dict containing updated call details
        """
        data = {"status": status, **kwargs}
        return await self._make_request(
            "POST",
            f"/api/laml/2010-04-01/Accounts/{self.project_id}/Calls/{call_sid}.json",
            data=data
        )

    async def list_calls(
        self,
        status: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        List calls with optional filtering.
        
        Args:
            status: Filter by call status
            start_time: Filter by start time
            end_time: Filter by end time
            **kwargs: Additional filter parameters
            
        Returns:
            List of call details
        """
        params = {
            "status": status,
            "start_time": start_time,
            "end_time": end_time,
            **kwargs
        }
        
        response = await self._make_request(
            "GET",
            f"/api/laml/2010-04-01/Accounts/{self.project_id}/Calls.json",
            params=params
        )
        
        return response.get("calls", [])

    async def get_phone_number(self, phone_number_sid: str) -> Dict[str, Any]:
        """
        Get phone number details.
        
        Args:
            phone_number_sid: Phone number SID
            
        Returns:
            Dict containing phone number details
        """
        return await self._make_request(
            "GET",
            f"/api/laml/2010-04-01/Accounts/{self.project_id}/IncomingPhoneNumbers/{phone_number_sid}.json"
        )

    async def list_phone_numbers(
        self,
        phone_number: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        List phone numbers with optional filtering.
        
        Args:
            phone_number: Filter by phone number
            **kwargs: Additional filter parameters
            
        Returns:
            List of phone number details
        """
        params = {"phone_number": phone_number, **kwargs}
        
        response = await self._make_request(
            "GET",
            f"/api/laml/2010-04-01/Accounts/{self.project_id}/IncomingPhoneNumbers.json",
            params=params
        )
        
        return response.get("incoming_phone_numbers", [])

    async def update_phone_number(
        self,
        phone_number_sid: str,
        voice_url: Optional[str] = None,
        voice_method: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update phone number configuration.
        
        Args:
            phone_number_sid: Phone number SID
            voice_url: New voice webhook URL
            voice_method: HTTP method for voice webhook
            **kwargs: Additional update parameters
            
        Returns:
            Dict containing updated phone number details
        """
        data = {
            "voice_url": voice_url,
            "voice_method": voice_method,
            **kwargs
        }
        
        return await self._make_request(
            "POST",
            f"/api/laml/2010-04-01/Accounts/{self.project_id}/IncomingPhoneNumbers/{phone_number_sid}.json",
            data=data
        ) 