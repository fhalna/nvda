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

import globalPluginHandler
import ui
from scriptHandler import script
from logHandler import log

# Log when module loads
log.info("Dark Mode plugin module loading...")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""NVDA Global Plugin for Dark Mode."""

	scriptCategory = "Dark Mode"

	def __init__(self):
		super().__init__()
		log.info("Dark Mode plugin initialized")
		self._enabled = False

	def terminate(self):
		"""Called when NVDA is shutting down."""
		log.info("Dark Mode plugin terminating")
		super().terminate()

	@script(
		description="Toggle Dark Mode (screen curtain with visible focus)",
		gesture="kb:NVDA+alt+d",
	)
	def script_toggleDarkMode(self, gesture):
		"""Toggle the Dark Mode screen curtain on or off."""
		log.info("Dark Mode toggle pressed")
		self._enabled = not self._enabled
		if self._enabled:
			ui.message("Dark Mode on")
		else:
			ui.message("Dark Mode off")
