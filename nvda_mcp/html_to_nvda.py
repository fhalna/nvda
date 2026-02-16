"""
Convert HTML to NVDA browse mode output.

Simulates what NVDA announces in browse mode (virtual buffer) when
navigating a web page with the down arrow key. Parses real HTML and
produces a list of text lines matching NVDA's speech output.

This module is useful for:
- Testing the MCP server without running NVDA
- Demonstrating what an AI would see on any web page
- Automated accessibility analysis
"""

from html.parser import HTMLParser

# Mapping of HTML tags to NVDA role announcements (French)
LANDMARK_ROLES = {
	"banner": "bannière",
	"navigation": "navigation",
	"main": "contenu principal",
	"contentinfo": "informations de contenu",
	"complementary": "complémentaire",
	"search": "recherche",
	"form": "formulaire",
	"region": "région",
}

# HTML5 elements that map to implicit ARIA landmarks
IMPLICIT_LANDMARKS = {
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
}

# Elements to skip entirely (including <head> contents)
SKIP_ELEMENTS = {"script", "style", "noscript", "template", "svg", "path", "meta", "link", "head", "title"}

# Inline elements that don't cause line breaks
INLINE_ELEMENTS = {"a", "span", "strong", "em", "b", "i", "u", "s", "small", "mark", "abbr", "code", "time", "sub", "sup"}


class NVDABrowseModeParser(HTMLParser):
	"""Parse HTML and produce NVDA-like browse mode output."""

	def __init__(self):
		super().__init__()
		self.lines: list[str] = []
		self._current_line: list[str] = []
		self._tag_stack: list[dict] = []
		self._skip_depth: int = 0
		self._list_stack: list[dict] = []
		self._in_a: bool = False
		self._a_has_img: bool = False
		self._a_text: list[str] = []
		self._img_alt_in_link: str = ""
		self._landmark_stack: list[str] = []

	def _flush_line(self):
		"""Flush the current accumulated text as a line."""
		text = " ".join(self._current_line).strip()
		if text:
			self.lines.append(text)
		self._current_line = []

	def _add_text(self, text: str):
		"""Add text to the current line."""
		text = text.strip()
		if text:
			self._current_line.append(text)

	def _get_landmark_role(self, tag: str, attrs: dict) -> str | None:
		"""Determine the ARIA landmark role for an element."""
		# Explicit role attribute
		role = attrs.get("role", "")
		if role in LANDMARK_ROLES:
			return role
		# Implicit landmark from HTML5 element
		if tag in IMPLICIT_LANDMARKS:
			# <header> and <footer> are only landmarks when not nested
			if tag in ("header", "footer"):
				# Simplified: treat top-level header/footer as landmarks
				for item in self._tag_stack:
					if item["tag"] in ("article", "section", "aside"):
						return None
			return IMPLICIT_LANDMARKS[tag]
		return None

	def handle_starttag(self, tag: str, attrs_list: list):
		attrs = dict(attrs_list)
		tag_info = {"tag": tag, "attrs": attrs}
		self._tag_stack.append(tag_info)

		# Skip hidden elements
		if attrs.get("hidden") is not None or attrs.get("aria-hidden") == "true":
			self._skip_depth += 1
			return

		if self._skip_depth > 0:
			return

		if tag in SKIP_ELEMENTS:
			self._skip_depth += 1
			return

		# Landmark handling
		landmark = self._get_landmark_role(tag, attrs)
		if landmark:
			self._flush_line()
			role_name = LANDMARK_ROLES.get(landmark, landmark)
			aria_label = attrs.get("aria-label", "")
			if aria_label:
				self.lines.append(f"{aria_label}  {role_name}  repère")
			else:
				self.lines.append(f"{role_name}  repère")
			self._landmark_stack.append(role_name)

		# Block elements cause line breaks
		if tag in BLOCK_ELEMENTS:
			self._flush_line()

		# Headings
		if tag in HEADING_TAGS:
			level = tag[1]
			self._add_text(f"titre de niveau {level}")

		# Links
		if tag == "a":
			self._in_a = True
			self._a_has_img = False
			self._a_text = []
			self._img_alt_in_link = ""

		# Images
		if tag == "img":
			alt = attrs.get("alt", "")
			if self._in_a:
				self._a_has_img = True
				self._img_alt_in_link = alt
			elif alt:
				self._add_text(f"graphique  {alt}")

		# Lists
		if tag in ("ul", "ol"):
			self._flush_line()
			# Remember where in self.lines this list starts
			self._list_stack.append({"tag": tag, "count": 0, "start_index": len(self.lines)})

		if tag == "li":
			self._flush_line()
			if self._list_stack:
				self._list_stack[-1]["count"] += 1

		# Tables
		if tag == "table":
			self._flush_line()
			summary = attrs.get("aria-label", attrs.get("summary", ""))
			if summary:
				self.lines.append(f"tableau  {summary}")
			else:
				self.lines.append("tableau")

		if tag == "th":
			self._flush_line()

		if tag == "td":
			self._flush_line()

		# Labels (flush before so they appear on their own or before input)
		if tag == "label":
			self._flush_line()

		# Forms - each control on its own line
		if tag == "input":
			self._flush_line()
			input_type = attrs.get("type", "text")
			label = attrs.get("aria-label", attrs.get("placeholder", attrs.get("title", "")))
			if input_type in ("submit", "button"):
				value = attrs.get("value", label or "")
				self._add_text(f"bouton  {value}")
			elif input_type == "checkbox":
				self._add_text(f"case à cocher  {label}  non coché")
			elif input_type == "radio":
				self._add_text(f"bouton radio  {label}")
			elif input_type == "search":
				self._add_text(f"zone d'édition de recherche  {label}")
			elif input_type in ("text", "email", "url", "tel", "password", "number"):
				self._add_text(f"zone d'édition  {label}")
			self._flush_line()

		if tag == "textarea":
			self._flush_line()
			label = attrs.get("aria-label", attrs.get("placeholder", ""))
			self._add_text(f"zone d'édition multi-lignes  {label}")
			self._flush_line()

		if tag == "select":
			self._flush_line()
			label = attrs.get("aria-label", "")
			self._add_text(f"liste déroulante  {label}")
			self._flush_line()

		if tag == "button":
			self._flush_line()
			self._add_text("bouton")

		if tag == "fieldset":
			self._flush_line()

		if tag == "legend":
			self._flush_line()

		# Separators
		if tag == "hr":
			self.lines.append("séparateur")

		if tag == "br":
			self._flush_line()

	def handle_endtag(self, tag: str):
		# Pop tag stack
		while self._tag_stack and self._tag_stack[-1]["tag"] != tag:
			self._tag_stack.pop()
		if self._tag_stack:
			popped = self._tag_stack.pop()
		else:
			popped = {"tag": tag, "attrs": {}}

		attrs = popped.get("attrs", {})

		if tag in SKIP_ELEMENTS:
			self._skip_depth = max(0, self._skip_depth - 1)
			return

		if attrs.get("hidden") is not None or attrs.get("aria-hidden") == "true":
			self._skip_depth = max(0, self._skip_depth - 1)
			return

		if self._skip_depth > 0:
			return

		# Links
		if tag == "a":
			link_text_parts = []
			if self._a_has_img:
				link_text_parts.append("graphique")
			if self._img_alt_in_link:
				link_text_parts.append(f" {self._img_alt_in_link}")
			# Add any text accumulated for this link
			inline = " ".join(self._a_text).strip()
			if inline:
				link_text_parts.append(f" {inline}")

			full_text = "".join(link_text_parts).strip()
			if full_text:
				self._add_text(f"lien {full_text}")
			else:
				href = attrs.get("href", "")
				self._add_text(f"lien {href}")
			self._in_a = False
			self._a_text = []
			self._a_has_img = False
			self._img_alt_in_link = ""

		# Buttons
		if tag == "button":
			self._flush_line()

		# Lists
		if tag in ("ul", "ol"):
			self._flush_line()
			if self._list_stack:
				info = self._list_stack.pop()
				count = info["count"]
				start = info["start_index"]
				# Insert "liste de N éléments" at the position where the list started
				if count:
					self.lines.insert(start, f"liste de {count} éléments")
					self.lines.append(f"fin de liste")
				else:
					self.lines.append("fin de liste")

		# Block elements cause line breaks
		if tag in BLOCK_ELEMENTS:
			self._flush_line()

		# Tables
		if tag == "table":
			self._flush_line()
			self.lines.append("fin de tableau")

		# Landmark end
		landmark = self._get_landmark_role(tag, attrs)
		if landmark and self._landmark_stack:
			self._flush_line()
			role_name = self._landmark_stack.pop()
			self.lines.append(f"fin de {role_name}  repère")

	def handle_data(self, data: str):
		if self._skip_depth > 0:
			return
		text = " ".join(data.split())
		if not text:
			return
		if self._in_a:
			self._a_text.append(text)
		else:
			self._add_text(text)

	def handle_entityref(self, name: str):
		if self._skip_depth > 0:
			return
		entity_map = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}
		char = entity_map.get(name, f"&{name};")
		if self._in_a:
			self._a_text.append(char)
		else:
			self._add_text(char)

	def handle_charref(self, name: str):
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

	def get_lines(self) -> list[str]:
		"""Return all accumulated lines."""
		self._flush_line()
		# Add list item counts retroactively
		return self._post_process(self.lines)

	def _post_process(self, lines: list[str]) -> list[str]:
		"""Post-process lines: clean up empty lines."""
		return [line.strip() for line in lines if line.strip()]


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

	if len(sys.argv) > 1:
		url = sys.argv[1]
		lines = fetch_and_convert(url)
	else:
		# Demo with a simple HTML page
		demo_html = """<!DOCTYPE html>
<html lang="fr">
<head><title>Page de test</title></head>
<body>
  <a href="#main">Aller au contenu</a>
  <header>
    <a href="/"><img src="logo.png" alt="Mon Site" /></a>
    <nav aria-label="Menu principal">
      <ul>
        <li><a href="/services">Services</a></li>
        <li><a href="/contact">Contact</a></li>
      </ul>
    </nav>
  </header>
  <main id="main">
    <h1>Bienvenue sur mon site</h1>
    <p>Ceci est un <strong>paragraphe</strong> de test avec un <a href="/lien">lien interne</a>.</p>
    <h2>Nos services</h2>
    <ul>
      <li><a href="/audit">Audit accessibilité</a></li>
      <li><a href="/formation">Formation RGAA</a></li>
    </ul>
    <img src="photo.jpg" alt="Équipe au travail" />
    <form>
      <label for="email">Email</label>
      <input type="email" id="email" placeholder="votre@email.com" />
      <button type="submit">Envoyer</button>
    </form>
  </main>
  <footer>
    <p>&copy; 2025 Mon Site</p>
    <a href="/mentions">Mentions légales</a>
  </footer>
</body>
</html>"""
		lines = html_to_nvda_lines(demo_html)

	for i, line in enumerate(lines, 1):
		print(f"{i:3d}. {line}")
