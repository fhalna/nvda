# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2024 NV Access Limited

from typing import Dict

from utils.displayString import DisplayStringStrEnum


class Orientation(DisplayStringStrEnum):
	"""Values to use within NVDA to denote orientation values.
	These describe the orientation of a widget.
	EG aria-orientation
	"""

	UNDEFINED = ""
	HORIZONTAL = "horizontal"
	VERTICAL = "vertical"

	@property
	def _displayStringLabels(self):
		return _orientationLabels


#: Text to use for 'orientation' values. These describe the orientation of a widget.
_orientationLabels: Dict[Orientation, str] = {
	Orientation.UNDEFINED: "",  # There is nothing extra to say for items without explicit orientation.
	# Translators: Presented when a control has horizontal orientation (e.g., a horizontal slider)
	Orientation.HORIZONTAL: _("horizontal"),
	# Translators: Presented when a control has vertical orientation (e.g., a vertical slider)
	Orientation.VERTICAL: _("vertical"),
}
