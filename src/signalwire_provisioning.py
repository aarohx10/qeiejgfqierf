import json
import logging
import base64
from typing import Dict, Optional, Any, List
import httpx
from config import (
    SIGNALWIRE_PROJECT_ID,
    SIGNALWIRE_TOKEN,
    SIGNALWIRE_SPACE_URL,
    HTTP_TIMEOUT
)

logger = logging.getLogger(__name__)

class SignalWireProvisioningClient:
    def __init__(self):
        """Initialize the SignalWire provisioning client."""
        self.project_id = SIGNALWIRE_PROJECT_ID
        self.token = SIGNALWIRE_TOKEN
        self.space_url = SIGNALWIRE_SPACE_URL
        self.base_path = f"{self.space_url}/api/laml/2010-04-01/Accounts/{self.project_id}"
        
        # Create Basic Auth header
        auth_string = f"{self.project_id}:{self.token}"
        auth_bytes = auth_string.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')
        
        self.headers = {
            "Authorization": f"Basic {base64_auth}",
            "Content-Type": "application/json"
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure httpx client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                headers=self.headers
            )
        return self._client

    async def close(self):
        """Close the httpx client."""
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
        Make a request to the SignalWire API with proper error handling and retries.
        
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
        import backoff  # Import here to avoid circular imports
        
        @backoff.on_exception(
            backoff.expo,
            (httpx.NetworkError, httpx.TimeoutException),
            max_tries=3,
            max_time=30
        )
        async def _make_request_with_retry():
            client = await self._ensure_client()
            url = f"{self.base_path}/{endpoint.lstrip('/')}"
            
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(
                    f"SignalWire API request failed: {str(e)}",
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
                    f"Unexpected error in SignalWire API request: {str(e)}",
                    exc_info=True,
                    extra={
                        "method": method,
                        "endpoint": endpoint
                    }
                )
                raise

        return await _make_request_with_retry()

    async def get_phone_number(self, phone_number_sid: str) -> Dict[str, Any]:
        """Get phone number details."""
        return await self._make_request(
            "GET",
            f"/phone_numbers/{phone_number_sid}"
        )

    async def list_phone_numbers(
        self,
        phone_number: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """List phone numbers with optional filtering."""
        params = {"phone_number": phone_number, **kwargs}
        response = await self._make_request(
            "GET",
            "/phone_numbers",
            params=params
        )
        return response.get("data", [])

    async def get_sip_trunk(self, trunk_sid: str) -> Dict[str, Any]:
        """Get SIP trunk details."""
        return await self._make_request(
            "GET",
            f"/sip_trunks/{trunk_sid}"
        )

    async def list_sip_trunks(
        self,
        trunk_name: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """List SIP trunks with optional filtering."""
        params = {"name": trunk_name, **kwargs}
        response = await self._make_request(
            "GET",
            "/sip_trunks",
            params=params
        )
        return response.get("data", [])

    async def update_sip_trunk(
        self,
        trunk_sid: str,
        name: Optional[str] = None,
        ip_addresses: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Update SIP trunk configuration."""
        data = {
            "name": name,
            "ip_addresses": ip_addresses,
            **kwargs
        }
        return await self._make_request(
            "PATCH",
            f"/sip_trunks/{trunk_sid}",
            data=data
        )

    async def get_call_recording(self, recording_sid: str) -> Dict[str, Any]:
        """Get call recording details."""
        return await self._make_request(
            "GET",
            f"/recordings/{recording_sid}"
        )

    async def list_call_recordings(
        self,
        call_sid: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """List call recordings with optional filtering."""
        params = {
            "call_sid": call_sid,
            "start_time": start_time,
            "end_time": end_time,
            **kwargs
        }
        response = await self._make_request(
            "GET",
            "/recordings",
            params=params
        )
        return response.get("data", [])

    async def get_call_analytics(
        self,
        start_time: str,
        end_time: str,
        metrics: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Get call analytics data."""
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "metrics": metrics,
            **kwargs
        }
        return await self._make_request(
            "GET",
            "/analytics/calls",
            params=params
        )

    async def initiate_call(self, from_number: str, to_number: str, webhook_url: str, client_state: Optional[Dict] = None) -> Dict:
        """
        Programmatically originates an outbound call via SignalWire.
        Args:
            from_number (str): The number to call from (your SignalWire number).
            to_number (str): The destination phone number.
            webhook_url (str): The URL where SignalWire should send call events (e.g., media stream URL).
            client_state (Optional[Dict]): Custom data to pass through SignalWire.
        Returns:
            Dict: Response from SignalWire containing call details.
        """
        call_payload = {
            "from": from_number,
            "to": to_number,
            "url": webhook_url, # This webhook receives call events for the duration of the call
            "method": "POST",
            "client_state": json.dumps(client_state) if client_state else None
        }
        logger.info(f"Initiating outbound call from {from_number} to {to_number}")
        return await self._make_request('POST', f'calls', json_data=call_payload)

    async def purchase_phone_number(self, number_config: Dict) -> Dict:
        """Initiates the purchase of a new phone number."""
        logger.info(f"Attempting to purchase phone number: {number_config.get('number')}")
        return await self._make_request('POST', f'phone_numbers', json_data=number_config)

    async def configure_sip_trunk(self, trunk_config: Dict) -> Dict:
        """Sets up or modifies a BYOC SIP Trunk within SignalWire."""
        logger.info(f"Configuring SIP Trunk: {trunk_config.get('name')}")
        # The actual path might vary based on SignalWire API for SIP trunks (e.g., /api/relay/v2/trunks)
        return await self._make_request('POST', f'trunks', json_data=trunk_config)

    async def get_call_transcription(self, recording_id: str) -> Dict:
        """
        Get transcription for a specific recording.
        
        Args:
            recording_id: The recording ID to transcribe
            
        Returns:
            Dict containing transcription details
        """
        return await self._make_request("GET", f"recordings/{recording_id}/transcription")

    async def get_call_analytics(self, call_id: str) -> Dict[str, Any]:
        """Get analytics for a specific call."""
        return await self._make_request("GET", f"calls/{call_id}/analytics")

    async def get_call_quality_metrics(self, call_id: str) -> Dict[str, Any]:
        """Get quality metrics for a specific call."""
        return await self._make_request("GET", f"calls/{call_id}/quality_metrics")

    async def get_call_analytics(
        self,
        start_date: str,
        end_date: str,
        metrics: List[str] = ["duration", "status", "direction"]
    ) -> Dict:
        """
        Get call analytics for a date range.
        
        Args:
            start_date: Start date in ISO format
            end_date: End date in ISO format
            metrics: List of metrics to include
            
        Returns:
            Dict containing call analytics
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "metrics": ",".join(metrics)
        }
        return await self._make_request("GET", "/analytics/calls", params=params)

    async def get_active_calls(self) -> List[Dict]:
        """
        Get list of currently active calls.
        
        Returns:
            List of active call details
        """
        response = await self._make_request("GET", "/calls", params={"status": "in-progress"})
        return response.get("calls", [])

    async def get_call_details(self, call_id: str) -> Dict:
        """
        Get detailed information about a specific call.
        
        Args:
            call_id: The call ID to look up
            
        Returns:
            Dict containing call details
        """
        return await self._make_request("GET", f"/calls/{call_id}")

    async def update_call_recording_settings(
        self,
        call_id: str,
        recording_id: str,
        settings: Dict[str, Any]
    ) -> Dict:
        """
        Update settings for an active recording.
        
        Args:
            call_id: The call ID
            recording_id: The recording ID to update
            settings: Dict of settings to update
            
        Returns:
            Dict containing updated recording details
        """
        return await self._make_request("PUT", f"/calls/{call_id}/recordings/{recording_id}", data=settings)

    async def get_call_recordings(self, call_id: str) -> List[Dict]:
        """
        Get all recordings for a specific call.
        
        Args:
            call_id: The call ID to get recordings for
            
        Returns:
            List of recording details
        """
        response = await self._make_request("GET", f"/calls/{call_id}/recordings")
        return response.get("recordings", [])

    async def delete_phone_number(self, phone_number: str) -> bool:
        """
        Release a phone number back to SignalWire.
        
        Args:
            phone_number: The phone number to release
            
        Returns:
            bool indicating success
        """
        try:
            await self._make_request("DELETE", f"phone_numbers/{phone_number}")
            return True
        except Exception as e:
            logger.error(f"Error deleting phone number {phone_number}: {str(e)}")
            return False

    async def start_call_recording(self, call_id: str, format: str = "mp3") -> Dict:
        """
        Start recording a call.
        
        Args:
            call_id: The call ID to record
            format: Audio format (mp3, wav)
            
        Returns:
            Dict containing recording details
        """
        data = {
            "format": format,
            "status_callback": f"{SIGNALWIRE_WEBHOOK_URL_BASE}/recording-status",
            "status_callback_event": ["completed"],
            "status_callback_method": "POST"
        }
        return await self._make_request("POST", f"calls/{call_id}/recordings", data=data)

    async def stop_call_recording(self, call_id: str, recording_id: str) -> Dict:
        """
        Stop an active call recording.
        
        Args:
            call_id: The call ID
            recording_id: The recording ID to stop
            
        Returns:
            Dict containing recording status
        """
        return await self._make_request("POST", f"calls/{call_id}/recordings/{recording_id}/stop") 