#!/usr/bin/env python3
"""
Simulation: an AI browses any website using the NVDA MCP server.

This script:
1. Fetches the real HTML of a given URL
2. Converts it to NVDA browse mode lines using html_to_nvda
3. Mocks the NVDA bridge HTTP server with this data
4. Runs the MCP tools against it, simulating the full AI experience

Usage:
    python -m nvda_mcp.demo_browse https://example.com
    python -m nvda_mcp.demo_browse                        # uses built-in demo
"""

import http.server
import json
import sys
import threading
import time
import urllib.request

from .html_to_nvda import html_to_nvda_lines, html_to_nvda_tab_lines


def fetch_html(url: str) -> str:
	"""Fetch a URL and return its HTML content."""
	req = urllib.request.Request(
		url,
		headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/128.0"},
	)
	with urllib.request.urlopen(req, timeout=15) as resp:
		return resp.read().decode("utf-8", errors="replace")


# ============================================================
# Mock NVDA Bridge
# ============================================================

class MockNVDABridge:
	"""Mock NVDA bridge that serves browse mode lines from parsed HTML."""

	def __init__(self, browse_lines: list[str], tab_lines: list[str], page_title: str, url: str):
		self.browse_lines = browse_lines
		self.tab_lines = tab_lines
		self.page_title = page_title
		self.url = url
		self.current_line = 0
		self.current_tab = -1  # -1 = before first tab stop
		self.speech_history: list[str] = []

	def dispatch(self, method: str, params: dict) -> dict:
		if method == "speak":
			text = params.get("text", "")
			self.speech_history.append(text)
			return {"spoken": text}

		elif method == "cancelSpeech":
			return {"cancelled": True}

		elif method == "getSpeechHistory":
			count = params.get("count", 10)
			return {"history": self.speech_history[-count:]}

		elif method == "getFocus":
			return {
				"name": f"{self.page_title} - Mozilla Firefox",
				"role": "fenêtre de cadre",
				"roleId": "FRAME",
				"value": "",
				"states": ["focalisé"],
				"stateIds": ["FOCUSED"],
				"childCount": 1,
				"windowClassName": "MozillaWindowClass",
				"appName": "firefox",
			}

		elif method == "getForeground":
			return {
				"name": f"{self.page_title} - Mozilla Firefox",
				"role": "fenêtre de cadre",
				"roleId": "FRAME",
				"value": "",
				"states": [],
				"stateIds": [],
				"childCount": 5,
				"windowClassName": "MozillaWindowClass",
				"appName": "firefox",
				"location": {"left": 0, "top": 0, "width": 1920, "height": 1080},
			}

		elif method == "getVersion":
			return {"version": "2025.1", "name": "NVDA"}

		elif method == "getStatusBar":
			return {"text": "", "found": False}

		elif method == "sendKeys":
			keys = params.get("keys", "")
			if keys == "downArrow" and self.current_line < len(self.browse_lines) - 1:
				self.current_line += 1
				self.speech_history.append(self.browse_lines[self.current_line])
			elif keys == "upArrow" and self.current_line > 0:
				self.current_line -= 1
				self.speech_history.append(self.browse_lines[self.current_line])
			elif keys == "tab" and self.tab_lines:
				if self.current_tab < len(self.tab_lines) - 1:
					self.current_tab += 1
					self.speech_history.append(self.tab_lines[self.current_tab])
			elif keys == "shift+tab" and self.tab_lines:
				if self.current_tab > 0:
					self.current_tab -= 1
					self.speech_history.append(self.tab_lines[self.current_tab])
			elif keys == "control+home":
				self.current_line = 0
				self.current_tab = -1
			return {"sent": keys}

		elif method == "reviewCurrentLine":
			if 0 <= self.current_line < len(self.browse_lines):
				return {"text": self.browse_lines[self.current_line]}
			return {"text": ""}

		elif method == "getClipboard":
			return {"text": ""}

		elif method == "getSpeechSettings":
			return {
				"synthName": "OneCore",
				"synthId": "oneCore",
				"rate": 50,
				"volume": 100,
				"voice": "Microsoft Hortense",
			}

		elif method == "getObjectTree":
			# Build a simplified tree from landmarks in the browse lines
			landmarks = []
			for line in self.browse_lines:
				if line.endswith("repère") and not line.startswith("fin de"):
					role = line.replace("  repère", "").strip()
					landmarks.append({
						"name": "",
						"role": role,
						"roleId": role.upper(),
						"value": "",
						"states": [],
						"stateIds": [],
						"childCount": 0,
						"children": [],
					})
			return {
				"name": self.page_title,
				"role": "document",
				"roleId": "DOCUMENT",
				"value": self.url,
				"states": ["focalisé", "lecture seule"],
				"stateIds": ["FOCUSED", "READONLY"],
				"childCount": len(landmarks),
				"appName": "firefox",
				"children": landmarks,
			}

		return {}


class MockBridgeHTTPHandler(http.server.BaseHTTPRequestHandler):
	def do_POST(self):
		content_length = int(self.headers.get("Content-Length", 0))
		body = self.rfile.read(content_length)
		request = json.loads(body)
		result = self.server.bridge.dispatch(request.get("method", ""), request.get("params", {}))
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps({"result": result}).encode())

	def do_GET(self):
		if self.path == "/health":
			self.send_response(200)
			self.send_header("Content-Type", "application/json")
			self.end_headers()
			self.wfile.write(json.dumps({"status": "ok", "version": "2025.1"}).encode())
		else:
			self.send_response(404)
			self.end_headers()

	def log_message(self, format, *args):
		pass


# ============================================================
# Demo runner
# ============================================================

def run_demo(url: str | None = None, html: str | None = None):
	"""Run the full MCP demo for a given URL or HTML content."""

	# --- Step 0: Get HTML and parse it ---
	if html is None and url is not None:
		print(f"Récupération de {url} ...")
		html = fetch_html(url)
		print(f"  {len(html)} octets récupérés.")
	elif html is None:
		# Use a built-in demo page
		url = "https://example.com"
		html = """<!DOCTYPE html>
<html lang="fr">
<head><title>Exemple - Page de test accessibilité</title></head>
<body>
  <a href="#main">Aller au contenu</a>
  <header>
    <a href="/"><img src="logo.png" alt="Mon Site" /></a>
    <nav aria-label="Menu principal">
      <ul>
        <li><a href="/services">Services</a></li>
        <li><a href="/formations">Formations</a></li>
        <li><a href="/contact">Contact</a></li>
      </ul>
    </nav>
  </header>
  <main id="main">
    <h1>Bienvenue sur notre site</h1>
    <p>Nous sommes spécialisés dans l'accessibilité numérique et accompagnons les entreprises dans leur mise en conformité RGAA.</p>
    <a href="/services">Découvrir nos services</a>
    <h2>Nos services</h2>
    <ul>
      <li><h3><a href="/audit">Audit de conformité</a></h3><p>Nous auditons vos sites web selon le RGAA et les WCAG.</p></li>
      <li><h3><a href="/formation">Formation</a></h3><p>Des formations pour tous les profils : développeurs, designers, chefs de projet.</p></li>
      <li><h3><a href="/accompagnement">Accompagnement</a></h3><p>Un suivi personnalisé pour intégrer l'accessibilité dans vos projets.</p></li>
    </ul>
    <h2>Actualités</h2>
    <article>
      <h3><a href="/blog/webinaire">Webinaire : Design accessible</a></h3>
      <p>Découvrez les bonnes pratiques de conception accessibles dans notre dernier webinaire.</p>
    </article>
  </main>
  <footer>
    <p>© 2025 Mon Site - Tous droits réservés</p>
    <nav aria-label="Liens du pied de page">
      <ul>
        <li><a href="/mentions">Mentions légales</a></li>
        <li><a href="/accessibilite">Accessibilité</a></li>
        <li><a href="/plan">Plan du site</a></li>
      </ul>
    </nav>
  </footer>
</body>
</html>"""

	# Parse HTML to NVDA browse mode lines
	print(f"\nConversion HTML → sortie NVDA browse mode ...")
	browse_lines = html_to_nvda_lines(html)
	print(f"  {len(browse_lines)} lignes générées.")

	# Parse HTML to Tab order lines
	print(f"Conversion HTML → ordre de tabulation ...")
	tab_lines = html_to_nvda_tab_lines(html)
	print(f"  {len(tab_lines)} éléments focusables trouvés.\n")

	# Extract page title from HTML
	import re
	title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
	page_title = title_match.group(1).strip() if title_match else url or "Page"

	# --- Start mock bridge ---
	bridge = MockNVDABridge(browse_lines, tab_lines, page_title, url or "")
	server = http.server.HTTPServer(("127.0.0.1", 8765), MockBridgeHTTPHandler)
	server.bridge = bridge
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	time.sleep(0.2)

	# Import MCP tools
	from nvda_mcp.server import (
		check_connection,
		get_focus,
		get_foreground,
		get_nvda_version,
		get_object_tree,
		get_speech_history,
		get_speech_settings,
		review_current_line,
		send_keys,
	)

	print("=" * 72)
	print(f"  SIMULATION : IA pilotant NVDA sur {url or 'page de démo'} via MCP")
	print("=" * 72)

	# --- Step 1: Connection check ---
	print("\n" + "─" * 72)
	print("ÉTAPE 1 : Connexion et identification")
	print("─" * 72)
	print(f">>> check_connection()")
	print(f"<<< {check_connection()}")
	print(f"\n>>> get_foreground()")
	print(f"<<< {get_foreground()}")
	print(f"\n>>> get_object_tree(depth=2)")
	print(f"<<< {get_object_tree(depth=2)}")

	# --- Step 2: Read current position ---
	print("\n" + "─" * 72)
	print("ÉTAPE 2 : Position courante")
	print("─" * 72)
	print(f">>> review_current_line()")
	print(f"<<< {review_current_line()}")

	# --- Step 3: Navigate with down arrow ---
	print("\n" + "─" * 72)
	print("ÉTAPE 3 : Parcours page avec flèche bas")
	print("─" * 72)

	for i in range(len(browse_lines)):
		send_keys("downArrow")
		line = review_current_line()
		print(f"  ↓  {line}")

		if bridge.current_line >= len(browse_lines) - 1:
			print("\n    ── fin de page ──")
			break

	# --- Step 4: Tab navigation ---
	print("\n" + "─" * 72)
	print("ÉTAPE 4 : Parcours page avec touche Tab (éléments focusables)")
	print("─" * 72)

	# Reset to top
	send_keys("control+home")

	for i in range(len(tab_lines)):
		send_keys("tab")
		line = review_current_line()
		# Use the tab line directly since review_current_line tracks browse lines
		if i < len(tab_lines):
			print(f"  Tab → {tab_lines[i]}")

		if bridge.current_tab >= len(tab_lines) - 1:
			print("\n    ── dernier élément focusable ──")
			break

	# --- Step 5: Speech history ---
	print("\n" + "─" * 72)
	print("ÉTAPE 5 : Historique de parole (10 dernières)")
	print("─" * 72)
	print(get_speech_history(count=10))

	server.shutdown()
	print("\n" + "=" * 72)
	print("  FIN DE LA SIMULATION")
	print("=" * 72)


if __name__ == "__main__":
	target_url = sys.argv[1] if len(sys.argv) > 1 else None
	run_demo(url=target_url)
