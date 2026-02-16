#!/usr/bin/env python3
"""
Simulation: an AI browses www.tanaguru.com using the NVDA MCP server.

This script mocks the NVDA bridge HTTP server with realistic data
and runs the MCP tools against it, simulating what an AI would
receive when navigating tanaguru.com with the down arrow key.

Usage:
    python -m nvda_mcp.demo_browse_tanaguru
"""

import http.server
import json
import threading
import time

# ============================================================
# Simulated NVDA browse mode content for www.tanaguru.com
# In NVDA browse mode, down arrow reads line by line through
# the virtual buffer. Each entry represents one "line" that
# NVDA would announce.
# ============================================================

TANAGURU_BROWSE_LINES = [
	# -- Banner / Skip links --
	"lien Aller au contenu",
	# -- Header navigation --
	"bannière  repère",
	"lien graphique  logo Tanaguru",
	"navigation  repère",
	"liste de 6 éléments",
	"lien Services",
	"lien Formations",
	"lien Outils open source",
	"lien Blog",
	"lien Contact",
	"lien Accessibilité",
	"fin de liste",
	"fin de navigation  repère",
	"fin de bannière  repère",
	# -- Main content --
	"contenu principal  repère",
	# Hero section
	"titre de niveau 1  L'accessibilité numérique, simplement",
	"Tanaguru est une équipe pluridisciplinaire et un ensemble d'outils entièrement dédiés à la qualité et à l'accessibilité du web.",
	"lien Découvrir nos services",
	"lien Nous contacter",
	# Services section
	"titre de niveau 2  Nos services",
	"liste de 4 éléments",
	# Audit
	"titre de niveau 3  lien Audit",
	"Nous réalisons des audits de conformité (RGAA, WCAG) pour mesurer et améliorer l'accessibilité de vos supports numériques.",
	# Accompagnement
	"titre de niveau 3  lien Accompagnement",
	"Nous vous accompagnons à chaque étape de vos projets numériques pour intégrer l'accessibilité dès la conception.",
	# Formation
	"titre de niveau 3  lien Formation",
	"Nos formations couvrent tous les profils : design, développement, gestion de projet, rédaction de contenus, audit RGAA.",
	# Outils
	"titre de niveau 3  lien Outils open source",
	"Tanaguru Engine automatise environ 180 tests d'accessibilité issus du RGAA, AccessiWeb et des WCAG.",
	"fin de liste",
	# Chiffres / Highlights
	"titre de niveau 2  Quelques chiffres",
	"20  ans d'expérience en accessibilité numérique",
	"1 000  personnes formées depuis 2021",
	"180  tests automatisés par Tanaguru Engine",
	"106  critères du RGAA couverts par nos audits",
	# Blog / actualités
	"titre de niveau 2  Actualités",
	"titre de niveau 3  lien (Re)voir le webinaire Design accessible : par où commencer ?",
	"Frédéric Halna, président de Tanaguru et consultant en accessibilité, entre dans sa 20ème année de travail sur l'accessibilité numérique.",
	"lien Lire la suite",
	"titre de niveau 3  lien Automatiser vos tests d'accessibilité avec Tanaguru Engine",
	"Découvrez comment Tanaguru Engine peut vous aider à standardiser et accélérer vos tests d'accessibilité.",
	"lien Lire la suite",
	"fin de contenu principal  repère",
	# -- Footer --
	"informations de contenu  repère",
	"titre de niveau 2  Tanaguru",
	"8 rue des Pirates",
	"75013 Paris",
	"lien contact@tanaguru.com",
	"lien 01 23 45 67 89",
	"liste de 3 éléments",
	"lien graphique  LinkedIn",
	"lien graphique  GitHub",
	"lien graphique  Twitter",
	"fin de liste",
	"lien Mentions légales",
	"lien Politique de confidentialité",
	"lien Accessibilité : partiellement conforme",
	"lien Plan du site",
	"© 2025 Tanaguru - Tous droits réservés",
	"fin de informations de contenu  repère",
]

# Current position in the virtual buffer
_current_line = 0
_speech_history = []
_focus_info = {
	"name": "L'accessibilité numérique, simplement | Tanaguru - Mozilla Firefox",
	"role": "fenêtre de cadre",
	"roleId": "FRAME",
	"value": "",
	"description": "",
	"states": ["focalisé"],
	"stateIds": ["FOCUSED"],
	"childCount": 1,
	"windowClassName": "MozillaWindowClass",
	"appName": "firefox",
}
_foreground_info = {
	"name": "L'accessibilité numérique, simplement | Tanaguru - Mozilla Firefox",
	"role": "fenêtre de cadre",
	"roleId": "FRAME",
	"value": "",
	"description": "",
	"states": [],
	"stateIds": [],
	"childCount": 5,
	"windowClassName": "MozillaWindowClass",
	"appName": "firefox",
	"location": {"left": 0, "top": 0, "width": 1920, "height": 1080},
}


class MockBridgeHandler(http.server.BaseHTTPRequestHandler):
	def do_POST(self):
		global _current_line
		content_length = int(self.headers.get("Content-Length", 0))
		body = self.rfile.read(content_length)
		request = json.loads(body)
		method = request.get("method")
		params = request.get("params", {})
		result = {}

		if method == "speak":
			text = params.get("text", "")
			_speech_history.append(text)
			result = {"spoken": text}

		elif method == "cancelSpeech":
			result = {"cancelled": True}

		elif method == "getSpeechHistory":
			count = params.get("count", 10)
			result = {"history": _speech_history[-count:]}

		elif method == "getFocus":
			result = _focus_info

		elif method == "getForeground":
			result = _foreground_info

		elif method == "getVersion":
			result = {"version": "2025.1", "name": "NVDA"}

		elif method == "getStatusBar":
			result = {"text": "", "found": False}

		elif method == "sendKeys":
			keys = params.get("keys", "")
			if keys == "downArrow":
				if _current_line < len(TANAGURU_BROWSE_LINES) - 1:
					_current_line += 1
				line_text = TANAGURU_BROWSE_LINES[_current_line]
				_speech_history.append(line_text)
			elif keys == "upArrow":
				if _current_line > 0:
					_current_line -= 1
				line_text = TANAGURU_BROWSE_LINES[_current_line]
				_speech_history.append(line_text)
			result = {"sent": keys}

		elif method == "reviewCurrentLine":
			result = {"text": TANAGURU_BROWSE_LINES[_current_line]}

		elif method == "getClipboard":
			result = {"text": ""}

		elif method == "getNavigator":
			line = TANAGURU_BROWSE_LINES[_current_line]
			# Determine role from the line content
			role = "texte"
			if line.startswith("titre de niveau"):
				role = "titre"
			elif line.startswith("lien"):
				role = "lien"
			elif line.startswith("liste"):
				role = "liste"
			elif "repère" in line:
				role = "repère"
			result = {
				"name": line,
				"role": role,
				"roleId": role.upper(),
				"value": "",
				"description": "",
				"states": [],
				"stateIds": [],
				"childCount": 0,
				"appName": "firefox",
			}

		elif method == "getSpeechSettings":
			result = {
				"synthName": "OneCore",
				"synthId": "oneCore",
				"rate": 50,
				"volume": 100,
				"voice": "Microsoft Hortense",
			}

		elif method == "getObjectTree":
			result = {
				"name": "L'accessibilité numérique, simplement | Tanaguru",
				"role": "document",
				"roleId": "DOCUMENT",
				"value": "https://www.tanaguru.com",
				"description": "",
				"states": ["focalisé", "lecture seule"],
				"stateIds": ["FOCUSED", "READONLY"],
				"childCount": 3,
				"appName": "firefox",
				"children": [
					{
						"name": "",
						"role": "bannière",
						"roleId": "BANNER",
						"value": "",
						"states": [],
						"stateIds": [],
						"childCount": 12,
						"children": [],
					},
					{
						"name": "",
						"role": "contenu principal",
						"roleId": "MAIN",
						"value": "",
						"states": [],
						"stateIds": [],
						"childCount": 25,
						"children": [],
					},
					{
						"name": "",
						"role": "informations de contenu",
						"roleId": "CONTENTINFO",
						"value": "",
						"states": [],
						"stateIds": [],
						"childCount": 10,
						"children": [],
					},
				],
			}

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
		pass  # Silence HTTP logs


def run_demo():
	global _current_line
	# Start mock bridge
	server = http.server.HTTPServer(("127.0.0.1", 8765), MockBridgeHandler)
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	time.sleep(0.3)

	# Import MCP tools (they connect to localhost:8765)
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
	print("  SIMULATION : IA pilotant NVDA sur www.tanaguru.com via MCP")
	print("  (Chaque section montre l'appel MCP et la réponse reçue par l'IA)")
	print("=" * 72)

	# Step 1: Check connection
	print("\n" + "─" * 72)
	print("ÉTAPE 1 : L'IA vérifie la connexion à NVDA")
	print("─" * 72)
	print(f">>> check_connection()")
	result = check_connection()
	print(f"<<< {result}")

	# Step 2: Get NVDA version
	print(f"\n>>> get_nvda_version()")
	result = get_nvda_version()
	print(f"<<< {result}")

	# Step 3: Get speech settings
	print(f"\n>>> get_speech_settings()")
	result = get_speech_settings()
	print(f"<<< {result}")

	# Step 4: Check what window is in foreground
	print("\n" + "─" * 72)
	print("ÉTAPE 2 : L'IA identifie la fenêtre active")
	print("─" * 72)
	print(f">>> get_foreground()")
	result = get_foreground()
	print(f"<<< {result}")

	print(f"\n>>> get_focus()")
	result = get_focus()
	print(f"<<< {result}")

	# Step 5: Get the page structure
	print("\n" + "─" * 72)
	print("ÉTAPE 3 : L'IA obtient la structure de la page")
	print("─" * 72)
	print(f">>> get_object_tree(depth=2, from_object='focus')")
	result = get_object_tree(depth=2, from_object="focus")
	print(f"<<< {result}")

	# Step 6: Read current position
	print("\n" + "─" * 72)
	print("ÉTAPE 4 : L'IA lit la position courante")
	print("─" * 72)
	_current_line = 0
	print(f">>> review_current_line()")
	result = review_current_line()
	print(f"<<< {result}")

	# Step 7: Navigate with down arrow
	print("\n" + "─" * 72)
	print("ÉTAPE 5 : L'IA parcourt la page avec flèche bas (downArrow)")
	print("         Chaque appel = 1 appui sur flèche bas + lecture de la ligne")
	print("─" * 72)

	for i in range(len(TANAGURU_BROWSE_LINES)):
		print(f"\n>>> send_keys('downArrow')")
		send_result = send_keys("downArrow")

		print(f">>> review_current_line()")
		line_result = review_current_line()
		print(f"<<< {line_result}")

		# Stop if at end
		if _current_line >= len(TANAGURU_BROWSE_LINES) - 1:
			print("\n    (Fin de page atteinte)")
			break

	# Step 8: Check speech history
	print("\n" + "─" * 72)
	print("ÉTAPE 6 : L'IA consulte l'historique de parole (dernières 10 entrées)")
	print("─" * 72)
	print(f">>> get_speech_history(count=10)")
	result = get_speech_history(count=10)
	print(f"<<< {result}")

	server.shutdown()
	print("\n" + "=" * 72)
	print("  FIN DE LA SIMULATION")
	print("=" * 72)


if __name__ == "__main__":
	run_demo()
