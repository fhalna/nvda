"""
Convert HTML to NVDA browse mode output.

Simulates what NVDA announces in browse mode (virtual buffer) when
navigating a web page with the down arrow key. Parses real HTML and
produces a list of text lines matching NVDA's speech output.

This module is useful for:
- Testing the MCP server without running NVDA
- Demonstrating what an AI would see on any web page
- Automated accessibility analysis

Coverage includes: landmarks, headings, links, tables (with row/column
counts and cell coordinates), lists (with nesting level), forms (all
input types), ARIA roles, ARIA states/properties, label resolution
(for/aria-labelledby/aria-describedby), semantic text formatting,
interactive HTML5 elements (details/summary, dialog), media elements,
and language change announcements.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# ARIA role → French announcement
# ---------------------------------------------------------------------------

LANDMARK_ROLES: dict[str, str] = {
	"banner": "bannière",
	"navigation": "navigation",
	"main": "principale",
	"contentinfo": "information sur le contenu",
	"complementary": "complémentaire",
	"search": "recherche",
	"form": "formulaire",
	"region": "région",
}

# controlTypes.Role.LANDMARK.displayString in French = "région"
LANDMARK_DISPLAY = "région"

# Other ARIA widget / document / structure roles
ARIA_ROLE_LABELS: dict[str, str] = {
	# Widgets
	"alert": "alerte",
	"alertdialog": "dialogue d'alerte",
	"application": "application",
	"button": "bouton",
	"checkbox": "case à cocher",
	"combobox": "liste déroulante",
	"dialog": "dialogue",
	"grid": "grille",
	"gridcell": "cellule de grille",
	"link": "lien",
	"listbox": "liste",
	"log": "journal",
	"marquee": "défilement",
	"menu": "menu",
	"menubar": "barre de menu",
	"menuitem": "élément de menu",
	"menuitemcheckbox": "élément de menu à cocher",
	"menuitemradio": "élément de menu radio",
	"option": "option",
	"progressbar": "barre de progression",
	"radio": "bouton radio",
	"radiogroup": "groupe de boutons radio",
	"scrollbar": "barre de défilement",
	"separator": "séparateur",
	"slider": "potentiomètre",
	"spinbutton": "bouton rotatif",
	"status": "barre d'état",
	"switch": "bascule",
	"tab": "onglet",
	"tablist": "onglet",
	"tabpanel": "page de propriété",
	"textbox": "édition",
	"timer": "minuteur",
	"toolbar": "barre d'outils",
	"tooltip": "infobulle",
	"tree": "arborescence",
	"treeitem": "élément d'arborescence",
	"treegrid": "grille arborescente",
	# Document structure roles
	"article": "article",
	"cell": "cellule",
	"columnheader": "en-tête de colonne",
	"definition": "définition",
	"directory": "répertoire",
	"document": "document",
	"feed": "flux",
	"figure": "figure",
	"group": "groupe",
	"heading": "titre",
	"img": "graphique",
	"list": "liste",
	"listitem": "élément de liste",
	"math": "math",
	"none": "",
	"note": "note",
	"presentation": "",
	"row": "ligne",
	"rowgroup": "groupe de lignes",
	"rowheader": "en-tête de ligne",
	"table": "tableau",
	"term": "terme",
}

# HTML5 elements that map to implicit ARIA landmarks
IMPLICIT_LANDMARKS: dict[str, str] = {
	"header": "banner",
	"nav": "navigation",
	"main": "main",
	"footer": "contentinfo",
	"aside": "complementary",
	"form": "form",
	"search": "search",
}

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

# Block elements that cause line breaks in NVDA
BLOCK_ELEMENTS = {
	"div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
	"ul", "ol", "li", "dl", "dt", "dd",
	"table", "tr", "th", "td", "caption",
	"blockquote", "pre", "figure", "figcaption",
	"section", "article", "header", "footer", "nav", "main", "aside",
	"form", "fieldset", "legend",
	"details", "summary",
	"hr", "br",
	"address",
	"dialog",
	"output", "progress", "meter",
}

# Elements to skip entirely (including <head> contents)
SKIP_ELEMENTS = {
	"script", "style", "noscript", "template", "svg", "path",
	"meta", "link", "head", "title",
}

# Inline elements that don't cause line breaks
INLINE_ELEMENTS = {
	"a", "span", "strong", "em", "b", "i", "u", "s", "small",
	"mark", "abbr", "code", "time", "sub", "sup", "kbd", "samp",
	"var", "cite", "q", "dfn", "ins", "del", "bdi", "bdo", "data",
	"ruby", "rt", "rp", "wbr",
}

# ---------------------------------------------------------------------------
# Helpers for ARIA state announcements
# ---------------------------------------------------------------------------

_ARIA_STATE_ANNOUNCEMENTS: dict[str, dict[str, str]] = {
	"aria-expanded": {"true": "développé", "false": "réduit"},
	"aria-checked": {"true": "coché", "false": "non coché", "mixed": "semi-coché"},
	"aria-selected": {"true": "sélectionné", "false": "non sélectionné"},
	"aria-pressed": {"true": "enfoncé", "false": "non enfoncé", "mixed": "à moitié enfoncé"},
	"aria-disabled": {"true": "non disponible"},
	"aria-required": {"true": "obligatoire"},
	"aria-invalid": {"true": "entrée invalide", "grammar": "erreur de grammaire", "spelling": "erreur d'orthographe"},
	"aria-current": {
		"true": "en cours",
		"page": "page courante",
		"step": "étape courante",
		"location": "position courante",
		"date": "date actuelle",
		"time": "heure actuelle",
	},
	"aria-haspopup": {
		"true": "sous-menu",
		"menu": "sous-menu",
		"dialog": "ouvre un dialogue",
		"listbox": "ouvre une liste",
		"tree": "ouvre une arborescence",
		"grid": "ouvre une grille",
	},
	"aria-readonly": {"true": "en lecture seule"},
	"aria-busy": {"true": "occupé"},
	"aria-grabbed": {"true": "attrapé", "false": "peut être attrapé"},
	"aria-dropeffect": {
		"copy": "déposer pour copier",
		"move": "déposer pour déplacer",
		"link": "déposer pour lier",
		"execute": "déposer pour exécuter",
		"popup": "déposer pour popup",
	},
	"aria-sort": {
		"ascending": "trié par ordre croissant",
		"descending": "trié par ordre décroissant",
		"other": "trié",
	},
	"aria-autocomplete": {
		"inline": "autocomplétion",
		"list": "autocomplétion",
		"both": "autocomplétion",
	},
	"aria-orientation": {
		"horizontal": "horizontal",
		"vertical": "vertical",
	},
	"aria-multiselectable": {"true": "sélection multiple"},
	"aria-multiline": {"true": "multi-lignes"},
}

# Input type → French label used by NVDA
_INPUT_TYPE_LABELS: dict[str, str] = {
	"text": "édition",
	"email": "édition",
	"url": "édition",
	"tel": "édition",
	"password": "édition du mot de passe",
	"number": "édition",
	"search": "édition",
	"date": "édition",
	"time": "édition",
	"datetime-local": "édition",
	"month": "édition",
	"week": "édition",
	"color": "bouton",
	"range": "potentiomètre",
	"file": "bouton",
	"hidden": "",
}


class NVDABrowseModeParser(HTMLParser):
	"""Parse HTML and produce NVDA-like browse mode output.

	Two-pass design
	---------------
	Pass 1 (feed):  Walk the DOM, collect elements into an internal tree and
	                 build look-up tables (id → text, label-for mappings).
	Pass 2 (get_lines):  Flatten the tree to produce the final list of
	                 announcement lines, resolving cross-references.
	"""

	def __init__(self) -> None:
		super().__init__()
		# Output lines
		self.lines: list[str] = []
		self._current_line: list[str] = []

		# Tag stack for context tracking
		self._tag_stack: list[dict] = []
		self._skip_depth: int = 0

		# Links
		self._in_a: bool = False
		self._a_has_img: bool = False
		self._a_text: list[str] = []
		self._img_alt_in_link: str = ""
		self._a_attrs: dict = {}

		# Landmarks
		self._landmark_stack: list[str] = []

		# Lists (supports nesting)
		self._list_stack: list[dict] = []

		# Tables (supports nesting)
		self._table_stack: list[dict] = []

		# Label resolution  (pass-1 collection)
		self._id_to_element: dict[str, dict] = {}  # id → {tag, attrs, text}
		self._label_for_map: dict[str, str] = {}    # for-id → label text
		self._current_label_for: str | None = None
		self._current_label_text: list[str] = []

		# details/summary
		self._in_summary: bool = False
		self._details_stack: list[dict] = []

		# Text formatting context
		self._format_stack: list[str] = []

		# Language tracking
		self._lang_stack: list[str] = []

		# Collect all element texts by id for aria-labelledby / aria-describedby
		self._id_text_collector: dict[str, list[str]] = {}
		self._current_id_targets: list[str] = []  # stack of ids being collected

		# Pre-formatted text
		self._pre_depth: int = 0

	# ------------------------------------------------------------------
	# Low-level helpers
	# ------------------------------------------------------------------

	def _flush_line(self) -> None:
		"""Flush the current accumulated text as a line."""
		text = " ".join(self._current_line).strip()
		if text:
			self.lines.append(text)
		self._current_line = []

	def _add_text(self, text: str) -> None:
		"""Add text to the current line."""
		text = text.strip()
		if text:
			self._current_line.append(text)

	# ------------------------------------------------------------------
	# ARIA helpers
	# ------------------------------------------------------------------

	def _get_landmark_role(self, tag: str, attrs: dict) -> str | None:
		"""Determine the ARIA landmark role for an element."""
		role = attrs.get("role", "")
		if role in LANDMARK_ROLES:
			return role
		if tag in IMPLICIT_LANDMARKS:
			if tag in ("header", "footer"):
				for item in self._tag_stack:
					if item["tag"] in ("article", "section", "aside"):
						return None
			return IMPLICIT_LANDMARKS[tag]
		return None

	def _collect_aria_states(self, attrs: dict) -> list[str]:
		"""Return list of French announcements for ARIA states on *attrs*."""
		parts: list[str] = []
		for aria_attr, mapping in _ARIA_STATE_ANNOUNCEMENTS.items():
			val = attrs.get(aria_attr, "")
			if val and val in mapping and mapping[val]:
				parts.append(mapping[val])
		return parts

	def _get_aria_value_text(self, attrs: dict) -> str:
		"""Build value announcement for sliders / progress / spinbuttons."""
		vtext = attrs.get("aria-valuetext", "")
		if vtext:
			return vtext
		vnow = attrs.get("aria-valuenow", "")
		vmin = attrs.get("aria-valuemin", "")
		vmax = attrs.get("aria-valuemax", "")
		if vnow:
			parts = [vnow]
			if vmin and vmax:
				parts.append(f"de {vmin} à {vmax}")
			return " ".join(parts)
		return ""

	def _resolve_label(self, attrs: dict) -> str:
		"""Resolve the accessible name for a form control.

		Priority: aria-labelledby > aria-label > associated <label for> >
		          placeholder > title.
		"""
		# aria-labelledby
		labelledby = attrs.get("aria-labelledby", "")
		if labelledby:
			parts = []
			for ref_id in labelledby.split():
				ref_text = self._resolve_id_text(ref_id)
				if ref_text:
					parts.append(ref_text)
			if parts:
				return " ".join(parts)

		# aria-label
		aria_label = attrs.get("aria-label", "")
		if aria_label:
			return aria_label

		# <label for="…">
		elem_id = attrs.get("id", "")
		if elem_id and elem_id in self._label_for_map:
			return self._label_for_map[elem_id]

		# placeholder / title fallback
		return attrs.get("placeholder", attrs.get("title", ""))

	def _resolve_description(self, attrs: dict) -> str:
		"""Resolve aria-describedby."""
		describedby = attrs.get("aria-describedby", "")
		if describedby:
			parts = []
			for ref_id in describedby.split():
				ref_text = self._resolve_id_text(ref_id)
				if ref_text:
					parts.append(ref_text)
			if parts:
				return " ".join(parts)
		return ""

	def _resolve_id_text(self, ref_id: str) -> str:
		"""Get text content for an element by its id."""
		if ref_id in self._id_text_collector:
			return " ".join(self._id_text_collector[ref_id]).strip()
		if ref_id in self._id_to_element:
			return self._id_to_element[ref_id].get("text", "")
		return ""

	def _announce_description(self, attrs: dict) -> None:
		"""Append aria-describedby description if present."""
		desc = self._resolve_description(attrs)
		if desc:
			self._add_text(desc)

	def _get_accessible_name(self, tag: str, attrs: dict) -> str:
		"""Compute accessible name via aria-label / aria-labelledby."""
		labelledby = attrs.get("aria-labelledby", "")
		if labelledby:
			parts = []
			for ref_id in labelledby.split():
				ref_text = self._resolve_id_text(ref_id)
				if ref_text:
					parts.append(ref_text)
			if parts:
				return " ".join(parts)
		return attrs.get("aria-label", "")

	# ------------------------------------------------------------------
	# handle_starttag
	# ------------------------------------------------------------------

	def handle_starttag(self, tag: str, attrs_list: list) -> None:  # noqa: C901
		attrs = dict(attrs_list)
		tag_info = {"tag": tag, "attrs": attrs}
		self._tag_stack.append(tag_info)

		# Track element id for later reference resolution
		elem_id = attrs.get("id", "")
		if elem_id:
			self._id_to_element[elem_id] = {"tag": tag, "attrs": attrs, "text": ""}
			self._current_id_targets.append(elem_id)

		# --- Skip hidden / non-visual elements ---
		if "hidden" in attrs or attrs.get("aria-hidden") == "true":
			self._skip_depth += 1
			return
		if self._skip_depth > 0:
			return
		if tag in SKIP_ELEMENTS:
			self._skip_depth += 1
			return

		# --- Language change ---
		lang = attrs.get("lang", attrs.get("xml:lang", ""))
		if lang:
			if self._lang_stack and self._lang_stack[-1] != lang:
				self._flush_line()
				# Map common codes
				lang_names = {
					"fr": "français", "en": "anglais", "de": "allemand",
					"es": "espagnol", "it": "italien", "pt": "portugais",
					"nl": "néerlandais", "ja": "japonais", "zh": "chinois",
					"ar": "arabe", "ru": "russe", "ko": "coréen",
				}
				name = lang_names.get(lang.split("-")[0], lang)
				self.lines.append(f"langue : {name}")
			self._lang_stack.append(lang)

		# --- ARIA role handling (non-landmark widget/structure roles) ---
		role = attrs.get("role", "")
		if role and role not in LANDMARK_ROLES:
			self._handle_aria_role_start(tag, attrs, role)

		# --- Landmark handling ---
		landmark = self._get_landmark_role(tag, attrs)
		if landmark:
			self._flush_line()
			landmark_type = LANDMARK_ROLES.get(landmark, landmark)
			# NVDA format: "{landmarkType} région"
			# For CARET reason (line nav), name is NOT announced
			self.lines.append(f"{landmark_type} {LANDMARK_DISPLAY}")
			self._landmark_stack.append(landmark_type)

		# --- Block elements cause line breaks ---
		if tag in BLOCK_ELEMENTS:
			self._flush_line()

		# --- Text formatting (inline semantic) ---
		self._handle_format_start(tag, attrs)

		# --- Headings ---
		if tag in HEADING_TAGS:
			level = tag[1]
			self._add_text(f"titre de niveau {level}")

		# --- Links ---
		if tag == "a":
			# In NVDA, each link is on its own line — but when a link is
			# the direct child of a heading, it stays on the same line
			# (e.g. "titre de niveau 3  lien Audit").
			parent_tag = self._tag_stack[-2]["tag"] if len(self._tag_stack) >= 2 else ""
			if parent_tag not in HEADING_TAGS:
				self._flush_line()
			self._in_a = True
			self._a_has_img = False
			self._a_text = []
			self._img_alt_in_link = ""
			self._a_attrs = attrs

		# --- Images ---
		if tag == "img":
			alt = attrs.get("alt")
			role_attr = attrs.get("role", "")
			if role_attr in ("presentation", "none"):
				pass  # decorative, skip
			elif self._in_a:
				self._a_has_img = True
				self._img_alt_in_link = alt or ""
			elif alt is None:
				# No alt attribute at all – NVDA announces the src
				src = attrs.get("src", "")
				self._add_text(f"graphique {src}")
			elif alt == "":
				pass  # explicitly decorative
			else:
				self._add_text(f"graphique {alt}")
				self._announce_description(attrs)

		# --- Lists ---
		if tag in ("ul", "ol"):
			self._flush_line()
			level = len(self._list_stack) + 1
			self._list_stack.append({
				"tag": tag, "count": 0, "start_index": len(self.lines), "level": level,
			})

		if tag == "li":
			self._flush_line()
			if self._list_stack:
				self._list_stack[-1]["count"] += 1
				# For ordered lists announce item number
				info = self._list_stack[-1]
				if info["tag"] == "ol":
					self._add_text(f"{info['count']}.")

		# Definition lists
		if tag == "dl":
			self._flush_line()

		if tag == "dt":
			self._flush_line()
			self._add_text("terme")

		if tag == "dd":
			self._flush_line()
			self._add_text("définition")

		# --- Tables ---
		if tag == "table":
			self._flush_line()
			label = self._get_accessible_name(tag, attrs) or attrs.get("summary", "")
			# Insert placeholder line – will be replaced with dimensions at end
			if label:
				self.lines.append(f"tableau {label}")
			else:
				self.lines.append("tableau")
			self._table_stack.append({
				"label": label,
				"row": 0, "col": 0,
				"total_rows": 0, "total_cols": 0,
				"current_row_cols": 0,
				"max_cols": 0,
				"header_cells": {},  # (row, col) → text
				"in_thead": False,
				"started": True,
			})

		if tag == "thead" and self._table_stack:
			self._table_stack[-1]["in_thead"] = True

		if tag == "tbody" and self._table_stack:
			self._table_stack[-1]["in_thead"] = False

		if tag == "tfoot" and self._table_stack:
			self._table_stack[-1]["in_thead"] = False

		if tag == "caption":
			self._flush_line()

		if tag == "tr":
			self._flush_line()
			if self._table_stack:
				t = self._table_stack[-1]
				t["row"] += 1
				t["total_rows"] = max(t["total_rows"], t["row"])
				t["col"] = 0
				t["current_row_cols"] = 0

		if tag in ("th", "td"):
			self._flush_line()
			if self._table_stack:
				t = self._table_stack[-1]
				t["col"] += 1
				t["current_row_cols"] += 1
				t["max_cols"] = max(t["max_cols"], t["current_row_cols"])
				row, col = t["row"], t["col"]
				self._add_text(f"ligne {row} colonne {col}")
				if tag == "th":
					self._add_text("en-tête de colonne")

		# --- Labels ---
		if tag == "label":
			self._flush_line()
			for_id = attrs.get("for", "")
			if for_id:
				self._current_label_for = for_id
				self._current_label_text = []

		# --- Form controls ---
		self._handle_form_control_start(tag, attrs)

		# --- details / summary ---
		if tag == "details":
			self._flush_line()
			is_open = "open" in attrs
			self._details_stack.append({"open": is_open})

		if tag == "summary":
			self._flush_line()
			self._in_summary = True

		# --- dialog ---
		if tag == "dialog":
			self._flush_line()
			label = self._get_accessible_name(tag, attrs)
			if label:
				self.lines.append(f"dialogue {label}")
			else:
				self.lines.append("dialogue")

		# --- Separators ---
		if tag == "hr":
			self.lines.append("séparateur")

		if tag == "br":
			self._flush_line()

		# --- Blockquote ---
		if tag == "blockquote":
			cite = attrs.get("cite", "")
			self._add_text("citation")
			if cite:
				self._add_text(f"source {cite}")

		# --- Pre-formatted ---
		if tag == "pre":
			self._pre_depth += 1

		# --- figure ---
		if tag == "figure":
			self._flush_line()
			label = self._get_accessible_name(tag, attrs)
			if label:
				self.lines.append(f"figure {label}")
			else:
				self.lines.append("figure")

		# --- Media elements ---
		if tag == "video":
			self._flush_line()
			label = self._get_accessible_name(tag, attrs) or ""
			self.lines.append(f"vidéo {label}".strip())

		if tag == "audio":
			self._flush_line()
			label = self._get_accessible_name(tag, attrs) or ""
			self.lines.append(f"audio {label}".strip())

		if tag == "iframe":
			self._flush_line()
			frame_title = attrs.get("title", attrs.get("aria-label", ""))
			if frame_title:
				self.lines.append(f"cadre {frame_title}")
			else:
				src = attrs.get("src", "")
				self.lines.append(f"cadre {src}")

		# --- abbr with title ---
		if tag == "abbr":
			abbr_title = attrs.get("title", "")
			if abbr_title:
				self._add_text(f"abréviation")

		# --- Clickable (role=button on non-button elements, onclick) ---
		if role == "button" and tag != "button":
			pass  # already handled by ARIA role handler
		elif any(a.startswith("onclick") or a.startswith("on-click") for a in attrs):
			self._add_text("cliquable")

		# --- MathML ---
		if tag == "math":
			self._flush_line()
			alt = attrs.get("alttext", attrs.get("aria-label", ""))
			if alt:
				self.lines.append(f"math {alt}")
			else:
				self.lines.append("math")

	# ------------------------------------------------------------------
	# ARIA widget role handler (start)
	# ------------------------------------------------------------------

	def _handle_aria_role_start(self, tag: str, attrs: dict, role: str) -> None:
		"""Handle opening of elements with explicit ARIA widget/structure roles."""
		label = self._get_accessible_name(tag, attrs)
		states = self._collect_aria_states(attrs)
		value_text = self._get_aria_value_text(attrs)
		role_label = ARIA_ROLE_LABELS.get(role, role)

		# Roles that are purely presentational produce no output
		if not role_label:
			return

		# Group-like roles: announce role + label + states
		if role in (
			"group", "radiogroup", "toolbar", "tablist", "menubar",
			"menu", "tree", "treegrid", "feed", "log", "status",
			"timer", "marquee", "alert", "note", "directory",
		):
			self._flush_line()
			parts = []
			if label:
				parts.append(label)
			parts.append(role_label)
			parts.extend(states)
			self.lines.append(" ".join(parts))
			return

		# Tab / treeitem / menuitem: inline announcement
		if role in ("tab", "treeitem", "menuitem", "menuitemcheckbox", "menuitemradio", "option"):
			self._flush_line()
			parts = [role_label]
			if label:
				parts.append(label)
			parts.extend(states)
			if value_text:
				parts.append(value_text)
			aria_level = attrs.get("aria-level", "")
			if aria_level:
				parts.append(f"niveau {aria_level}")
			aria_posinset = attrs.get("aria-posinset", "")
			aria_setsize = attrs.get("aria-setsize", "")
			if aria_posinset and aria_setsize:
				parts.append(f"{aria_posinset} sur {aria_setsize}")
			self._add_text(" ".join(parts))
			return

		# Dialog-like
		if role in ("dialog", "alertdialog"):
			self._flush_line()
			parts = [role_label]
			if label:
				parts.append(label)
			parts.extend(states)
			self.lines.append(" ".join(parts))
			return

		# Slider / spinbutton / progressbar / scrollbar: value-bearing
		if role in ("slider", "spinbutton", "progressbar", "scrollbar"):
			self._flush_line()
			parts = [role_label]
			if label:
				parts.append(label)
			if value_text:
				parts.append(value_text)
			parts.extend(states)
			self._add_text(" ".join(parts))
			return

		# Switch
		if role == "switch":
			self._flush_line()
			parts = []
			if label:
				parts.append(label)
			parts.append("bascule")
			checked = attrs.get("aria-checked", "false")
			parts.append("activé" if checked == "true" else "désactivé")
			parts.extend(s for s in states if s not in ("coché", "non coché"))
			self._add_text(" ".join(parts))
			return

		# Tooltip
		if role == "tooltip":
			self._flush_line()
			parts = ["infobulle"]
			if label:
				parts.append(label)
			self._add_text(" ".join(parts))
			return

		# Tabpanel
		if role == "tabpanel":
			self._flush_line()
			parts = ["page de propriété"]
			if label:
				parts.append(label)
			self.lines.append(" ".join(parts))
			return

		# Application
		if role == "application":
			self._flush_line()
			parts = ["application"]
			if label:
				parts.append(label)
			self.lines.append(" ".join(parts))
			return

		# Figure
		if role == "figure":
			self._flush_line()
			if label:
				self.lines.append(f"figure {label}")
			else:
				self.lines.append("figure")
			return

		# Heading with aria-level
		if role == "heading":
			level = attrs.get("aria-level", "2")
			self._flush_line()
			self._add_text(f"titre de niveau {level}")
			return

		# Img role
		if role == "img":
			if label:
				self._add_text(f"graphique {label}")
			return

		# Combobox / listbox / textbox
		if role in ("combobox", "listbox", "textbox"):
			self._flush_line()
			parts = [role_label]
			if label:
				parts.append(label)
			parts.extend(states)
			self._add_text(" ".join(parts))
			return

		# Generic: announce role label + accessible name + states
		if role in ARIA_ROLE_LABELS:
			parts = [role_label]
			if label:
				parts.append(label)
			parts.extend(states)
			if parts:
				self._add_text(" ".join(parts))

	# ------------------------------------------------------------------
	# Text formatting (inline semantic tags)
	# ------------------------------------------------------------------

	def _handle_format_start(self, tag: str, attrs: dict) -> None:
		fmt_map = {
			"strong": "gras", "b": "gras",
			"em": "italique", "i": "italique",
			"u": "souligné",
			"s": "barré", "del": "effacé", "ins": "inséré",
			"code": "code", "kbd": "clavier", "samp": "exemple",
			"var": "variable",
			"mark": "surligné",
			"q": "citation",
			"sub": "indice", "sup": "exposant",
		}
		fmt = fmt_map.get(tag)
		if fmt:
			self._format_stack.append(fmt)

	def _handle_format_end(self, tag: str) -> None:
		fmt_map = {
			"strong": "gras", "b": "gras",
			"em": "italique", "i": "italique",
			"u": "souligné",
			"s": "barré", "del": "effacé", "ins": "inséré",
			"code": "code", "kbd": "clavier", "samp": "exemple",
			"var": "variable",
			"mark": "surligné",
			"q": "citation",
			"sub": "indice", "sup": "exposant",
		}
		fmt = fmt_map.get(tag)
		if fmt and self._format_stack and self._format_stack[-1] == fmt:
			self._format_stack.pop()

	# ------------------------------------------------------------------
	# Form controls
	# ------------------------------------------------------------------

	def _handle_form_control_start(self, tag: str, attrs: dict) -> None:  # noqa: C901
		"""Handle <input>, <textarea>, <select>, <button>, <progress>, <meter>, <output>."""
		states = self._collect_aria_states(attrs)

		# Common disabled / required from HTML attributes
		if "disabled" in attrs and "non disponible" not in states:
			states.append("non disponible")
		if "required" in attrs and "obligatoire" not in states:
			states.append("obligatoire")
		if "readonly" in attrs and "en lecture seule" not in states:
			states.append("en lecture seule")

		if tag == "input":
			self._flush_line()
			input_type = attrs.get("type", "text").lower()

			if input_type == "hidden":
				return

			label = self._resolve_label(attrs)

			if input_type in ("submit", "button", "reset"):
				value = attrs.get("value", label or ("Envoyer" if input_type == "submit" else "Réinitialiser" if input_type == "reset" else ""))
				parts = ["bouton", value]
				parts.extend(states)
				self._add_text(" ".join(p for p in parts if p))
			elif input_type == "image":
				alt = attrs.get("alt", attrs.get("value", label or ""))
				parts = ["bouton", alt]
				parts.extend(states)
				self._add_text(" ".join(p for p in parts if p))
			elif input_type == "checkbox":
				checked = "coché" if "checked" in attrs else "non coché"
				# Remove duplicate checked states from aria
				filtered = [s for s in states if s not in ("coché", "non coché", "partiellement coché")]
				parts = ["case à cocher", label, checked]
				parts.extend(filtered)
				self._add_text(" ".join(p for p in parts if p))
			elif input_type == "radio":
				checked = "sélectionné" if "checked" in attrs else "non sélectionné"
				filtered = [s for s in states if s not in ("sélectionné", "non sélectionné")]
				parts = ["bouton radio", label, checked]
				parts.extend(filtered)
				self._add_text(" ".join(p for p in parts if p))
			elif input_type == "range":
				value = attrs.get("value", "")
				vmin = attrs.get("min", "0")
				vmax = attrs.get("max", "100")
				parts = ["potentiomètre", label]
				if value:
					parts.append(value)
				parts.append(f"de {vmin} à {vmax}")
				parts.extend(states)
				self._add_text(" ".join(p for p in parts if p))
			elif input_type == "file":
				parts = ["bouton", label]
				parts.extend(states)
				self._add_text(" ".join(p for p in parts if p))
			elif input_type == "color":
				value = attrs.get("value", "")
				parts = ["bouton", label]
				if value:
					parts.append(value)
				parts.extend(states)
				self._add_text(" ".join(p for p in parts if p))
			else:
				# text, email, url, tel, password, number, search, date, time, etc.
				type_label = _INPUT_TYPE_LABELS.get(input_type, "édition")
				value = attrs.get("value", "")
				parts = [type_label, label]
				if value and input_type != "password":
					parts.append(value)
				parts.extend(states)
				self._add_text(" ".join(p for p in parts if p))

			self._announce_description(attrs)
			self._flush_line()
			return

		if tag == "textarea":
			self._flush_line()
			label = self._resolve_label(attrs)
			parts = []
			if label:
				parts.append(label)
			parts.append("édition")
			parts.append("multiligne")
			parts.extend(states)
			self._add_text(" ".join(p for p in parts if p))
			self._announce_description(attrs)
			self._flush_line()
			return

		if tag == "select":
			self._flush_line()
			label = self._resolve_label(attrs)
			multiple = "multiple" in attrs
			if multiple:
				parts = ["liste", label, "sélection multiple"]
			else:
				parts = ["liste déroulante", label]
			parts.extend(states)
			self._add_text(" ".join(p for p in parts if p))
			self._announce_description(attrs)
			self._flush_line()
			return

		if tag == "option":
			self._flush_line()
			selected = "selected" in attrs
			if selected:
				self._add_text("sélectionné")
			return

		if tag == "button":
			self._flush_line()
			label = self._get_accessible_name(tag, attrs)
			role_attr = attrs.get("role", "")
			if role_attr and role_attr != "button":
				# role overrides default button semantics (handled by ARIA role handler)
				return
			parts = ["bouton"]
			if label:
				parts.append(label)
			parts.extend(states)
			self._add_text(" ".join(p for p in parts if p))
			return

		if tag == "fieldset":
			self._flush_line()
			return

		if tag == "legend":
			self._flush_line()
			return

		if tag == "progress":
			self._flush_line()
			label = self._resolve_label(attrs)
			value = attrs.get("value", "")
			vmax = attrs.get("max", "100")
			parts = ["barre de progression", label]
			if value:
				try:
					pct = int(float(value) / float(vmax) * 100)
					parts.append(f"{pct}%")
				except (ValueError, ZeroDivisionError):
					parts.append(value)
			parts.extend(states)
			self._add_text(" ".join(p for p in parts if p))
			self._flush_line()
			# Skip fallback text content inside <progress>
			self._skip_depth += 1
			return

		if tag == "meter":
			self._flush_line()
			label = self._resolve_label(attrs)
			value = attrs.get("value", "")
			vmin = attrs.get("min", "0")
			vmax = attrs.get("max", "1")
			parts = ["jauge", label]
			if value:
				parts.append(value)
				parts.append(f"de {vmin} à {vmax}")
			parts.extend(states)
			self._add_text(" ".join(p for p in parts if p))
			self._flush_line()
			# Skip fallback text content inside <meter>
			self._skip_depth += 1
			return

		if tag == "output":
			self._flush_line()
			label = self._resolve_label(attrs)
			parts = ["sortie", label]
			parts.extend(states)
			self._add_text(" ".join(p for p in parts if p))
			return

	# ------------------------------------------------------------------
	# handle_endtag
	# ------------------------------------------------------------------

	def handle_endtag(self, tag: str) -> None:  # noqa: C901
		# Pop tag stack
		while self._tag_stack and self._tag_stack[-1]["tag"] != tag:
			self._tag_stack.pop()
		if self._tag_stack:
			popped = self._tag_stack.pop()
		else:
			popped = {"tag": tag, "attrs": {}}

		attrs = popped.get("attrs", {})

		# Track id text collection
		elem_id = attrs.get("id", "")
		if elem_id and self._current_id_targets and self._current_id_targets[-1] == elem_id:
			self._current_id_targets.pop()

		# Skip elements
		if tag in SKIP_ELEMENTS:
			self._skip_depth = max(0, self._skip_depth - 1)
			return

		if "hidden" in attrs or attrs.get("aria-hidden") == "true":
			self._skip_depth = max(0, self._skip_depth - 1)
			return

		# progress / meter: their text content was skipped (fallback)
		if tag in ("progress", "meter"):
			self._skip_depth = max(0, self._skip_depth - 1)

		if self._skip_depth > 0:
			return

		# --- Language ---
		lang = attrs.get("lang", attrs.get("xml:lang", ""))
		if lang and self._lang_stack:
			self._lang_stack.pop()
			if self._lang_stack:
				prev_lang = self._lang_stack[-1]
				if prev_lang != lang:
					lang_names = {
						"fr": "français", "en": "anglais", "de": "allemand",
						"es": "espagnol", "it": "italien", "pt": "portugais",
					}
					name = lang_names.get(prev_lang.split("-")[0], prev_lang)
					self._flush_line()
					self.lines.append(f"langue : {name}")

		# --- Text formatting ---
		self._handle_format_end(tag)

		# --- Links ---
		if tag == "a":
			link_text_parts = []
			if self._a_has_img:
				link_text_parts.append("graphique")
			if self._img_alt_in_link:
				link_text_parts.append(f" {self._img_alt_in_link}")
			inline = " ".join(self._a_text).strip()
			if inline:
				link_text_parts.append(f" {inline}")
			full_text = "".join(link_text_parts).strip()
			if full_text:
				self._add_text(f"lien {full_text}")
			else:
				href = self._a_attrs.get("href", "")
				self._add_text(f"lien {href}")
			# ARIA states on link
			link_states = self._collect_aria_states(self._a_attrs)
			for s in link_states:
				self._add_text(s)
			self._in_a = False
			self._a_text = []
			self._a_has_img = False
			self._img_alt_in_link = ""
			self._a_attrs = {}
			self._flush_line()

		# --- Buttons ---
		if tag == "button":
			self._flush_line()

		# --- Labels ---
		if tag == "label":
			if self._current_label_for:
				label_text = " ".join(self._current_label_text).strip()
				if label_text:
					self._label_for_map[self._current_label_for] = label_text
				self._current_label_for = None
				self._current_label_text = []
			self._flush_line()

		# --- Lists ---
		if tag in ("ul", "ol"):
			self._flush_line()
			if self._list_stack:
				info = self._list_stack.pop()
				count = info["count"]
				start = info["start_index"]
				level = info["level"]
				level_str = f"  niveau {level}" if level > 1 else ""
				if count:
					self.lines.insert(start, f"liste de {count} éléments{level_str}")
					self.lines.append("hors de liste")
				else:
					self.lines.append("hors de liste")

		if tag == "dl":
			self._flush_line()

		# --- Block elements ---
		if tag in BLOCK_ELEMENTS:
			self._flush_line()

		# --- Tables ---
		if tag == "table":
			self._flush_line()
			if self._table_stack:
				t = self._table_stack.pop()
				rows = t["total_rows"]
				cols = t["max_cols"]
				label = t["label"]
				# Insert the table header with dimensions at start
				# Find the "tableau" line we inserted at start
				# Replace simple "tableau" with detailed version
				start_label = f"tableau de {rows} lignes et {cols} colonnes"
				if label:
					start_label = f"tableau {label} de {rows} lignes et {cols} colonnes"
				# Walk backwards to find our "tableau" line
				for idx in range(len(self.lines) - 1, -1, -1):
					line = self.lines[idx]
					if line == "tableau" or line.startswith("tableau  "):
						self.lines[idx] = start_label
						break
				self.lines.append("hors de tableau")
			else:
				self.lines.append("hors de tableau")

		if tag == "thead" and self._table_stack:
			self._table_stack[-1]["in_thead"] = False

		# --- details / summary ---
		if tag == "summary":
			self._flush_line()
			if self._details_stack:
				is_open = self._details_stack[-1]["open"]
				self._add_text("développé" if is_open else "réduit")
				self._flush_line()
			self._in_summary = False

		if tag == "details":
			self._flush_line()
			if self._details_stack:
				self._details_stack.pop()

		# --- dialog ---
		if tag == "dialog":
			self._flush_line()
			self.lines.append("hors de dialogue")

		# --- Landmark end ---
		# NVDA: speakExitForLine=False for landmarks → no exit speech
		# during line-by-line navigation (CARET reason)
		landmark = self._get_landmark_role(tag, attrs)
		if landmark and self._landmark_stack:
			self._flush_line()
			self._landmark_stack.pop()

		# --- ARIA role end for group-like roles ---
		role = attrs.get("role", "")
		if role and role not in LANDMARK_ROLES:
			self._handle_aria_role_end(role, attrs)

		# --- figure ---
		if tag == "figure":
			self._flush_line()
			self.lines.append("hors de figure")

		# --- Blockquote ---
		if tag == "blockquote":
			self._flush_line()
			self.lines.append("hors de citation")

		# --- Pre ---
		if tag == "pre":
			self._pre_depth = max(0, self._pre_depth - 1)

		# --- abbr ---
		if tag == "abbr":
			abbr_title = attrs.get("title", "")
			if abbr_title:
				self._add_text(f"({abbr_title})")

		# --- Media ---
		if tag == "video":
			self._flush_line()
			self.lines.append("hors de vidéo")

		if tag == "audio":
			self._flush_line()
			self.lines.append("hors de audio")

		if tag == "math":
			self._flush_line()

	# ------------------------------------------------------------------
	# ARIA role handler (end)
	# ------------------------------------------------------------------

	def _handle_aria_role_end(self, role: str, attrs: dict) -> None:
		role_label = ARIA_ROLE_LABELS.get(role, "")
		if not role_label:
			return
		if role in (
			"group", "radiogroup", "toolbar", "tablist", "menubar",
			"menu", "tree", "treegrid", "feed", "log", "status",
			"timer", "marquee", "alert", "note", "directory",
		):
			self._flush_line()
			self.lines.append(f"hors de {role_label}")
		elif role in ("dialog", "alertdialog"):
			self._flush_line()
			self.lines.append(f"hors de {role_label}")
		elif role == "application":
			self._flush_line()
			self.lines.append("hors de application")
		elif role == "tabpanel":
			self._flush_line()
			self.lines.append("hors de page de propriété")

	# ------------------------------------------------------------------
	# handle_data / entity / charref
	# ------------------------------------------------------------------

	def handle_data(self, data: str) -> None:
		if self._skip_depth > 0:
			return

		# Pre-formatted: preserve line breaks
		if self._pre_depth > 0:
			for line in data.split("\n"):
				stripped = line.rstrip()
				if stripped:
					self._add_text(stripped)
					self._flush_line()
			return

		text = " ".join(data.split())
		if not text:
			return

		# Collect text for id-based resolution
		if self._current_id_targets:
			for target_id in self._current_id_targets:
				if target_id not in self._id_text_collector:
					self._id_text_collector[target_id] = []
				self._id_text_collector[target_id].append(text)
			# Also update _id_to_element
			for target_id in self._current_id_targets:
				if target_id in self._id_to_element:
					prev = self._id_to_element[target_id].get("text", "")
					self._id_to_element[target_id]["text"] = (prev + " " + text).strip()

		# Collect text for <label for="…">
		if self._current_label_for is not None:
			self._current_label_text.append(text)

		# Add to output
		if self._in_a:
			self._a_text.append(text)
		else:
			self._add_text(text)

	def handle_entityref(self, name: str) -> None:
		if self._skip_depth > 0:
			return
		entity_map = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}
		char = entity_map.get(name, f"&{name};")
		if self._in_a:
			self._a_text.append(char)
		else:
			self._add_text(char)

	def handle_charref(self, name: str) -> None:
		if self._skip_depth > 0:
			return
		try:
			if name.startswith("x"):
				char = chr(int(name[1:], 16))
			else:
				char = chr(int(name))
		except (ValueError, OverflowError):
			char = f"&#{name};"
		if self._in_a:
			self._a_text.append(char)
		else:
			self._add_text(char)

	# ------------------------------------------------------------------
	# Output
	# ------------------------------------------------------------------

	def get_lines(self) -> list[str]:
		"""Return all accumulated lines."""
		self._flush_line()
		return self._post_process(self.lines)

	def _post_process(self, lines: list[str]) -> list[str]:
		"""Post-process lines: clean up empty lines and redundant spaces."""
		result = []
		for line in lines:
			cleaned = re.sub(r"\s{2,}", " ", line).strip()
			if cleaned:
				result.append(cleaned)
		return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tab navigation parser
# ---------------------------------------------------------------------------

# Elements that are natively focusable (receive Tab) without tabindex
_NATIVELY_FOCUSABLE_TAGS = {"a", "button", "input", "select", "textarea", "summary"}

# ARIA interactive roles that are focusable when they carry tabindex
_FOCUSABLE_ARIA_ROLES = {
	"button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
	"menuitemcheckbox", "menuitemradio", "option", "slider", "spinbutton",
	"combobox", "textbox", "searchbox", "treeitem", "gridcell",
}


class NVDATabOrderParser(HTMLParser):
	"""Parse HTML and produce NVDA focus-mode announcements for Tab order.

	Extracts all focusable elements in DOM order and produces the
	announcement NVDA would make when the user presses Tab to reach
	each element. This simulates keyboard-only navigation.

	Focusable elements include:
	- <a href="…"> links
	- <button> elements
	- <input> (except type=hidden)
	- <select>, <textarea>
	- <summary> (inside <details>)
	- Elements with tabindex >= 0
	- Elements with interactive ARIA roles + tabindex
	"""

	def __init__(self) -> None:
		super().__init__()
		self.tab_stops: list[str] = []

		# Tag stack for context
		self._tag_stack: list[dict] = []
		self._skip_depth: int = 0

		# Text collectors
		self._current_text: list[str] = []
		self._in_a: bool = False
		self._a_text: list[str] = []
		self._a_has_img: bool = False
		self._img_alt_in_link: str = ""
		self._a_attrs: dict = {}

		# Button text
		self._in_button: bool = False
		self._button_text: list[str] = []
		self._button_attrs: dict = {}

		# Summary text
		self._in_summary: bool = False
		self._summary_text: list[str] = []
		self._details_stack: list[dict] = []

		# Select state
		self._in_select: bool = False
		self._select_attrs: dict = {}
		self._select_options: list[dict] = []
		self._current_option_text: list[str] = []
		self._current_option_selected: bool = False
		self._in_option: bool = False

		# Label resolution
		self._label_for_map: dict[str, str] = {}
		self._current_label_for: str | None = None
		self._current_label_text: list[str] = []
		self._id_to_element: dict[str, dict] = {}
		self._id_text_collector: dict[str, list[str]] = {}
		self._current_id_targets: list[str] = []

		# Landmark context (for announcing region when tabbing into it)
		self._landmark_stack: list[str] = []

	# ------------------------------------------------------------------
	# Helpers
	# ------------------------------------------------------------------

	def _resolve_label(self, attrs: dict) -> str:
		"""Resolve accessible name for a form control."""
		# aria-labelledby
		labelledby = attrs.get("aria-labelledby", "")
		if labelledby:
			parts = []
			for ref_id in labelledby.split():
				ref_text = self._resolve_id_text(ref_id)
				if ref_text:
					parts.append(ref_text)
			if parts:
				return " ".join(parts)
		# aria-label
		aria_label = attrs.get("aria-label", "")
		if aria_label:
			return aria_label
		# <label for="…">
		elem_id = attrs.get("id", "")
		if elem_id and elem_id in self._label_for_map:
			return self._label_for_map[elem_id]
		# placeholder / title
		return attrs.get("placeholder", attrs.get("title", ""))

	def _resolve_id_text(self, ref_id: str) -> str:
		if ref_id in self._id_text_collector:
			return " ".join(self._id_text_collector[ref_id]).strip()
		if ref_id in self._id_to_element:
			return self._id_to_element[ref_id].get("text", "")
		return ""

	def _collect_aria_states(self, attrs: dict) -> list[str]:
		parts: list[str] = []
		for aria_attr, mapping in _ARIA_STATE_ANNOUNCEMENTS.items():
			val = attrs.get(aria_attr, "")
			if val and val in mapping and mapping[val]:
				parts.append(mapping[val])
		return parts

	def _is_hidden(self, attrs: dict) -> bool:
		return "hidden" in attrs or attrs.get("aria-hidden") == "true"

	def _is_disabled(self, attrs: dict) -> bool:
		return "disabled" in attrs or attrs.get("aria-disabled") == "true"

	def _get_tabindex(self, attrs: dict) -> int | None:
		ti = attrs.get("tabindex", None)
		if ti is not None:
			try:
				return int(ti)
			except ValueError:
				return None
		return None

	# ------------------------------------------------------------------
	# handle_starttag
	# ------------------------------------------------------------------

	def handle_starttag(self, tag: str, attrs_list: list) -> None:
		attrs = dict(attrs_list)
		self._tag_stack.append({"tag": tag, "attrs": attrs})

		# Track IDs
		elem_id = attrs.get("id", "")
		if elem_id:
			self._id_to_element[elem_id] = {"tag": tag, "attrs": attrs, "text": ""}
			self._current_id_targets.append(elem_id)

		# Skip hidden
		if self._is_hidden(attrs):
			self._skip_depth += 1
			return
		if self._skip_depth > 0:
			return
		if tag in SKIP_ELEMENTS:
			self._skip_depth += 1
			return

		# Track landmarks
		role = attrs.get("role", "")
		landmark_role = None
		if role in LANDMARK_ROLES:
			landmark_role = role
		elif tag in IMPLICIT_LANDMARKS:
			if tag in ("header", "footer"):
				for item in self._tag_stack[:-1]:
					if item["tag"] in ("article", "section", "aside"):
						landmark_role = None
						break
				else:
					landmark_role = IMPLICIT_LANDMARKS[tag]
			else:
				landmark_role = IMPLICIT_LANDMARKS[tag]
		if landmark_role:
			label = attrs.get("aria-label", "")
			landmark_name = LANDMARK_ROLES.get(landmark_role, landmark_role)
			if label:
				self._landmark_stack.append(f"{landmark_name} {label}")
			else:
				self._landmark_stack.append(landmark_name)

		# Labels (<label for>)
		if tag == "label":
			for_id = attrs.get("for", "")
			if for_id:
				self._current_label_for = for_id
				self._current_label_text = []

		# --- Links ---
		if tag == "a" and ("href" in attrs):
			tabindex = self._get_tabindex(attrs)
			if tabindex is not None and tabindex < 0:
				return
			if self._is_disabled(attrs):
				return
			self._in_a = True
			self._a_text = []
			self._a_has_img = False
			self._img_alt_in_link = ""
			self._a_attrs = attrs

		# --- Images inside links ---
		if tag == "img" and self._in_a:
			alt = attrs.get("alt")
			role_attr = attrs.get("role", "")
			if role_attr not in ("presentation", "none"):
				self._a_has_img = True
				self._img_alt_in_link = alt or ""

		# --- Buttons ---
		if tag == "button":
			tabindex = self._get_tabindex(attrs)
			if tabindex is not None and tabindex < 0:
				return
			if self._is_disabled(attrs):
				return
			self._in_button = True
			self._button_text = []
			self._button_attrs = attrs

		# --- Input ---
		if tag == "input":
			input_type = attrs.get("type", "text").lower()
			if input_type == "hidden":
				return
			tabindex = self._get_tabindex(attrs)
			if tabindex is not None and tabindex < 0:
				return
			if self._is_disabled(attrs):
				return
			self._emit_input(attrs, input_type)

		# --- Select ---
		if tag == "select":
			tabindex = self._get_tabindex(attrs)
			if tabindex is not None and tabindex < 0:
				return
			if self._is_disabled(attrs):
				return
			self._in_select = True
			self._select_attrs = attrs
			self._select_options = []

		if tag == "option" and self._in_select:
			self._in_option = True
			self._current_option_text = []
			self._current_option_selected = "selected" in attrs

		# --- Textarea ---
		if tag == "textarea":
			tabindex = self._get_tabindex(attrs)
			if tabindex is not None and tabindex < 0:
				return
			if self._is_disabled(attrs):
				return
			label = self._resolve_label(attrs)
			states = self._collect_aria_states(attrs)
			if "required" in attrs and "obligatoire" not in states:
				states.append("obligatoire")
			parts = [label, "édition multiligne"] if label else ["édition multiligne"]
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))

		# --- Summary ---
		if tag == "summary":
			self._in_summary = True
			self._summary_text = []

		if tag == "details":
			is_open = "open" in attrs
			self._details_stack.append({"open": is_open})

		# --- Elements with tabindex >= 0 and interactive ARIA roles ---
		if tag not in _NATIVELY_FOCUSABLE_TAGS:
			tabindex = self._get_tabindex(attrs)
			if tabindex is not None and tabindex >= 0:
				if role in _FOCUSABLE_ARIA_ROLES:
					self._emit_aria_role_focus(tag, attrs, role)

	# ------------------------------------------------------------------
	# Emit helpers
	# ------------------------------------------------------------------

	def _emit_input(self, attrs: dict, input_type: str) -> None:
		label = self._resolve_label(attrs)
		states = self._collect_aria_states(attrs)
		if "required" in attrs and "obligatoire" not in states:
			states.append("obligatoire")

		if input_type in ("submit", "button", "reset"):
			default = {"submit": "Envoyer", "reset": "Réinitialiser"}.get(input_type, "")
			value = attrs.get("value", label or default)
			parts = ["bouton", value]
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif input_type == "image":
			alt = attrs.get("alt", attrs.get("value", label or ""))
			parts = ["bouton", alt]
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif input_type == "checkbox":
			checked = "coché" if "checked" in attrs else "non coché"
			parts = [label, "case à cocher", checked] if label else ["case à cocher", checked]
			parts.extend(s for s in states if s not in ("coché", "non coché"))
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif input_type == "radio":
			checked = "sélectionné" if "checked" in attrs else "non sélectionné"
			parts = [label, "bouton radio", checked] if label else ["bouton radio", checked]
			parts.extend(s for s in states if s not in ("sélectionné", "non sélectionné"))
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif input_type == "range":
			value = attrs.get("value", "")
			vmin = attrs.get("min", "0")
			vmax = attrs.get("max", "100")
			parts = [label, "potentiomètre"] if label else ["potentiomètre"]
			if value:
				parts.append(value)
			parts.append(f"de {vmin} à {vmax}")
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif input_type == "file":
			parts = [label, "bouton Parcourir…"] if label else ["bouton Parcourir…"]
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif input_type == "color":
			value = attrs.get("value", "")
			parts = [label, "bouton"] if label else ["bouton"]
			if value:
				parts.append(value)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		else:
			type_label = _INPUT_TYPE_LABELS.get(input_type, "édition")
			value = attrs.get("value", "")
			parts = [label, type_label] if label else [type_label]
			if value and input_type != "password":
				parts.append(f"contient {value}")
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))

	def _emit_aria_role_focus(self, tag: str, attrs: dict, role: str) -> None:
		label = attrs.get("aria-label", "")
		states = self._collect_aria_states(attrs)
		role_label = ARIA_ROLE_LABELS.get(role, role)

		if role in ("button",):
			parts = ["bouton"]
			if label:
				parts.append(label)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif role == "link":
			parts = ["lien"]
			if label:
				parts.append(label)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif role in ("checkbox",):
			checked_val = attrs.get("aria-checked", "false")
			checked = "coché" if checked_val == "true" else ("semi-coché" if checked_val == "mixed" else "non coché")
			parts = [label, "case à cocher", checked] if label else ["case à cocher", checked]
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif role == "switch":
			checked_val = attrs.get("aria-checked", "false")
			state = "activé" if checked_val == "true" else "désactivé"
			parts = [label, "bascule", state] if label else ["bascule", state]
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif role == "tab":
			parts = ["onglet"]
			if label:
				parts.append(label)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif role in ("slider", "spinbutton"):
			parts = [role_label]
			if label:
				parts.append(label)
			vnow = attrs.get("aria-valuenow", "")
			if vnow:
				parts.append(vnow)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		elif role in ("combobox", "textbox", "searchbox", "listbox"):
			parts = [role_label]
			if label:
				parts.append(label)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
		else:
			parts = [role_label]
			if label:
				parts.append(label)
			parts.extend(states)
			if parts:
				self.tab_stops.append(" ".join(p for p in parts if p))

	# ------------------------------------------------------------------
	# handle_data
	# ------------------------------------------------------------------

	def handle_data(self, data: str) -> None:
		if self._skip_depth > 0:
			return
		text = " ".join(data.split())
		if not text:
			return

		# Collect for id resolution
		if self._current_id_targets:
			for target_id in self._current_id_targets:
				if target_id not in self._id_text_collector:
					self._id_text_collector[target_id] = []
				self._id_text_collector[target_id].append(text)
			for target_id in self._current_id_targets:
				if target_id in self._id_to_element:
					prev = self._id_to_element[target_id].get("text", "")
					self._id_to_element[target_id]["text"] = (prev + " " + text).strip()

		# Collect for <label for>
		if self._current_label_for is not None:
			self._current_label_text.append(text)

		# Link text
		if self._in_a:
			self._a_text.append(text)

		# Button text
		if self._in_button:
			self._button_text.append(text)

		# Summary text
		if self._in_summary:
			self._summary_text.append(text)

		# Option text
		if self._in_option and self._in_select:
			self._current_option_text.append(text)

	def handle_entityref(self, name: str) -> None:
		if self._skip_depth > 0:
			return
		entity_map = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}
		char = entity_map.get(name, f"&{name};")
		if self._in_a:
			self._a_text.append(char)
		elif self._in_button:
			self._button_text.append(char)
		elif self._in_summary:
			self._summary_text.append(char)
		elif self._in_option:
			self._current_option_text.append(char)

	def handle_charref(self, name: str) -> None:
		if self._skip_depth > 0:
			return
		try:
			if name.startswith("x"):
				char = chr(int(name[1:], 16))
			else:
				char = chr(int(name))
		except (ValueError, OverflowError):
			char = f"&#{name};"
		if self._in_a:
			self._a_text.append(char)
		elif self._in_button:
			self._button_text.append(char)
		elif self._in_summary:
			self._summary_text.append(char)
		elif self._in_option:
			self._current_option_text.append(char)

	# ------------------------------------------------------------------
	# handle_endtag
	# ------------------------------------------------------------------

	def handle_endtag(self, tag: str) -> None:
		# Pop tag stack
		while self._tag_stack and self._tag_stack[-1]["tag"] != tag:
			self._tag_stack.pop()
		if self._tag_stack:
			popped = self._tag_stack.pop()
		else:
			popped = {"tag": tag, "attrs": {}}
		attrs = popped.get("attrs", {})

		# Track id collection
		elem_id = attrs.get("id", "")
		if elem_id and self._current_id_targets and self._current_id_targets[-1] == elem_id:
			self._current_id_targets.pop()

		# Skip hidden/script
		if tag in SKIP_ELEMENTS:
			self._skip_depth = max(0, self._skip_depth - 1)
			return
		if self._is_hidden(attrs):
			self._skip_depth = max(0, self._skip_depth - 1)
			return
		if self._skip_depth > 0:
			return

		# Labels
		if tag == "label":
			if self._current_label_for:
				label_text = " ".join(self._current_label_text).strip()
				if label_text:
					self._label_for_map[self._current_label_for] = label_text
				self._current_label_for = None
				self._current_label_text = []

		# Links: emit on close
		if tag == "a" and self._in_a:
			link_parts = []
			if self._a_has_img:
				link_parts.append("graphique")
				if self._img_alt_in_link:
					link_parts.append(self._img_alt_in_link)
			inline = " ".join(self._a_text).strip()
			if inline:
				link_parts.append(inline)
			full_text = " ".join(link_parts).strip()

			aria_label = self._a_attrs.get("aria-label", "")
			if aria_label:
				full_text = aria_label

			states = self._collect_aria_states(self._a_attrs)
			parts = ["lien"]
			if full_text:
				parts.append(full_text)
			else:
				href = self._a_attrs.get("href", "")
				parts.append(href)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))

			self._in_a = False
			self._a_text = []
			self._a_has_img = False
			self._img_alt_in_link = ""
			self._a_attrs = {}

		# Buttons: emit on close
		if tag == "button" and self._in_button:
			label = self._button_attrs.get("aria-label", "")
			if not label:
				label = " ".join(self._button_text).strip()
			states = self._collect_aria_states(self._button_attrs)
			parts = ["bouton"]
			if label:
				parts.append(label)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
			self._in_button = False
			self._button_text = []
			self._button_attrs = {}

		# Summary: emit on close
		if tag == "summary" and self._in_summary:
			text = " ".join(self._summary_text).strip()
			is_open = self._details_stack[-1]["open"] if self._details_stack else False
			state = "développé" if is_open else "réduit"
			parts = ["bouton", text, state] if text else ["bouton", state]
			self.tab_stops.append(" ".join(p for p in parts if p))
			self._in_summary = False
			self._summary_text = []

		if tag == "details" and self._details_stack:
			self._details_stack.pop()

		# Select: emit on close
		if tag == "option" and self._in_option:
			option_text = " ".join(self._current_option_text).strip()
			self._select_options.append({
				"text": option_text,
				"selected": self._current_option_selected,
			})
			self._in_option = False
			self._current_option_text = []
			self._current_option_selected = False

		if tag == "select" and self._in_select:
			label = self._resolve_label(self._select_attrs)
			states = self._collect_aria_states(self._select_attrs)
			multiple = "multiple" in self._select_attrs
			selected_opt = ""
			for opt in self._select_options:
				if opt["selected"]:
					selected_opt = opt["text"]
					break
			if not selected_opt and self._select_options:
				selected_opt = self._select_options[0]["text"]

			if multiple:
				parts = [label, "liste sélection multiple"] if label else ["liste sélection multiple"]
			else:
				parts = [label, "liste déroulante"] if label else ["liste déroulante"]
			if selected_opt:
				parts.append(selected_opt)
			parts.extend(states)
			self.tab_stops.append(" ".join(p for p in parts if p))
			self._in_select = False
			self._select_attrs = {}
			self._select_options = []

		# Landmark end
		landmark_role = None
		role = attrs.get("role", "")
		if role in LANDMARK_ROLES:
			landmark_role = role
		elif tag in IMPLICIT_LANDMARKS:
			landmark_role = IMPLICIT_LANDMARKS.get(tag)
		if landmark_role and self._landmark_stack:
			self._landmark_stack.pop()

	def get_tab_stops(self) -> list[str]:
		"""Return all Tab stops (focusable elements) in DOM order."""
		result = []
		for stop in self.tab_stops:
			cleaned = re.sub(r"\s{2,}", " ", stop).strip()
			if cleaned:
				result.append(cleaned)
		return result


def html_to_nvda_tab_lines(html: str) -> list[str]:
	"""Convert HTML to NVDA Tab-order announcements.

	Simulates what NVDA announces when pressing Tab repeatedly on a page.
	Only focusable/interactive elements are included (links, buttons,
	form controls, elements with tabindex, etc.).

	Args:
		html: The HTML content of a web page.

	Returns:
		A list of strings, each representing what NVDA announces when
		pressing Tab to reach the next focusable element.
	"""
	parser = NVDATabOrderParser()
	parser.feed(html)
	return parser.get_tab_stops()


def html_to_nvda_lines(html: str) -> list[str]:
	"""Convert an HTML string to a list of NVDA browse mode lines.

	Args:
		html: The HTML content of a web page.

	Returns:
		A list of strings, each representing one line that NVDA would
		announce when pressing the down arrow key in browse mode.
	"""
	parser = NVDABrowseModeParser()
	parser.feed(html)
	return parser.get_lines()


def fetch_and_convert(url: str, timeout: float = 15.0) -> list[str]:
	"""Fetch a URL and convert its HTML to NVDA browse mode lines.

	Args:
		url: The URL to fetch.
		timeout: Request timeout in seconds.

	Returns:
		A list of NVDA browse mode lines.
	"""
	import urllib.request

	req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/128.0"})
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		html = resp.read().decode("utf-8", errors="replace")
	return html_to_nvda_lines(html)


if __name__ == "__main__":
	import sys

	# --tab flag for Tab order output
	tab_mode = "--tab" in sys.argv
	args = [a for a in sys.argv[1:] if a != "--tab"]

	if args:
		url = args[0]
		import urllib.request as _ur
		_req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/128.0"})
		with _ur.urlopen(_req, timeout=15) as _resp:
			_html = _resp.read().decode("utf-8", errors="replace")
		if tab_mode:
			lines = html_to_nvda_tab_lines(_html)
		else:
			lines = html_to_nvda_lines(_html)
	else:
		# Demo with a comprehensive HTML page
		demo_html = """<!DOCTYPE html>
<html lang="fr">
<head><title>Page de test complète</title></head>
<body>
  <a href="#main">Aller au contenu</a>
  <header>
    <a href="/"><img src="logo.png" alt="Mon Site" /></a>
    <nav aria-label="Menu principal">
      <ul>
        <li><a href="/services">Services</a></li>
        <li><a href="/contact" aria-current="page">Contact</a></li>
      </ul>
    </nav>
  </header>
  <main id="main">
    <h1>Bienvenue sur mon site</h1>
    <p>Ceci est un <strong>paragraphe</strong> de test avec un <a href="/lien">lien interne</a>.</p>
    <p lang="en">This paragraph is in English.</p>
    <h2>Nos services</h2>
    <ul>
      <li><a href="/audit">Audit accessibilité</a></li>
      <li><a href="/formation">Formation RGAA</a></li>
    </ul>
    <img src="photo.jpg" alt="Équipe au travail" />

    <h2>Tableau d'exemple</h2>
    <table aria-label="Tarifs">
      <tr><th>Service</th><th>Prix</th></tr>
      <tr><td>Audit</td><td>500 €</td></tr>
      <tr><td>Formation</td><td>1200 €</td></tr>
    </table>

    <h2>Formulaire</h2>
    <form>
      <label for="email">Adresse email</label>
      <input type="email" id="email" required />
      <label for="msg">Message</label>
      <textarea id="msg" aria-describedby="msg-help"></textarea>
      <p id="msg-help">Décrivez votre besoin en quelques lignes.</p>
      <input type="range" min="0" max="10" value="5" aria-label="Satisfaction" />
      <progress value="70" max="100" aria-label="Progression">70%</progress>
      <button type="submit">Envoyer</button>
    </form>

    <h2>Composants interactifs</h2>
    <details>
      <summary>En savoir plus</summary>
      <p>Contenu supplémentaire affiché quand on développe.</p>
    </details>
    <div role="tablist" aria-label="Sections">
      <div role="tab" aria-selected="true">Onglet 1</div>
      <div role="tab" aria-selected="false">Onglet 2</div>
    </div>
    <div role="tabpanel" aria-label="Contenu onglet 1">
      <p>Contenu du premier onglet.</p>
    </div>
    <div role="alert">Votre session expire bientôt.</div>
    <div role="switch" aria-checked="true" aria-label="Mode sombre">Mode sombre</div>
  </main>
  <footer>
    <p>&copy; 2025 Mon Site</p>
    <a href="/mentions">Mentions légales</a>
  </footer>
</body>
</html>"""
		if tab_mode:
			lines = html_to_nvda_tab_lines(demo_html)
		else:
			lines = html_to_nvda_lines(demo_html)

	mode_label = "TAB ORDER" if tab_mode else "BROWSE MODE"
	print(f"--- {mode_label} ({len(lines)} entries) ---")
	for i, line in enumerate(lines, 1):
		print(f"{i:3d}. {line}")
