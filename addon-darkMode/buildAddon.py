#!/usr/bin/env python3
"""
Build script for Dark Mode NVDA add-on.
Creates a .nvda-addon file that can be installed via NVDA's Add-on Manager.
"""

import os
import zipfile
import configparser

def build_addon():
    # Get the directory where this script is located
    addon_dir = os.path.dirname(os.path.abspath(__file__))

    # Read manifest to get add-on name and version
    manifest_path = os.path.join(addon_dir, "manifest.ini")
    config = configparser.ConfigParser()
    config.read(manifest_path)

    name = config.get("General", "name", fallback="darkMode")
    version = config.get("General", "version", fallback="1.0.0")

    # Output filename
    output_filename = f"{name}-{version}.nvda-addon"
    output_path = os.path.join(addon_dir, output_filename)

    # Files/folders to include
    include_items = [
        "manifest.ini",
        "globalPlugins",
    ]

    # Create the zip file
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in include_items:
            item_path = os.path.join(addon_dir, item)
            if os.path.isfile(item_path):
                zf.write(item_path, item)
                print(f"Added: {item}")
            elif os.path.isdir(item_path):
                for root, dirs, files in os.walk(item_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, addon_dir)
                        zf.write(file_path, arcname)
                        print(f"Added: {arcname}")

    print(f"\nAdd-on package created: {output_path}")
    print(f"Install by double-clicking the file or via NVDA's Add-on Manager.")

if __name__ == "__main__":
    build_addon()
