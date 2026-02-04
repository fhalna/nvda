# Dark Mode - Focus Spotlight NVDA Add-on
# A screen curtain that shows only the currently highlighted element
# Copyright (C) 2024 NVDA Dark Mode Contributors
# This file is covered by the GNU General Public License.

"""
Dark Mode global plugin for NVDA.
Provides a screen curtain that blacks out the entire screen except for the
currently focused element (system focus, navigator object, or browse mode cursor).
Toggle with NVDA+Control+Alt+D.
"""

import threading
import ctypes
from ctypes import windll, byref, c_int, WINFUNCTYPE, POINTER, WinError
from ctypes.wintypes import HWND, HDC, RECT, MSG, BOOL, UINT, LPARAM, WPARAM

import globalPluginHandler
import ui
import api
import wx
from scriptHandler import script
from logHandler import log

# Windows constants
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001
GWL_EXSTYLE = -20
WM_PAINT = 0x000F
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_QUIT = 0x0012
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
COLOR_BACKGROUND = 1
SW_SHOW = 5
SW_HIDE = 0
PM_REMOVE = 0x0001
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001

# User32 functions
user32 = windll.user32
gdi32 = windll.gdi32

# Window class structure
WNDPROC = WINFUNCTYPE(c_int, HWND, UINT, WPARAM, LPARAM)

class WNDCLASSEX(ctypes.Structure):
	_fields_ = [
		("cbSize", UINT),
		("style", UINT),
		("lpfnWndProc", WNDPROC),
		("cbClsExtra", c_int),
		("cbWndExtra", c_int),
		("hInstance", ctypes.c_void_p),
		("hIcon", ctypes.c_void_p),
		("hCursor", ctypes.c_void_p),
		("hbrBackground", ctypes.c_void_p),
		("lpszMenuName", ctypes.c_wchar_p),
		("lpszClassName", ctypes.c_wchar_p),
		("hIconSm", ctypes.c_void_p),
	]


class PAINTSTRUCT(ctypes.Structure):
	_fields_ = [
		("hdc", HDC),
		("fErase", BOOL),
		("rcPaint", RECT),
		("fRestore", BOOL),
		("fIncUpdate", BOOL),
		("rgbReserved", ctypes.c_byte * 32),
	]


# Transparent color (magenta - will be the "hole")
TRANSPARENT_COLOR = 0x00FF00FF  # BGR format: magenta

# Highlight colors (BGR format for Windows)
COLOR_FOCUS = 0x00FF3603  # Blue
COLOR_NAVIGATOR = 0x006602FF  # Pink
COLOR_BROWSEMODE = 0x0003DEFF  # Yellow


class DarkModeOverlay:
	"""Creates a black overlay window with a transparent hole for the focused element."""

	def __init__(self):
		self._hwnd = None
		self._thread = None
		self._running = False
		self._wndproc = None  # Must keep reference to prevent garbage collection
		self._current_rect = None
		self._current_color = COLOR_FOCUS
		self._brush_black = None
		self._brush_transparent = None

	def start(self):
		"""Start the overlay in a separate thread."""
		if self._running:
			return True

		self._running = True
		self._thread = threading.Thread(target=self._run, daemon=True)
		self._thread.start()

		# Wait for window to be created
		import time
		for _ in range(50):  # Wait up to 5 seconds
			if self._hwnd:
				return True
			time.sleep(0.1)

		self._running = False
		return False

	def stop(self):
		"""Stop the overlay."""
		if not self._running:
			return

		self._running = False
		if self._hwnd:
			user32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)

		if self._thread:
			self._thread.join(timeout=2.0)
			self._thread = None

		self._hwnd = None

	def _run(self):
		"""Thread main function - creates window and runs message loop."""
		try:
			# Create brushes
			self._brush_black = gdi32.CreateSolidBrush(0x00000000)  # Black
			self._brush_transparent = gdi32.CreateSolidBrush(TRANSPARENT_COLOR)

			# Register window class
			self._wndproc = WNDPROC(self._window_proc)

			wc = WNDCLASSEX()
			wc.cbSize = ctypes.sizeof(WNDCLASSEX)
			wc.style = CS_HREDRAW | CS_VREDRAW
			wc.lpfnWndProc = self._wndproc
			wc.hInstance = user32.GetModuleHandleW(None)
			wc.hbrBackground = self._brush_black
			wc.lpszClassName = "NVDADarkModeOverlay"

			atom = user32.RegisterClassExW(byref(wc))
			if not atom:
				log.error("Failed to register window class")
				return

			# Get screen dimensions
			screen_width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
			screen_height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

			# For multi-monitor, get virtual screen
			left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
			top = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
			width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
			height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

			# Create window
			ex_style = WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
			style = WS_POPUP | WS_VISIBLE

			self._hwnd = user32.CreateWindowExW(
				ex_style,
				"NVDADarkModeOverlay",
				"NVDA Dark Mode",
				style,
				left, top, width, height - 1,  # -1 to allow desktop shortcuts
				None, None,
				user32.GetModuleHandleW(None),
				None
			)

			if not self._hwnd:
				log.error("Failed to create window")
				return

			# Set layered window attributes - make magenta transparent
			user32.SetLayeredWindowAttributes(self._hwnd, TRANSPARENT_COLOR, 255, LWA_COLORKEY)

			# Set up timer for refresh (100ms)
			user32.SetTimer(self._hwnd, 1, 100, None)

			# Show window
			user32.ShowWindow(self._hwnd, SW_SHOW)
			user32.UpdateWindow(self._hwnd)

			log.info("Dark Mode overlay window created")

			# Message loop
			msg = MSG()
			while self._running:
				if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
					if msg.message == WM_QUIT:
						break
					user32.TranslateMessage(byref(msg))
					user32.DispatchMessageW(byref(msg))
				else:
					import time
					time.sleep(0.01)

			# Cleanup
			user32.KillTimer(self._hwnd, 1)
			user32.DestroyWindow(self._hwnd)
			user32.UnregisterClassW("NVDADarkModeOverlay", user32.GetModuleHandleW(None))

			if self._brush_black:
				gdi32.DeleteObject(self._brush_black)
			if self._brush_transparent:
				gdi32.DeleteObject(self._brush_transparent)

			log.info("Dark Mode overlay window destroyed")

		except Exception:
			log.exception("Error in Dark Mode overlay thread")

		self._hwnd = None

	def _window_proc(self, hwnd, msg, wparam, lparam):
		"""Window procedure."""
		if msg == WM_PAINT:
			self._on_paint(hwnd)
			return 0
		elif msg == WM_TIMER:
			self._on_timer()
			return 0
		elif msg == WM_DESTROY:
			user32.PostQuitMessage(0)
			return 0

		return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

	def _on_paint(self, hwnd):
		"""Handle paint message."""
		ps = PAINTSTRUCT()
		hdc = user32.BeginPaint(hwnd, byref(ps))

		if hdc:
			# Get window dimensions
			rect = RECT()
			user32.GetClientRect(hwnd, byref(rect))

			# Fill entire window with black
			user32.FillRect(hdc, byref(rect), self._brush_black)

			# If we have a focus rectangle, cut out a transparent hole
			if self._current_rect:
				focus_rect = RECT()
				# Convert screen coordinates to client coordinates
				left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
				top = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN

				focus_rect.left = self._current_rect[0] - left
				focus_rect.top = self._current_rect[1] - top
				focus_rect.right = self._current_rect[2] - left
				focus_rect.bottom = self._current_rect[3] - top

				# Fill focus area with transparent color (creates the hole)
				user32.FillRect(hdc, byref(focus_rect), self._brush_transparent)

				# Draw border around the focus area
				pen = gdi32.CreatePen(0, 3, self._current_color)  # PS_SOLID, 3px width
				old_pen = gdi32.SelectObject(hdc, pen)
				old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))  # NULL_BRUSH

				gdi32.Rectangle(hdc, focus_rect.left - 3, focus_rect.top - 3,
								focus_rect.right + 3, focus_rect.bottom + 3)

				gdi32.SelectObject(hdc, old_pen)
				gdi32.SelectObject(hdc, old_brush)
				gdi32.DeleteObject(pen)

		user32.EndPaint(hwnd, byref(ps))

	def _on_timer(self):
		"""Update focus rectangle on timer."""
		try:
			# Get focus object location
			focus = api.getFocusObject()
			if focus and hasattr(focus, 'location') and focus.location:
				loc = focus.location
				self._current_rect = (loc.left, loc.top, loc.left + loc.width, loc.top + loc.height)
				self._current_color = COLOR_FOCUS
			else:
				# Try navigator object
				nav = api.getNavigatorObject()
				if nav and hasattr(nav, 'location') and nav.location:
					loc = nav.location
					self._current_rect = (loc.left, loc.top, loc.left + loc.width, loc.top + loc.height)
					self._current_color = COLOR_NAVIGATOR
				else:
					self._current_rect = None

			# Force repaint
			if self._hwnd:
				user32.InvalidateRect(self._hwnd, None, True)

		except Exception:
			pass  # Ignore errors during timer


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""NVDA Global Plugin for Dark Mode."""

	scriptCategory = "Dark Mode"

	def __init__(self):
		super().__init__()
		log.info("Dark Mode plugin initialized")
		self._overlay = None

	def terminate(self):
		"""Called when NVDA is shutting down."""
		if self._overlay:
			self._overlay.stop()
		log.info("Dark Mode plugin terminating")
		super().terminate()

	@script(
		description="Toggle Dark Mode (screen curtain with visible focus)",
		gesture="kb:NVDA+control+alt+d",
	)
	def script_toggleDarkMode(self, gesture):
		"""Toggle the Dark Mode screen curtain on or off."""
		if self._overlay and self._overlay._running:
			self._overlay.stop()
			self._overlay = None
			ui.message("Dark Mode off")
		else:
			self._overlay = DarkModeOverlay()
			if self._overlay.start():
				ui.message("Dark Mode on")
			else:
				ui.message("Failed to start Dark Mode")
				self._overlay = None
