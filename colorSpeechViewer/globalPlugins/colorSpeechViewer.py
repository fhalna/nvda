# Color Speech Viewer - NVDA Add-on
# A speech viewer with color syntax highlighting
# Copyright (C) 2024 NVDA Community
# GNU General Public License version 2

import globalPluginHandler
import ui
import wx
import config
from speech.extensions import filter_speechSequence
from speech.commands import SpeechCommand
from speech.types import SpeechSequence
import controlTypes
from controlTypes import Role, State
from logHandler import log
from gui import mainFrame, guiHelper
import core
from typing import Set, Dict, Optional


def _buildVocabulary() -> Dict[str, str]:
	"""Build vocabulary of known roles and states with their display strings.

	Returns a dict mapping display strings to their type ('role', 'state', 'orientation', 'current').
	"""
	vocabulary: Dict[str, str] = {}

	# Add all role display strings
	for role in Role:
		try:
			displayString = role.displayString
			if displayString:
				vocabulary[displayString.lower()] = "role"
		except Exception:
			pass

	# Add all state display strings
	for state in State:
		try:
			displayString = state.displayString
			if displayString:
				vocabulary[displayString.lower()] = "state"
			# Also add negative state labels
			negDisplayString = state.negativeDisplayString
			if negDisplayString:
				vocabulary[negDisplayString.lower()] = "state"
		except Exception:
			pass

	# Add orientation values
	try:
		from controlTypes import Orientation
		for orientation in Orientation:
			try:
				displayString = orientation.displayString
				if displayString:
					vocabulary[displayString.lower()] = "orientation"
			except Exception:
				pass
	except ImportError:
		pass

	# Add isCurrent values
	try:
		from controlTypes import IsCurrent
		for current in IsCurrent:
			try:
				displayString = current.displayString
				if displayString:
					vocabulary[displayString.lower()] = "current"
			except Exception:
				pass
	except ImportError:
		pass

	# Add landmark keywords
	try:
		import aria
		for landmarkKey, landmarkDisplay in aria.landmarkRoles.items():
			vocabulary[landmarkKey.lower()] = "landmark"
			vocabulary[landmarkDisplay.lower()] = "landmark"
	except (ImportError, AttributeError):
		pass
	# Fallback landmark keywords if aria module not available
	landmarkKeywords = [
		"banner", "navigation", "main", "complementary",
		"contentinfo", "content info", "search", "form",
		"landmark", "region"
	]
	for kw in landmarkKeywords:
		if kw not in vocabulary:
			vocabulary[kw] = "landmark"

	return vocabulary


# Color definitions (RGB)
COLORS = {
	"role": wx.Colour(50, 120, 200),      # Blue for roles
	"state": wx.Colour(150, 50, 180),     # Purple for states
	"orientation": wx.Colour(180, 100, 50),  # Orange-brown for orientation
	"current": wx.Colour(50, 150, 150),   # Teal for current
	"name": wx.Colour(50, 150, 50),       # Green for names (inferred)
	"landmark": wx.Colour(200, 130, 0),   # Orange for landmarks
	"default": wx.Colour(0, 0, 0),        # Black for unknown
	"message": wx.Colour(100, 100, 100),  # Gray for NVDA messages
}

# Background color for landmarks (light beige)
LANDMARK_BG_COLOR = wx.Colour(255, 245, 220)


class ColorSpeechViewerFrame(wx.Frame):
	"""A speech viewer window with color syntax highlighting."""

	def __init__(self, parent, vocabulary: Dict[str, str]):
		super().__init__(
			parent,
			title="Color Speech Viewer",
			style=wx.CAPTION | wx.RESIZE_BORDER | wx.CLOSE_BOX | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX,
		)
		self.vocabulary = vocabulary
		self._isDestroyed = False

		# Create panel and sizer
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		# Create rich text control
		self.textCtrl = wx.TextCtrl(
			panel,
			style=wx.TE_RICH2 | wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
		)

		# Pre-create fonts ONCE for performance (avoid creating new Font objects per call)
		self._normalFont = wx.Font(
			10,
			wx.FONTFAMILY_TELETYPE,
			wx.FONTSTYLE_NORMAL,
			wx.FONTWEIGHT_NORMAL,
		)
		self._boldFont = wx.Font(self._normalFont)
		self._boldFont.SetWeight(wx.FONTWEIGHT_BOLD)
		self.textCtrl.SetFont(self._normalFont)

		# Pre-create ALL TextAttr objects ONCE for performance
		self._textAttrs = {
			"role": wx.TextAttr(COLORS["role"]),
			"state": wx.TextAttr(COLORS["state"]),
			"orientation": wx.TextAttr(COLORS["orientation"]),
			"current": wx.TextAttr(COLORS["current"]),
			"message": wx.TextAttr(COLORS["message"]),
			"default": wx.TextAttr(COLORS["default"]),
		}
		# Name: green + bold
		nameAttr = wx.TextAttr(COLORS["name"])
		nameAttr.SetFont(self._boldFont)
		self._textAttrs["name"] = nameAttr
		# Landmark: orange + background
		landmarkAttr = wx.TextAttr(COLORS["landmark"])
		landmarkAttr.SetBackgroundColour(LANDMARK_BG_COLOR)
		self._textAttrs["landmark"] = landmarkAttr

		sizer.Add(self.textCtrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

		# Add legend
		legendSizer = wx.BoxSizer(wx.HORIZONTAL)
		legendItems = [
			("Role", COLORS["role"], None, False),
			("State", COLORS["state"], None, False),
			("Name", COLORS["name"], None, True),  # Bold
			("Landmark", COLORS["landmark"], LANDMARK_BG_COLOR, False),  # With background
			("Message", COLORS["message"], None, False),
		]
		for label, fgColor, bgColor, bold in legendItems:
			legendText = wx.StaticText(panel, label=f" {label} ")
			legendText.SetForegroundColour(fgColor)
			if bgColor:
				legendText.SetBackgroundColour(bgColor)
			if bold:
				font = legendText.GetFont()
				font.SetWeight(wx.FONTWEIGHT_BOLD)
				legendText.SetFont(font)
			legendSizer.Add(legendText, flag=wx.LEFT, border=5)

		sizer.Add(legendSizer, flag=wx.ALL, border=5)

		# Add clear button
		buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
		clearButton = wx.Button(panel, label="Clear")
		clearButton.Bind(wx.EVT_BUTTON, self.onClear)
		buttonSizer.Add(clearButton, flag=wx.ALL, border=5)

		sizer.Add(buttonSizer, flag=wx.ALIGN_RIGHT)

		panel.SetSizer(sizer)

		# Set window size
		self.SetSize(600, 400)

		# Bind close event
		self.Bind(wx.EVT_CLOSE, self.onClose)

	def onClear(self, event):
		"""Clear the text control."""
		self.textCtrl.Clear()

	def onClose(self, event):
		"""Handle window close."""
		self.Hide()

	def appendSpeech(self, speechSequence: SpeechSequence, isMessage: bool = False):
		"""Append speech to the viewer with color highlighting."""
		if self._isDestroyed:
			return

		# Extract text items from the sequence
		textItems = [item for item in speechSequence if isinstance(item, str)]

		if not textItems:
			return

		for text in textItems:
			self._appendColoredText(text, isMessage)
			self._appendColoredText("  ", isMessage=False)  # Separator

		# Add newline at end
		self.textCtrl.AppendText("\n")

	def _appendColoredText(self, text: str, isMessage: bool = False):
		"""Append text with appropriate color based on vocabulary matching."""
		if not text.strip():
			self.textCtrl.AppendText(text)
			return

		startPos = self.textCtrl.GetLastPosition()
		self.textCtrl.AppendText(text)
		endPos = self.textCtrl.GetLastPosition()

		# Determine text type
		textType = None
		if isMessage:
			textType = "message"
		else:
			textLower = text.lower().strip()
			textType = self.vocabulary.get(textLower)

			if not textType:
				# Check if any word in the text is a known role/state/landmark
				words = textLower.split()
				for word in words:
					wordType = self.vocabulary.get(word)
					if wordType:
						textType = wordType
						break

			if not textType:
				# Assume it's a name if it's a single text segment not matching anything
				textType = "name"

		# Use pre-created TextAttr - NO new object creation for performance!
		textAttr = self._textAttrs.get(textType, self._textAttrs["default"])
		self.textCtrl.SetStyle(startPos, endPos, textAttr)

	def destroy(self):
		"""Safely destroy the frame."""
		self._isDestroyed = True
		self.Destroy()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Global plugin for Color Speech Viewer."""

	def __init__(self):
		super().__init__()
		self._viewerFrame: Optional[ColorSpeechViewerFrame] = None
		self._vocabulary = _buildVocabulary()
		self._isActive = False

		log.debug(f"ColorSpeechViewer: Built vocabulary with {len(self._vocabulary)} entries")

	def terminate(self):
		"""Clean up when plugin terminates."""
		self._deactivate()

	def _activate(self):
		"""Activate the speech viewer."""
		if self._isActive:
			return

		try:
			# Register for speech events (using filter_speechSequence for NVDA 2024.4.x compatibility)
			filter_speechSequence.register(self._onSpeechFilter)

			# Create viewer frame
			if not self._viewerFrame:
				self._viewerFrame = ColorSpeechViewerFrame(mainFrame, self._vocabulary)

			self._viewerFrame.Show()
			self._viewerFrame.Raise()
			self._viewerFrame.Centre()
			self._isActive = True

			ui.message("Color Speech Viewer activated")
			log.info("ColorSpeechViewer: Window activated successfully")

			# Show confirmation popup
			wx.CallAfter(
				wx.MessageBox,
				"Color Speech Viewer is now active!\n\nNavigate around and speech will be logged in the viewer window with color highlighting.",
				"Color Speech Viewer",
				wx.OK | wx.ICON_INFORMATION
			)

		except Exception as e:
			log.error(f"ColorSpeechViewer: Failed to activate - {e}")
			# Show error popup
			wx.CallAfter(
				wx.MessageBox,
				f"Color Speech Viewer failed to start:\n\n{e}",
				"Color Speech Viewer Error",
				wx.OK | wx.ICON_ERROR
			)

	def _deactivate(self):
		"""Deactivate the speech viewer."""
		if not self._isActive:
			return

		# Unregister from speech events
		try:
			filter_speechSequence.unregister(self._onSpeechFilter)
		except Exception:
			pass

		# Hide viewer frame
		if self._viewerFrame:
			try:
				self._viewerFrame.destroy()
			except Exception:
				pass
			self._viewerFrame = None

		self._isActive = False

	def _onSpeechFilter(self, speechSequence: SpeechSequence) -> SpeechSequence:
		"""Filter callback for speech - logs to viewer and returns sequence unchanged."""
		if self._isActive and self._viewerFrame:
			# Determine if this is a simple message (no commands, just text)
			hasCommands = any(isinstance(item, SpeechCommand) for item in speechSequence)
			isSimpleMessage = not hasCommands and len(speechSequence) == 1

			# Append to viewer
			wx.CallAfter(self._viewerFrame.appendSpeech, speechSequence, isMessage=isSimpleMessage)

		# Filter must return the sequence (unchanged)
		return speechSequence

	def script_toggleColorSpeechViewer(self, gesture):
		"""Toggle the Color Speech Viewer window."""
		if self._isActive:
			self._deactivate()
			ui.message("Color Speech Viewer deactivated")
			wx.CallAfter(
				wx.MessageBox,
				"Color Speech Viewer has been deactivated.",
				"Color Speech Viewer",
				wx.OK | wx.ICON_INFORMATION
			)
		else:
			self._activate()

	script_toggleColorSpeechViewer.__doc__ = "Toggle the Color Speech Viewer"
	script_toggleColorSpeechViewer.category = "Tools"

	__gestures = {
		"kb:NVDA+shift+v": "toggleColorSpeechViewer",
	}
