"""HTTP client for communicating with the NVDA MCP Bridge plugin."""

import json
import urllib.request
import urllib.error

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"


class NVDABridgeError(Exception):
	"""Error communicating with the NVDA bridge."""

	pass


class NVDABridgeClient:
	"""Client for the NVDA MCP Bridge HTTP API."""

	def __init__(self, base_url: str = DEFAULT_BRIDGE_URL, timeout: float = 15.0):
		self.base_url = base_url.rstrip("/")
		self.timeout = timeout

	def health_check(self) -> dict:
		"""Check if the NVDA bridge is running."""
		try:
			req = urllib.request.Request(f"{self.base_url}/health")
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				return json.loads(resp.read())
		except urllib.error.URLError as e:
			raise NVDABridgeError(
				f"Cannot connect to NVDA bridge at {self.base_url}. "
				f"Make sure NVDA is running with the nvdaMCPBridge plugin installed. "
				f"Error: {e}"
			) from e

	def call(self, method: str, params: dict | None = None) -> dict:
		"""Call a method on the NVDA bridge.

		Args:
			method: The API method name (e.g. 'speak', 'getFocus').
			params: Optional parameters for the method.

		Returns:
			The result dictionary from the bridge.

		Raises:
			NVDABridgeError: If the call fails.
		"""
		payload = json.dumps({"method": method, "params": params or {}}).encode("utf-8")
		req = urllib.request.Request(
			f"{self.base_url}/api",
			data=payload,
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				data = json.loads(resp.read())
		except urllib.error.URLError as e:
			raise NVDABridgeError(
				f"Cannot connect to NVDA bridge at {self.base_url}. "
				f"Make sure NVDA is running with the nvdaMCPBridge plugin installed. "
				f"Error: {e}"
			) from e
		except json.JSONDecodeError as e:
			raise NVDABridgeError(f"Invalid response from NVDA bridge: {e}") from e

		if "error" in data:
			raise NVDABridgeError(f"NVDA bridge error: {data['error']}")

		return data.get("result", {})
