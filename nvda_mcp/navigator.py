#!/usr/bin/env python3
"""
NVDA Page Navigator — Real MCP client that drives NVDA like a blind user.

Connects to the NVDA MCP server and navigates a web page using real NVDA
keyboard commands. Produces a text file of the full page restitution as
NVDA announces it.

Architecture:
    This script (MCP client)
        → NVDA MCP Server (SSE)
            → NVDA Bridge Plugin (HTTP)
                → NVDA (screen reader)
                    → Firefox (browser)

Usage:
    # Start the MCP server first:
    python -m nvda_mcp --transport sse --port 8080

    # Then navigate a page:
    python -m nvda_mcp.navigator https://www.tanaguru.com
    python -m nvda_mcp.navigator https://www.tanaguru.com -o restitution.txt
"""

import argparse
import asyncio
import datetime
import sys
import time

from mcp import ClientSession
from mcp.client.sse import sse_client


# ============================================================
# NVDA keyboard commands used by blind users
# ============================================================

# Browse mode navigation (single letter keys)
NVDA_KEYS = {
	"next_line": "downArrow",
	"prev_line": "upArrow",
	"next_heading": "h",
	"prev_heading": "shift+h",
	"next_heading_1": "1",
	"next_heading_2": "2",
	"next_heading_3": "3",
	"next_heading_4": "4",
	"next_heading_5": "5",
	"next_heading_6": "6",
	"next_link": "k",
	"prev_link": "shift+k",
	"next_unvisited_link": "u",
	"next_visited_link": "v",
	"next_form_field": "f",
	"prev_form_field": "shift+f",
	"next_button": "b",
	"next_edit": "e",
	"next_list": "l",
	"next_list_item": "i",
	"next_table": "t",
	"next_graphic": "g",
	"next_landmark": "d",
	"prev_landmark": "shift+d",
	"next_separator": "s",
	"next_frame": "m",
	"top_of_page": "control+home",
	"bottom_of_page": "control+end",
	"tab": "tab",
	"shift_tab": "shift+tab",
	"enter": "enter",
	"space": "space",
	"escape": "escape",
	"address_bar": "control+l",
	"elements_list": "NVDA+f7",  # NVDA elements list dialog
}

# Maximum lines to read before stopping (safety limit)
MAX_LINES = 500

# Delay between commands (seconds) to let NVDA process
COMMAND_DELAY = 0.3


async def call_tool(session: ClientSession, name: str, args: dict | None = None) -> str:
	"""Call an MCP tool and return the text result."""
	result = await session.call_tool(name, args or {})
	# MCP returns a list of content blocks
	parts = []
	for block in result.content:
		if hasattr(block, "text"):
			parts.append(block.text)
	return "\n".join(parts)


async def send_key(session: ClientSession, key: str) -> str:
	"""Send a key and return what NVDA announced."""
	await call_tool(session, "send_keys", {"keys": key})
	await asyncio.sleep(COMMAND_DELAY)
	return await call_tool(session, "review_current_line")


async def navigate_to_url(session: ClientSession, url: str) -> str:
	"""Navigate Firefox to a URL using keyboard commands."""
	# Ctrl+L to focus address bar
	await call_tool(session, "send_keys", {"keys": "control+l"})
	await asyncio.sleep(0.5)

	# Type the URL character by character via clipboard (more reliable)
	await call_tool(session, "set_clipboard", {"text": url})
	await call_tool(session, "send_keys", {"keys": "control+v"})
	await asyncio.sleep(0.3)

	# Press Enter to load
	await call_tool(session, "send_keys", {"keys": "enter"})

	# Wait for page to load
	await asyncio.sleep(3.0)

	# Check what loaded
	return await call_tool(session, "get_foreground")


async def read_full_page(session: ClientSession) -> list[str]:
	"""Read the entire page line by line with down arrow.

	Returns the list of all lines NVDA announced.
	"""
	lines = []
	seen_lines = set()
	consecutive_empty = 0

	# Go to top of page
	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	# Read first line
	first = await call_tool(session, "review_current_line")
	text = first.replace("Current line: ", "").replace("Current line is empty.", "").strip()
	if text:
		lines.append(text)
		seen_lines.add(text)

	# Navigate down through entire page
	for _ in range(MAX_LINES):
		result = await send_key(session, "downArrow")
		text = result.replace("Current line: ", "").replace("Current line is empty.", "").strip()

		if not text:
			consecutive_empty += 1
			if consecutive_empty >= 3:
				break  # Likely at end of page
			continue

		consecutive_empty = 0

		# Detect end of page (same line repeated = stuck at bottom)
		if lines and text == lines[-1]:
			break

		lines.append(text)

	return lines


async def scan_headings(session: ClientSession) -> list[str]:
	"""Navigate through all headings using the H key.

	Returns the list of headings found.
	"""
	headings = []

	# Go to top
	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	last_text = None
	for _ in range(100):
		result = await send_key(session, "h")
		text = result.replace("Current line: ", "").strip()

		if not text or text == last_text:
			break

		# Check speech history for the heading announcement
		history = await call_tool(session, "get_speech_history", {"count": 1})
		headings.append(text)
		last_text = text

	return headings


async def scan_landmarks(session: ClientSession) -> list[str]:
	"""Navigate through all landmarks using the D key.

	Returns the list of landmarks found.
	"""
	landmarks = []

	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	last_text = None
	for _ in range(50):
		result = await send_key(session, "d")
		text = result.replace("Current line: ", "").strip()

		if not text or text == last_text:
			break

		landmarks.append(text)
		last_text = text

	return landmarks


async def scan_links(session: ClientSession) -> list[str]:
	"""Navigate through all links using the K key."""
	links = []

	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	last_text = None
	for _ in range(200):
		result = await send_key(session, "k")
		text = result.replace("Current line: ", "").strip()

		if not text or text == last_text:
			break

		links.append(text)
		last_text = text

	return links


async def scan_form_fields(session: ClientSession) -> list[str]:
	"""Navigate through all form fields using the F key."""
	fields = []

	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	last_text = None
	for _ in range(50):
		result = await send_key(session, "f")
		text = result.replace("Current line: ", "").strip()

		if not text or text == last_text:
			break

		fields.append(text)
		last_text = text

	return fields


async def scan_images(session: ClientSession) -> list[str]:
	"""Navigate through all images using the G key."""
	images = []

	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	last_text = None
	for _ in range(50):
		result = await send_key(session, "g")
		text = result.replace("Current line: ", "").strip()

		if not text or text == last_text:
			break

		images.append(text)
		last_text = text

	return images


async def scan_tables(session: ClientSession) -> list[str]:
	"""Navigate through all tables using the T key."""
	tables = []

	await call_tool(session, "send_keys", {"keys": "control+home"})
	await asyncio.sleep(COMMAND_DELAY)

	last_text = None
	for _ in range(20):
		result = await send_key(session, "t")
		text = result.replace("Current line: ", "").strip()

		if not text or text == last_text:
			break

		tables.append(text)
		last_text = text

	return tables


def format_restitution(
	url: str,
	foreground: str,
	tree: str,
	full_page: list[str],
	headings: list[str],
	landmarks: list[str],
	links: list[str],
	form_fields: list[str],
	images: list[str],
	tables: list[str],
	nvda_version: str,
	duration: float,
) -> str:
	"""Format all collected data into the restitution text file."""
	now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	sep = "=" * 72
	sub = "-" * 72

	sections = []

	# Header
	sections.append(f"""{sep}
  RESTITUTION NVDA — {url}
  Date : {now}
  NVDA : {nvda_version}
  Durée du parcours : {duration:.1f}s
{sep}""")

	# Window info
	sections.append(f"""
{sub}
  FENÊTRE ACTIVE
{sub}
{foreground}""")

	# Object tree / landmarks structure
	sections.append(f"""
{sub}
  ARBRE D'ACCESSIBILITÉ
{sub}
{tree}""")

	# Landmarks
	sections.append(f"""
{sub}
  REPÈRES / LANDMARKS ({len(landmarks)})
  Navigation : touche D
{sub}""")
	if landmarks:
		for i, lm in enumerate(landmarks, 1):
			sections.append(f"  {i:3d}. {lm}")
	else:
		sections.append("  (aucun repère trouvé)")

	# Headings
	sections.append(f"""
{sub}
  TITRES / HEADINGS ({len(headings)})
  Navigation : touche H
{sub}""")
	if headings:
		for i, h in enumerate(headings, 1):
			sections.append(f"  {i:3d}. {h}")
	else:
		sections.append("  (aucun titre trouvé)")

	# Full page content
	sections.append(f"""
{sub}
  PARCOURS COMPLET — LIGNE PAR LIGNE ({len(full_page)} lignes)
  Navigation : flèche bas (downArrow)
{sub}""")
	for i, line in enumerate(full_page, 1):
		sections.append(f"  {i:3d}. {line}")

	# Links
	sections.append(f"""
{sub}
  LIENS ({len(links)})
  Navigation : touche K
{sub}""")
	if links:
		for i, lk in enumerate(links, 1):
			sections.append(f"  {i:3d}. {lk}")
	else:
		sections.append("  (aucun lien trouvé)")

	# Form fields
	sections.append(f"""
{sub}
  CHAMPS DE FORMULAIRE ({len(form_fields)})
  Navigation : touche F
{sub}""")
	if form_fields:
		for i, f in enumerate(form_fields, 1):
			sections.append(f"  {i:3d}. {f}")
	else:
		sections.append("  (aucun champ de formulaire trouvé)")

	# Images
	sections.append(f"""
{sub}
  IMAGES / GRAPHIQUES ({len(images)})
  Navigation : touche G
{sub}""")
	if images:
		for i, img in enumerate(images, 1):
			sections.append(f"  {i:3d}. {img}")
	else:
		sections.append("  (aucune image trouvée)")

	# Tables
	sections.append(f"""
{sub}
  TABLEAUX ({len(tables)})
  Navigation : touche T
{sub}""")
	if tables:
		for i, tbl in enumerate(tables, 1):
			sections.append(f"  {i:3d}. {tbl}")
	else:
		sections.append("  (aucun tableau trouvé)")

	# Footer
	sections.append(f"""
{sep}
  FIN DE RESTITUTION
{sep}""")

	return "\n".join(sections)


async def run_navigator(url: str, mcp_url: str, output: str | None, skip_nav: bool):
	"""Main navigation workflow."""
	t0 = time.time()

	print(f"Connexion au serveur MCP : {mcp_url}")
	async with sse_client(mcp_url) as (read, write):
		async with ClientSession(read, write) as session:
			await session.initialize()

			# Verify connection
			print("Vérification de la connexion NVDA...")
			conn = await call_tool(session, "check_connection")
			print(f"  {conn}")

			nvda_version = await call_tool(session, "get_nvda_version")
			print(f"  {nvda_version}")

			# Navigate to URL
			if not skip_nav:
				print(f"\nNavigation vers : {url}")
				foreground = await navigate_to_url(session, url)
				print(f"  {foreground}")
			else:
				print(f"\nPage courante (--skip-nav)")
				foreground = await call_tool(session, "get_foreground")
				print(f"  {foreground}")

			# Get accessibility tree
			print("\nLecture de l'arbre d'accessibilité...")
			tree = await call_tool(session, "get_object_tree", {"depth": 3, "from_object": "focus"})
			print(f"  OK")

			# Scan landmarks
			print("Scan des repères (touche D)...")
			landmarks = await scan_landmarks(session)
			print(f"  {len(landmarks)} repères trouvés")

			# Scan headings
			print("Scan des titres (touche H)...")
			headings = await scan_headings(session)
			print(f"  {len(headings)} titres trouvés")

			# Full page read
			print("Parcours complet de la page (flèche bas)...")
			full_page = await read_full_page(session)
			print(f"  {len(full_page)} lignes lues")

			# Scan links
			print("Scan des liens (touche K)...")
			links = await scan_links(session)
			print(f"  {len(links)} liens trouvés")

			# Scan form fields
			print("Scan des champs de formulaire (touche F)...")
			form_fields = await scan_form_fields(session)
			print(f"  {len(form_fields)} champs trouvés")

			# Scan images
			print("Scan des images (touche G)...")
			images = await scan_images(session)
			print(f"  {len(images)} images trouvées")

			# Scan tables
			print("Scan des tableaux (touche T)...")
			tables = await scan_tables(session)
			print(f"  {len(tables)} tableaux trouvés")

			duration = time.time() - t0

			# Build restitution
			restitution = format_restitution(
				url=url,
				foreground=foreground,
				tree=tree,
				full_page=full_page,
				headings=headings,
				landmarks=landmarks,
				links=links,
				form_fields=form_fields,
				images=images,
				tables=tables,
				nvda_version=nvda_version,
				duration=duration,
			)

			# Output
			if output:
				with open(output, "w", encoding="utf-8") as f:
					f.write(restitution)
				print(f"\nRestitution écrite dans : {output}")
			else:
				print()
				print(restitution)

			print(f"\nTerminé en {duration:.1f}s.")


def main():
	parser = argparse.ArgumentParser(
		description="NVDA Page Navigator — Parcourt une page web via NVDA et produit la restitution",
	)
	parser.add_argument(
		"url",
		help="URL de la page à parcourir",
	)
	parser.add_argument(
		"-o", "--output",
		help="Fichier de sortie pour la restitution (défaut : stdout)",
	)
	parser.add_argument(
		"--mcp-url",
		default="http://localhost:8080/sse",
		help="URL du serveur MCP SSE (défaut : http://localhost:8080/sse)",
	)
	parser.add_argument(
		"--skip-nav",
		action="store_true",
		help="Ne pas naviguer vers l'URL (la page est déjà ouverte)",
	)
	parser.add_argument(
		"--delay",
		type=float,
		default=0.3,
		help="Délai entre les commandes en secondes (défaut : 0.3)",
	)
	args = parser.parse_args()

	global COMMAND_DELAY
	COMMAND_DELAY = args.delay

	asyncio.run(run_navigator(args.url, args.mcp_url, args.output, args.skip_nav))


if __name__ == "__main__":
	main()
