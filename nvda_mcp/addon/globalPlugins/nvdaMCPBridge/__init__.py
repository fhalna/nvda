# NVDA MCP Bridge - Global Plugin
# This plugin runs inside NVDA and exposes a local HTTP API
# that the MCP server can connect to for controlling NVDA.
#
# Installation: Copy this file to NVDA's globalPlugins/ directory
# (e.g. %APPDATA%/nvda/globalPlugins/nvdaMCPBridge.py)

import globalPluginHandler
import threading
import json
import http.server
import api
import speech
import braille
import controlTypes
import config
import buildVersion
import wx
import ui
from logHandler import log

DEFAULT_PORT = 8765


def _call_on_main_thread(func, timeout=10.0):
	"""Execute a function on NVDA's main (wx) thread and wait for the result."""
	result_holder = [None]
	error_holder = [None]
	event = threading.Event()

	def wrapper():
		try:
			result_holder[0] = func()
		except Exception as e:
			error_holder[0] = e
		finally:
			event.set()

	wx.CallAfter(wrapper)
	if not event.wait(timeout=timeout):
		raise TimeoutError("Call to NVDA main thread timed out")
	if error_holder[0]:
		raise error_holder[0]
	return result_holder[0]


def _serialize_nvda_object(obj):
	"""Convert an NVDAObject to a JSON-serializable dictionary."""
	if obj is None:
		return None
	result = {}
	try:
		result["name"] = obj.name or ""
	except Exception:
		result["name"] = ""
	try:
		result["role"] = controlTypes.Role(obj.role).displayString if obj.role else ""
		result["roleId"] = controlTypes.Role(obj.role).name if obj.role else ""
	except Exception:
		result["role"] = ""
		result["roleId"] = ""
	try:
		result["value"] = obj.value or ""
	except Exception:
		result["value"] = ""
	try:
		result["description"] = obj.description or ""
	except Exception:
		result["description"] = ""
	try:
		result["states"] = [s.displayString for s in obj.states] if obj.states else []
		result["stateIds"] = [s.name for s in obj.states] if obj.states else []
	except Exception:
		result["states"] = []
		result["stateIds"] = []
	try:
		location = obj.location
		if location:
			result["location"] = {
				"left": location.left,
				"top": location.top,
				"width": location.width,
				"height": location.height,
			}
	except Exception:
		pass
	try:
		result["childCount"] = obj.childCount
	except Exception:
		result["childCount"] = 0
	try:
		result["windowClassName"] = obj.windowClassName or ""
	except Exception:
		pass
	try:
		if obj.appModule:
			result["appName"] = obj.appModule.appName
	except Exception:
		pass
	try:
		result["windowText"] = obj.windowText or ""
	except Exception:
		pass
	return result


def _serialize_tree(obj, max_depth=3, current_depth=0):
	"""Recursively serialize an NVDAObject and its children."""
	if obj is None or current_depth >= max_depth:
		return None
	result = _serialize_nvda_object(obj)
	if current_depth < max_depth - 1:
		children = []
		try:
			child = obj.firstChild
			count = 0
			while child and count < 50:
				child_data = _serialize_tree(child, max_depth, current_depth + 1)
				if child_data:
					children.append(child_data)
				child = child.next
				count += 1
		except Exception:
			pass
		result["children"] = children
	return result


class NVDABridgeRequestHandler(http.server.BaseHTTPRequestHandler):
	"""HTTP request handler for the MCP Bridge."""

	def do_POST(self):
		if self.path != "/api":
			self.send_response(404)
			self.end_headers()
			return
		try:
			content_length = int(self.headers.get("Content-Length", 0))
			body = self.rfile.read(content_length)
			request = json.loads(body)
		except (ValueError, json.JSONDecodeError) as e:
			self._send_json(400, {"error": f"Invalid request: {e}"})
			return

		method = request.get("method")
		params = request.get("params", {})

		try:
			result = self.server.plugin.dispatch(method, params)
			self._send_json(200, {"result": result})
		except Exception as e:
			log.error(f"MCP Bridge error in {method}: {e}", exc_info=True)
			self._send_json(500, {"error": str(e)})

	def do_GET(self):
		if self.path == "/health":
			self._send_json(200, {"status": "ok", "version": buildVersion.version})
		else:
			self.send_response(404)
			self.end_headers()

	def _send_json(self, status, data):
		self.send_response(status)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps(data).encode("utf-8"))

	def log_message(self, format, *args):
		log.debug(f"MCPBridge: {format % args}")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""NVDA Global Plugin that exposes a local HTTP bridge for MCP control."""

	def __init__(self):
		super().__init__()
		self._server = None
		self._thread = None
		self._speech_history = []
		self._max_history = 100
		# Register speech callback to capture speech output
		speech.pre_speech.register(self._on_speech)
		self._start_server()

	def _start_server(self):
		port = DEFAULT_PORT
		try:
			self._server = http.server.HTTPServer(("127.0.0.1", port), NVDABridgeRequestHandler)
			self._server.plugin = self
			self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
			self._thread.start()
			log.info(f"NVDA MCP Bridge started on 127.0.0.1:{port}")
		except Exception as e:
			log.error(f"Failed to start MCP Bridge: {e}")

	def terminate(self):
		speech.pre_speech.unregister(self._on_speech)
		if self._server:
			self._server.shutdown()
			log.info("NVDA MCP Bridge stopped")

	def _on_speech(self, speechSequence=None, **kwargs):
		"""Capture speech output for history."""
		if speechSequence is None:
			return
		text_parts = [item for item in speechSequence if isinstance(item, str)]
		if text_parts:
			text = " ".join(text_parts)
			self._speech_history.append(text)
			if len(self._speech_history) > self._max_history:
				self._speech_history = self._speech_history[-self._max_history:]

	def dispatch(self, method, params):
		"""Dispatch an API method call to the appropriate handler."""
		handlers = {
			"speak": self._handle_speak,
			"speakSsml": self._handle_speak_ssml,
			"cancelSpeech": self._handle_cancel_speech,
			"getSpeechHistory": self._handle_get_speech_history,
			"braille": self._handle_braille,
			"getFocus": self._handle_get_focus,
			"getForeground": self._handle_get_foreground,
			"getNavigator": self._handle_get_navigator,
			"moveNavigator": self._handle_move_navigator,
			"activateObject": self._handle_activate_object,
			"getStatusBar": self._handle_get_status_bar,
			"getClipboard": self._handle_get_clipboard,
			"setClipboard": self._handle_set_clipboard,
			"sendKeys": self._handle_send_keys,
			"moveMouse": self._handle_move_mouse,
			"clickMouse": self._handle_click_mouse,
			"getVersion": self._handle_get_version,
			"getSpeechSettings": self._handle_get_speech_settings,
			"getObjectTree": self._handle_get_object_tree,
			"reviewCurrentLine": self._handle_review_current_line,
		}
		handler = handlers.get(method)
		if not handler:
			raise ValueError(f"Unknown method: {method}")
		return handler(params)

	# --- Speech handlers ---

	def _handle_speak(self, params):
		text = params.get("text", "")

		def do():
			speech.speakMessage(text)

		_call_on_main_thread(do)
		return {"spoken": text}

	def _handle_speak_ssml(self, params):
		ssml = params.get("ssml", "")

		def do():
			speech.speakSsml(ssml)

		_call_on_main_thread(do)
		return {"spoken": True}

	def _handle_cancel_speech(self, params):
		def do():
			speech.cancelSpeech()

		_call_on_main_thread(do)
		return {"cancelled": True}

	def _handle_get_speech_history(self, params):
		count = params.get("count", 10)
		return {"history": self._speech_history[-count:]}

	# --- Braille handlers ---

	def _handle_braille(self, params):
		text = params.get("text", "")

		def do():
			braille.handler.message(text)

		_call_on_main_thread(do)
		return {"displayed": text}

	# --- Navigation handlers ---

	def _handle_get_focus(self, params):
		def do():
			return _serialize_nvda_object(api.getFocusObject())

		return _call_on_main_thread(do)

	def _handle_get_foreground(self, params):
		def do():
			return _serialize_nvda_object(api.getForegroundObject())

		return _call_on_main_thread(do)

	def _handle_get_navigator(self, params):
		def do():
			return _serialize_nvda_object(api.getNavigatorObject())

		return _call_on_main_thread(do)

	def _handle_move_navigator(self, params):
		direction = params.get("direction")
		if direction not in ("parent", "firstChild", "next", "previous"):
			raise ValueError(f"Invalid direction: {direction}. Use: parent, firstChild, next, previous")

		def do():
			nav = api.getNavigatorObject()
			target = getattr(nav, direction, None)
			if target is None:
				return {"moved": False, "reason": f"No object in direction: {direction}"}
			api.setNavigatorObject(target)
			speech.speakObject(target)
			return {"moved": True, "object": _serialize_nvda_object(target)}

		return _call_on_main_thread(do)

	def _handle_activate_object(self, params):
		def do():
			nav = api.getNavigatorObject()
			try:
				nav.doAction()
				return {"activated": True, "object": _serialize_nvda_object(nav)}
			except NotImplementedError:
				return {"activated": False, "reason": "Object does not support activation"}

		return _call_on_main_thread(do)

	# --- Reading handlers ---

	def _handle_get_status_bar(self, params):
		def do():
			statusBar = api.getStatusBar()
			if statusBar is None:
				return {"text": "", "found": False}
			text = api.getStatusBarText(statusBar)
			return {"text": text or "", "found": True}

		return _call_on_main_thread(do)

	def _handle_review_current_line(self, params):
		def do():
			import textInfos

			pos = api.getReviewPosition()
			line = pos.copy()
			line.expand(textInfos.UNIT_LINE)
			return {"text": line.text or "", "lineNumber": pos.lineNumber if hasattr(pos, "lineNumber") else None}

		return _call_on_main_thread(do)

	# --- Clipboard handlers ---

	def _handle_get_clipboard(self, params):
		def do():
			return {"text": api.getClipData() or ""}

		return _call_on_main_thread(do)

	def _handle_set_clipboard(self, params):
		text = params.get("text", "")

		def do():
			success = api.copyToClip(text)
			return {"success": success}

		return _call_on_main_thread(do)

	# --- Input handlers ---

	def _handle_send_keys(self, params):
		keys = params.get("keys", "")

		def do():
			import keyboardHandler

			gesture = keyboardHandler.KeyboardInputGesture.fromName(keys)
			gesture.send()
			return {"sent": keys}

		return _call_on_main_thread(do)

	def _handle_move_mouse(self, params):
		x = params.get("x", 0)
		y = params.get("y", 0)

		def do():
			import winUser

			winUser.setCursorPos(x, y)
			return {"moved": True, "x": x, "y": y}

		return _call_on_main_thread(do)

	def _handle_click_mouse(self, params):
		x = params.get("x")
		y = params.get("y")
		button = params.get("button", "left")

		def do():
			import mouseHandler
			import winUser

			if x is not None and y is not None:
				winUser.setCursorPos(x, y)
			if button == "left":
				mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0)
				mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTUP, 0, 0)
			elif button == "right":
				mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_RIGHTDOWN, 0, 0)
				mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_RIGHTUP, 0, 0)
			return {"clicked": True, "button": button}

		return _call_on_main_thread(do)

	# --- System handlers ---

	def _handle_get_version(self, params):
		return {
			"version": buildVersion.version,
			"name": buildVersion.name,
		}

	def _handle_get_speech_settings(self, params):
		def do():
			result = {}
			try:
				import synthDriverHandler

				synth = synthDriverHandler.getSynth()
				if synth:
					result["synthName"] = synth.name
					result["synthId"] = synth.id if hasattr(synth, "id") else ""
			except Exception:
				pass
			try:
				result["rate"] = config.conf["speech"].get("rate")
				result["volume"] = config.conf["speech"].get("volume")
				result["voice"] = config.conf["speech"].get("voice", "")
			except Exception:
				pass
			return result

		return _call_on_main_thread(do)

	def _handle_get_object_tree(self, params):
		depth = params.get("depth", 3)
		from_obj = params.get("from", "focus")

		def do():
			if from_obj == "foreground":
				obj = api.getForegroundObject()
			elif from_obj == "navigator":
				obj = api.getNavigatorObject()
			else:
				obj = api.getFocusObject()
			return _serialize_tree(obj, max_depth=depth)

		return _call_on_main_thread(do)
