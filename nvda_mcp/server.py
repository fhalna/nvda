"""NVDA MCP Server - Control NVDA screen reader via the Model Context Protocol.

This server connects to the NVDA MCP Bridge plugin (running inside NVDA)
and exposes NVDA's capabilities as MCP tools.

Usage:
    python -m nvda_mcp                           # default bridge URL
    python -m nvda_mcp --bridge-url http://host:port  # custom bridge URL
"""

import json
import os

from mcp.server.fastmcp import FastMCP

from .bridge_client import NVDABridgeClient, NVDABridgeError

BRIDGE_URL = os.environ.get("NVDA_BRIDGE_URL", "http://127.0.0.1:8765")

mcp = FastMCP(
	"nvda",
	instructions=(
		"NVDA MCP Server - Controls the NVDA screen reader for Windows. "
		"Use these tools to read screen content, navigate UI elements, "
		"speak text, interact with braille displays, and simulate input. "
		"The NVDA Bridge plugin must be running inside NVDA."
	),
)

_client = NVDABridgeClient(BRIDGE_URL)


def _call(method: str, params: dict | None = None) -> dict:
	"""Call the NVDA bridge, returning the result or raising on error."""
	return _client.call(method, params)


def _format_object(obj: dict) -> str:
	"""Format an NVDAObject dict into a readable string."""
	if not obj:
		return "(no object)"
	parts = []
	name = obj.get("name", "")
	role = obj.get("role", "")
	value = obj.get("value", "")
	states = obj.get("states", [])
	desc = obj.get("description", "")
	app = obj.get("appName", "")

	if role:
		parts.append(f"[{role}]")
	if name:
		parts.append(f'"{name}"')
	if value:
		parts.append(f"value={value}")
	if states:
		parts.append(f"states=[{', '.join(states)}]")
	if desc:
		parts.append(f"desc={desc}")
	if app:
		parts.append(f"app={app}")
	child_count = obj.get("childCount", 0)
	if child_count:
		parts.append(f"children={child_count}")
	loc = obj.get("location")
	if loc:
		parts.append(f"pos=({loc['left']},{loc['top']} {loc['width']}x{loc['height']})")

	return " ".join(parts)


def _format_tree(obj: dict, indent: int = 0) -> str:
	"""Format an object tree into a readable indented string."""
	if not obj:
		return ""
	prefix = "  " * indent
	line = prefix + _format_object(obj)
	lines = [line]
	for child in obj.get("children", []):
		lines.append(_format_tree(child, indent + 1))
	return "\n".join(lines)


# ============================================================
# MCP Tools
# ============================================================


@mcp.tool()
def speak(text: str) -> str:
	"""Make NVDA speak the given text aloud.

	Args:
		text: The text to speak.
	"""
	result = _call("speak", {"text": text})
	return f"Spoken: {result.get('spoken', text)}"


@mcp.tool()
def cancel_speech() -> str:
	"""Stop NVDA from speaking immediately."""
	_call("cancelSpeech")
	return "Speech cancelled."


@mcp.tool()
def get_speech_history(count: int = 10) -> str:
	"""Get the recent speech output history from NVDA.

	Useful to understand what NVDA has been announcing to the user.

	Args:
		count: Number of recent speech entries to return (default 10).
	"""
	result = _call("getSpeechHistory", {"count": count})
	history = result.get("history", [])
	if not history:
		return "No speech history available."
	lines = [f"{i + 1}. {entry}" for i, entry in enumerate(history)]
	return "Recent speech output:\n" + "\n".join(lines)


@mcp.tool()
def braille_message(text: str) -> str:
	"""Display a message on the connected braille device.

	Args:
		text: The text to display on the braille device.
	"""
	result = _call("braille", {"text": text})
	return f"Displayed on braille: {result.get('displayed', text)}"


@mcp.tool()
def get_focus() -> str:
	"""Get information about the currently focused UI element.

	Returns details about the object that currently has keyboard focus,
	including its name, role, value, and states.
	"""
	result = _call("getFocus")
	return f"Focused element: {_format_object(result)}"


@mcp.tool()
def get_foreground() -> str:
	"""Get information about the current foreground window.

	Returns details about the top-level window that is currently in the foreground.
	"""
	result = _call("getForeground")
	return f"Foreground window: {_format_object(result)}"


@mcp.tool()
def get_navigator() -> str:
	"""Get the current navigator object.

	The navigator is NVDA's object review cursor, which can move independently
	of keyboard focus to explore the UI.
	"""
	result = _call("getNavigator")
	return f"Navigator object: {_format_object(result)}"


@mcp.tool()
def move_navigator(direction: str) -> str:
	"""Move the navigator object in the given direction.

	The navigator allows exploring the UI without changing keyboard focus.

	Args:
		direction: One of 'parent', 'firstChild', 'next', 'previous'.
			- parent: Move to the containing/parent element
			- firstChild: Move to the first child element
			- next: Move to the next sibling element
			- previous: Move to the previous sibling element
	"""
	result = _call("moveNavigator", {"direction": direction})
	if not result.get("moved", False):
		return f"Cannot move {direction}: {result.get('reason', 'unknown')}"
	obj = result.get("object", {})
	return f"Moved {direction} to: {_format_object(obj)}"


@mcp.tool()
def activate_object() -> str:
	"""Activate (perform the default action on) the current navigator object.

	This is equivalent to clicking or pressing Enter on the element.
	For example, activating a button will press it, activating a link will follow it.
	"""
	result = _call("activateObject")
	if not result.get("activated", False):
		return f"Could not activate: {result.get('reason', 'unknown')}"
	obj = result.get("object", {})
	return f"Activated: {_format_object(obj)}"


@mcp.tool()
def get_status_bar() -> str:
	"""Read the status bar of the current foreground application."""
	result = _call("getStatusBar")
	if not result.get("found", False):
		return "No status bar found for the current window."
	return f"Status bar: {result.get('text', '')}"


@mcp.tool()
def review_current_line() -> str:
	"""Read the current line at the review cursor position.

	This reads the text content at the current review/caret position.
	"""
	result = _call("reviewCurrentLine")
	text = result.get("text", "")
	return f"Current line: {text}" if text else "Current line is empty."


@mcp.tool()
def get_clipboard() -> str:
	"""Get the current content of the Windows clipboard."""
	result = _call("getClipboard")
	text = result.get("text", "")
	return f"Clipboard: {text}" if text else "Clipboard is empty."


@mcp.tool()
def set_clipboard(text: str) -> str:
	"""Set the Windows clipboard content.

	Args:
		text: The text to copy to the clipboard.
	"""
	result = _call("setClipboard", {"text": text})
	if result.get("success", False):
		return f"Clipboard set to: {text}"
	return "Failed to set clipboard."


@mcp.tool()
def send_keys(keys: str) -> str:
	"""Simulate keyboard input.

	Send key presses to the system as if typed on the keyboard.
	Uses NVDA's key name format.

	Args:
		keys: Key combination string. Examples:
			- "enter" - press Enter
			- "tab" - press Tab
			- "escape" - press Escape
			- "control+a" - select all
			- "control+c" - copy
			- "control+v" - paste
			- "alt+f4" - close window
			- "windows+d" - show desktop
			- "shift+tab" - reverse tab
			- "downArrow" - arrow down
			- "upArrow" - arrow up
			- "leftArrow" - arrow left
			- "rightArrow" - arrow right
			- "space" - press Space
			- "backspace" - press Backspace
			- "delete" - press Delete
			- "home" - press Home
			- "end" - press End
			- "f1" through "f12" - function keys
	"""
	result = _call("sendKeys", {"keys": keys})
	return f"Keys sent: {result.get('sent', keys)}"


@mcp.tool()
def move_mouse(x: int, y: int) -> str:
	"""Move the mouse cursor to the specified screen coordinates.

	Args:
		x: Horizontal position in pixels from the left edge of the screen.
		y: Vertical position in pixels from the top edge of the screen.
	"""
	result = _call("moveMouse", {"x": x, "y": y})
	return f"Mouse moved to ({x}, {y})"


@mcp.tool()
def click_mouse(x: int | None = None, y: int | None = None, button: str = "left") -> str:
	"""Click the mouse at the specified position (or current position).

	Args:
		x: Horizontal position. If not provided, clicks at current position.
		y: Vertical position. If not provided, clicks at current position.
		button: Mouse button - 'left' or 'right' (default: 'left').
	"""
	params = {"button": button}
	if x is not None:
		params["x"] = x
	if y is not None:
		params["y"] = y
	_call("clickMouse", params)
	pos = f"({x}, {y})" if x is not None else "current position"
	return f"{button.capitalize()} clicked at {pos}"


@mcp.tool()
def get_nvda_version() -> str:
	"""Get the NVDA version information."""
	result = _call("getVersion")
	return f"NVDA {result.get('name', '')} version {result.get('version', 'unknown')}"


@mcp.tool()
def get_speech_settings() -> str:
	"""Get the current NVDA speech synthesizer settings."""
	result = _call("getSpeechSettings")
	parts = []
	if result.get("synthName"):
		parts.append(f"Synthesizer: {result['synthName']}")
	if result.get("rate") is not None:
		parts.append(f"Rate: {result['rate']}")
	if result.get("volume") is not None:
		parts.append(f"Volume: {result['volume']}")
	if result.get("voice"):
		parts.append(f"Voice: {result['voice']}")
	return "\n".join(parts) if parts else "No speech settings available."


@mcp.tool()
def get_object_tree(depth: int = 3, from_object: str = "focus") -> str:
	"""Get a tree view of UI elements starting from a reference object.

	This provides a hierarchical snapshot of the accessibility tree,
	useful for understanding the structure of the current UI.

	Args:
		depth: How many levels deep to traverse (default 3, max 5).
		from_object: Starting point - 'focus', 'foreground', or 'navigator' (default 'focus').
	"""
	depth = min(depth, 5)
	result = _call("getObjectTree", {"depth": depth, "from": from_object})
	return f"Object tree ({from_object}, depth={depth}):\n{_format_tree(result)}"


@mcp.tool()
def check_connection() -> str:
	"""Check if the NVDA MCP Bridge is running and accessible.

	Use this to verify the connection to NVDA before performing other operations.
	"""
	try:
		result = _client.health_check()
		version = result.get("version", "unknown")
		return f"Connected to NVDA bridge. NVDA version: {version}"
	except NVDABridgeError as e:
		return f"NOT connected: {e}"


def main():
	"""Run the MCP server."""
	import argparse

	parser = argparse.ArgumentParser(description="NVDA MCP Server")
	parser.add_argument(
		"--bridge-url",
		default=BRIDGE_URL,
		help=f"URL of the NVDA MCP Bridge (default: {BRIDGE_URL})",
	)
	parser.add_argument(
		"--transport",
		choices=["stdio", "sse"],
		default="stdio",
		help="MCP transport type (default: stdio)",
	)
	parser.add_argument(
		"--port",
		type=int,
		default=3000,
		help="Port for SSE transport (default: 3000)",
	)
	parser.add_argument(
		"--host",
		default="localhost",
		help="Host for SSE transport (default: localhost)",
	)
	args = parser.parse_args()

	global _client
	_client = NVDABridgeClient(args.bridge_url)

	if args.transport == "sse":
		mcp.run(transport="sse", sse_params={"host": args.host, "port": args.port})
	else:
		mcp.run(transport="stdio")


if __name__ == "__main__":
	main()
