# Color Speech Viewer - NVDA Add-on
# A speech viewer with color syntax highlighting
# Copyright (C) 2024 NVDA Community
# GNU General Public License version 2

import globalPluginHandler
import ui
import wx
import config
from speech.extensions import pre_speechQueued, post_speechCanceled
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

	return vocabulary


# Color definitions (RGB)
COLORS = {
	"role": wx.Colour(50, 120, 200),      # Blue for roles
	"state": wx.Colour(150, 50, 180),     # Purple for states
	"orientation": wx.Colour(180, 100, 50),  # Orange-brown for orientation
	"current": wx.Colour(50, 150, 150),   # Teal for current
	"name": wx.Colour(50, 150, 50),       # Green for names (inferred)
	"default": wx.Colour(0, 0, 0),        # Black for unknown
	"message": wx.Colour(100, 100, 100),  # Gray for NVDA messages
}


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

		# Set default font
		font = wx.Font(
			10,
			wx.FONTFAMILY_TELETYPE,
			wx.FONTSTYLE_NORMAL,
			wx.FONTWEIGHT_NORMAL,
		)
		self.textCtrl.SetFont(font)

		sizer.Add(self.textCtrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

		# Add legend
		legendSizer = wx.BoxSizer(wx.HORIZONTAL)
		legendItems = [
			("Role", COLORS["role"]),
			("State", COLORS["state"]),
			("Name", COLORS["name"]),
			("Message", COLORS["message"]),
		]
		for label, color in legendItems:
			legendText = wx.StaticText(panel, label=f" {label} ")
			legendText.SetForegroundColour(color)
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

		# Determine color
		if isMessage:
			color = COLORS["message"]
		else:
			textLower = text.lower().strip()
			textType = self.vocabulary.get(textLower)

			if textType:
				color = COLORS.get(textType, COLORS["default"])
			else:
				# Check if any word in the text is a known role/state
				words = textLower.split()
				foundType = None
				for word in words:
					wordType = self.vocabulary.get(word)
					if wordType:
						foundType = wordType
						break

				if foundType:
					color = COLORS.get(foundType, COLORS["default"])
				else:
					# Assume it's a name if it's a single text segment not matching anything
					color = COLORS["name"]

		# Apply color
		textAttr = wx.TextAttr(color)
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
			# Register for speech events
			pre_speechQueued.register(self._onSpeechQueued)

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
			pre_speechQueued.unregister(self._onSpeechQueued)
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

	def _onSpeechQueued(self, speechSequence: SpeechSequence, priority):
		"""Handle speech queued event."""
		if not self._isActive or not self._viewerFrame:
			return

		# Determine if this is a simple message (no commands, just text)
		hasCommands = any(isinstance(item, SpeechCommand) for item in speechSequence)
		isSimpleMessage = not hasCommands and len(speechSequence) == 1

		# Append to viewer
		wx.CallAfter(self._viewerFrame.appendSpeech, speechSequence, isMessage=isSimpleMessage)

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
