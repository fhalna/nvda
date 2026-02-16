#!/usr/bin/env python3
"""Build the NVDA MCP Bridge addon (.nvda-addon file).

An NVDA addon is a ZIP file with extension .nvda-addon containing:
    manifest.ini
    globalPlugins/
        nvdaMCPBridge/
            __init__.py

Usage:
    python build_addon.py
    # Produces: nvdaMCPBridge-0.1.0.nvda-addon
"""

import os
import zipfile

ADDON_DIR = os.path.join(os.path.dirname(__file__), "addon")
OUTPUT_DIR = os.path.dirname(__file__)


def build():
	# Read version from manifest
	manifest_path = os.path.join(ADDON_DIR, "manifest.ini")
	version = "0.1.0"
	with open(manifest_path, encoding="utf-8") as f:
		for line in f:
			if line.startswith("version"):
				version = line.split("=", 1)[1].strip()
				break

	output_name = f"nvdaMCPBridge-{version}.nvda-addon"
	output_path = os.path.join(OUTPUT_DIR, output_name)

	with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
		for root, dirs, files in os.walk(ADDON_DIR):
			for file in files:
				full_path = os.path.join(root, file)
				arc_name = os.path.relpath(full_path, ADDON_DIR)
				# Skip __pycache__
				if "__pycache__" in arc_name:
					continue
				zf.write(full_path, arc_name)
				print(f"  + {arc_name}")

	print(f"\nAddon créé : {output_path}")
	print(f"Taille : {os.path.getsize(output_path)} octets")
	print(f"\nPour installer : double-cliquez sur {output_name} (NVDA doit être lancé)")


if __name__ == "__main__":
	build()
