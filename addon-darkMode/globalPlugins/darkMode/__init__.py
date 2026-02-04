# Dark Mode - Focus Spotlight NVDA Add-on
# A screen curtain that shows only the currently highlighted element
# Copyright (C) 2024 NVDA Dark Mode Contributors
# This file is covered by the GNU General Public License.

"""
Dark Mode global plugin for NVDA.
Provides a screen curtain that blacks out the entire screen except for the
currently focused element (system focus, navigator object, or browse mode cursor).
Toggle with NVDA+Shift+C.
"""

import threading
import weakref
from ctypes import (
	POINTER,
	WINFUNCTYPE,
	WinError,
	byref,
	c_int,
	windll,
)
from ctypes.wintypes import (
	HDC,
	RECT,
	MSG,
)
from typing import NamedTuple, Optional

import api
import core
import globalPluginHandler
import ui
import winGDI
import winUser
import wx
from colors import RGB
from locationHelper import RectLTRB, RectLTWH
from logHandler import log
from mouseHandler import getTotalWidthAndHeightAndMinimumPosition
from scriptHandler import script
from winAPI.messageWindow import WindowMessage
from winBindings import user32
from winBindings.gdi32 import CreateSolidBrush
from windowUtils import CustomWindow


# GDI functions for filling rectangles
gdi32 = windll.gdi32

# FillRect function
_FillRect = WINFUNCTYPE(c_int, HDC, POINTER(RECT), c_int)(("FillRect", windll.user32))


def fillRect(hdc, rect, hBrush):
	"""Fill a rectangle with a brush."""
	winRect = RECT(int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
	return _FillRect(hdc, byref(winRect), hBrush)


# Context enumeration (simplified from vision.constants)
class Context:
	FOCUS = "focus"
	NAVIGATOR = "navigator"
	BROWSEMODE = "browseMode"


class HighlightStyle(NamedTuple):
	"""Represents the style of a highlight for a particular context."""
	color: RGB
	width: int
	style: int
	margin: int


# NVDA's native highlight colors and styles
BLUE = RGB(0x03, 0x36, 0xFF)
PINK = RGB(0xFF, 0x02, 0x66)
YELLOW = RGB(0xFF, 0xDE, 0x03)

DASH_BLUE = HighlightStyle(BLUE, 5, winGDI.DashStyleDash, 5)
SOLID_PINK = HighlightStyle(PINK, 5, winGDI.DashStyleSolid, 5)
SOLID_YELLOW = HighlightStyle(YELLOW, 2, winGDI.DashStyleSolid, 2)

CONTEXT_STYLES = {
	Context.FOCUS: DASH_BLUE,
	Context.NAVIGATOR: SOLID_PINK,
	Context.BROWSEMODE: SOLID_YELLOW,
}


def getObjectRect(obj) -> Optional[RectLTRB]:
	"""Get the screen rectangle of an NVDA object."""
	try:
		location = obj.location
		if location:
			return location.toLTRB()
	except Exception:
		pass
	return None


def getCaretRect() -> Optional[RectLTRB]:
	"""Get the screen rectangle of the browse mode caret."""
	try:
		obj = api.getCaretObject()
		if api.isObjectInActiveTreeInterceptor(obj):
			obj = obj.treeInterceptor

		import textInfos
		try:
			caretInfo = obj.makeTextInfo(textInfos.POSITION_CARET)
		except (NotImplementedError, RuntimeError):
			try:
				caretInfo = obj.makeTextInfo(textInfos.POSITION_SELECTION)
			except (NotImplementedError, RuntimeError):
				return None

		if caretInfo.isCollapsed:
			caretInfo.expand(textInfos.UNIT_CHARACTER)

		try:
			rects = caretInfo.boundingRects
			if rects:
				return rects[0].toLTRB()
		except (NotImplementedError, AttributeError):
			pass

		try:
			return RectLTRB.fromPoint(caretInfo.pointAtStart)
		except Exception:
			pass
	except Exception:
		pass
	return None


def getContextRect(context: str) -> Optional[RectLTRB]:
	"""Get the rectangle for a given context."""
	try:
		if context == Context.FOCUS:
			return getObjectRect(api.getFocusObject())
		elif context == Context.NAVIGATOR:
			return getObjectRect(api.getNavigatorObject())
		elif context == Context.BROWSEMODE:
			if api.isObjectInActiveTreeInterceptor(api.getCaretObject()):
				return getCaretRect()
	except Exception:
		pass
	return None


class DarkModeWindow(CustomWindow):
	"""
	A full-screen overlay window that blacks out everything except
	the current highlight rectangle.
	"""
	transparency = 0xFF
	className = "NVDADarkMode"
	windowName = "NVDA Dark Mode Window"
	windowStyle = winUser.WS_POPUP | winUser.WS_DISABLED
	extendedWindowStyle = (
		winUser.WS_EX_TOPMOST
		| winUser.WS_EX_LAYERED
		| winUser.WS_EX_NOACTIVATE
		| winUser.WS_EX_TRANSPARENT
		| winUser.WS_EX_TOOLWINDOW
	)
	# Magenta as the transparent color (will show through as the "hole")
	transparentColor = 0xFF00FF  # RGB: 255, 0, 255 (magenta)

	@classmethod
	def _get__wClass(cls):
		wClass = super()._wClass
		wClass.style = winUser.CS_HREDRAW | winUser.CS_VREDRAW
		# Black background brush
		wClass.hbrBackground = CreateSolidBrush(0x000000)
		return wClass

	def __init__(self, darkModePlugin: "DarkModePlugin"):
		log.debug("Initializing Dark Mode window")
		super().__init__(
			windowName=self.windowName,
			windowStyle=self.windowStyle,
			extendedWindowStyle=self.extendedWindowStyle,
		)
		self.location = None
		self.pluginRef = weakref.ref(darkModePlugin)
		self._currentRect: Optional[RectLTRB] = None
		self._currentContext: Optional[str] = None

		# Create brush for the transparent "hole"
		self._transparentBrush = CreateSolidBrush(self.transparentColor)

		# Set layered window attributes
		winUser.SetLayeredWindowAttributes(
			self.handle,
			self.transparentColor,
			self.transparency,
			winUser.LWA_ALPHA | winUser.LWA_COLORKEY,
		)
		self.updateLocationForDisplays()
		if not user32.UpdateWindow(self.handle):
			raise WinError()

	def updateLocationForDisplays(self) -> None:
		"""Update window size to cover all displays."""
		log.debug("Updating Dark Mode window location for displays")
		displays = [wx.Display(i).GetGeometry() for i in range(wx.Display.GetCount())]
		screenWidth, screenHeight, minPos = getTotalWidthAndHeightAndMinimumPosition(displays)

		left = minPos.x
		top = minPos.y
		width = screenWidth
		height = screenHeight - 1  # Hack to allow desktop shortcuts to work

		self.location = RectLTWH(left, top, width, height)
		user32.ShowWindow(self.handle, winUser.SW_HIDE)
		if not user32.SetWindowPos(
			self.handle,
			winUser.HWND_TOPMOST,
			left,
			top,
			width,
			height,
			winUser.SWP_NOACTIVATE,
		):
			raise WinError()
		user32.ShowWindow(self.handle, winUser.SW_SHOWNA)
		user32.InvalidateRect(self.handle, None, True)

	def windowProc(self, hwnd: int, msg: int, wParam: int, lParam: int) -> None:
		if msg == winUser.WM_PAINT:
			self._paint()
			# Ensure the window is top most
			user32.SetWindowPos(
				self.handle,
				winUser.HWND_TOPMOST,
				0, 0, 0, 0,
				winUser.SWP_NOACTIVATE | winUser.SWP_NOMOVE | winUser.SWP_NOSIZE,
			)
		elif msg == winUser.WM_DESTROY:
			user32.PostQuitMessage(0)
		elif msg == winUser.WM_TIMER:
			self.refresh()
		elif msg == WindowMessage.DISPLAY_CHANGE:
			core.callLater(100, self.updateLocationForDisplays)

	def _mapRectToClient(self, rect: RectLTRB, margin: int = 0) -> Optional[RectLTRB]:
		"""Transform a screen rectangle to client coordinates."""
		if not self.location:
			return None
		try:
			rect = rect.intersection(self.location)
			return rect.toLogical(self.handle).toClient(self.handle).expandOrShrink(margin)
		except (RuntimeError, ValueError):
			return None

	def _paint(self) -> None:
		"""Paint the dark mode overlay with a transparent hole for the highlight."""
		plugin = self.pluginRef()
		if not plugin:
			user32.PostQuitMessage(0)
			return

		with winUser.paint(self.handle) as hdc:
			# Fill the entire window with black
			if self.location:
				clientRect = RectLTRB(0, 0, self.location.width, self.location.height)
				blackBrush = CreateSolidBrush(0x000000)
				fillRect(hdc, clientRect, blackBrush)
				gdi32.DeleteObject(blackBrush)

			# Get current highlight rectangle
			rect = self._currentRect
			context = self._currentContext

			if rect and context:
				style = CONTEXT_STYLES.get(context, DASH_BLUE)
				clientRect = self._mapRectToClient(rect, style.margin)

				if clientRect:
					# Fill the highlight area with transparent color (creates the "hole")
					fillRect(hdc, clientRect, self._transparentBrush)

					# Draw the highlight border using GDI+
					with winGDI.GDIPlusGraphicsContext(hdc) as graphicsContext:
						with winGDI.GDIPlusPen(
							style.color.toGDIPlusARGB(),
							style.width,
							style.style,
						) as pen:
							winGDI.gdiPlusDrawRectangle(
								graphicsContext,
								pen,
								*clientRect.toLTWH()
							)

	def updateHighlight(self, rect: Optional[RectLTRB], context: Optional[str]) -> None:
		"""Update the current highlight rectangle and trigger a repaint."""
		self._currentRect = rect
		self._currentContext = context
		user32.InvalidateRect(self.handle, None, True)

	def refresh(self) -> None:
		"""Refresh the highlight from current NVDA state."""
		plugin = self.pluginRef()
		if not plugin:
			return

		# Get the most recent context's rectangle
		rect = None
		context = None

		if plugin.lastContext:
			rect = getContextRect(plugin.lastContext)
			context = plugin.lastContext

		# If no rect from last context, try others
		if not rect:
			for ctx in [Context.FOCUS, Context.NAVIGATOR, Context.BROWSEMODE]:
				rect = getContextRect(ctx)
				if rect:
					context = ctx
					break

		if rect != self._currentRect or context != self._currentContext:
			self.updateHighlight(rect, context)


class DarkModePlugin:
	"""Manages the Dark Mode functionality."""

	_refreshInterval = 100  # milliseconds

	def __init__(self):
		self._window: Optional[DarkModeWindow] = None
		self._thread: Optional[threading.Thread] = None
		self._runningEvent = threading.Event()
		self.lastContext: Optional[str] = Context.FOCUS

	def start(self) -> bool:
		"""Start the dark mode overlay."""
		if self._window:
			return True  # Already running

		try:
			winGDI.gdiPlusInitialize()
			self._thread = threading.Thread(
				name="NVDADarkMode",
				target=self._run,
				daemon=True,
			)
			self._runningEvent.clear()
			self._thread.start()

			if not self._runningEvent.wait(0.5):
				log.error("Dark Mode thread failed to start")
				return False

			if not self._thread.is_alive():
				log.error("Dark Mode thread died unexpectedly")
				return False

			# Register for NVDA events
			self._registerEvents()

			log.info("Dark Mode started")
			return True
		except Exception:
			log.exception("Failed to start Dark Mode")
			return False

	def stop(self) -> None:
		"""Stop the dark mode overlay."""
		if not self._thread or not self._window:
			return

		try:
			self._unregisterEvents()

			if self._window and self._window.handle:
				if not user32.PostThreadMessage(self._thread.ident, winUser.WM_QUIT, 0, 0):
					raise WinError()
				self._thread.join(timeout=1.0)

			winGDI.gdiPlusTerminate()
			self._thread = None
			self._window = None
			log.info("Dark Mode stopped")
		except Exception:
			log.exception("Error stopping Dark Mode")

	def _run(self) -> None:
		"""Thread main function."""
		try:
			log.debug("Starting Dark Mode thread")
			self._window = DarkModeWindow(self)
			timer = winUser.WinTimer(self._window.handle, 0, self._refreshInterval, None)
			self._runningEvent.set()

			msg = MSG()
			while (res := winUser.getMessage(byref(msg), None, 0, 0)) > 0:
				user32.TranslateMessage(byref(msg))
				user32.DispatchMessage(byref(msg))

			if res == -1:
				raise WinError()

			log.debug("Dark Mode thread exiting")
			timer.terminate()
			self._window.destroy()
		except Exception:
			log.exception("Exception in Dark Mode thread")

	def _registerEvents(self) -> None:
		"""Register for NVDA focus/review/caret events."""
		try:
			import vision
			if hasattr(vision, 'handler') and vision.handler:
				vision.handler.extensionPoints.post_focusChange.register(self._onFocusChange)
				vision.handler.extensionPoints.post_reviewMove.register(self._onReviewMove)
				vision.handler.extensionPoints.post_browseModeMove.register(self._onBrowseModeMove)
		except Exception:
			log.debug("Could not register vision events, using fallback")

	def _unregisterEvents(self) -> None:
		"""Unregister from NVDA events."""
		try:
			import vision
			if hasattr(vision, 'handler') and vision.handler:
				vision.handler.extensionPoints.post_focusChange.unregister(self._onFocusChange)
				vision.handler.extensionPoints.post_reviewMove.unregister(self._onReviewMove)
				vision.handler.extensionPoints.post_browseModeMove.unregister(self._onBrowseModeMove)
		except Exception:
			pass

	def _onFocusChange(self, obj) -> None:
		"""Handle focus change event."""
		self.lastContext = Context.FOCUS
		if self._window:
			self._window.refresh()

	def _onReviewMove(self, context) -> None:
		"""Handle review/navigator move event."""
		self.lastContext = Context.NAVIGATOR
		if self._window:
			self._window.refresh()

	def _onBrowseModeMove(self, obj=None) -> None:
		"""Handle browse mode cursor move event."""
		self.lastContext = Context.BROWSEMODE
		if self._window:
			self._window.refresh()

	@property
	def isRunning(self) -> bool:
		return self._window is not None and self._thread is not None and self._thread.is_alive()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""NVDA Global Plugin for Dark Mode."""

	scriptCategory = "Dark Mode"

	def __init__(self):
		super().__init__()
		self._darkMode = DarkModePlugin()

	def terminate(self):
		"""Called when NVDA is shutting down."""
		if self._darkMode.isRunning:
			self._darkMode.stop()
		super().terminate()

	@script(
		description="Toggle Dark Mode (screen curtain with visible focus)",
		gesture="kb:NVDA+shift+c",
	)
	def script_toggleDarkMode(self, gesture):
		"""Toggle the Dark Mode screen curtain on or off."""
		if self._darkMode.isRunning:
			self._darkMode.stop()
			# Translators: Announced when Dark Mode is turned off
			ui.message("Dark Mode off")
		else:
			if self._darkMode.start():
				# Translators: Announced when Dark Mode is turned on
				ui.message("Dark Mode on")
			else:
				# Translators: Announced when Dark Mode fails to start
				ui.message("Failed to start Dark Mode")
