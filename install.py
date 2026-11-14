#!/usr/bin/env python3
"""Install a local workbench and macro by symlink; never replace unrelated files."""

import argparse
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent


def install_link(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() and destination.resolve() == source.resolve():
        print(f"Already installed: {destination}")
        return
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"Refusing to replace an existing path: {destination}")
    destination.symlink_to(source, target_is_directory=source.is_dir())
    print(f"Installed: {destination} -> {source}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-data", type=Path, help="Override FreeCAD's user application data directory")
    args = parser.parse_args()
    if args.user_data:
        target = args.user_data.expanduser().resolve()
    else:
        try:
            import FreeCAD
        except ImportError:
            sys.path.insert(0, "/usr/lib/freecad/lib")
            import FreeCAD
        target = Path(FreeCAD.getUserAppDataDir())
    # Check both paths before installing either link.
    pairs = [(SOURCE, target / "Mod" / "FastenerVarSets"),
             (SOURCE / "FastenerVarSets.FCMacro", target / "Macro" / "FastenerVarSets.FCMacro")]
    for source, destination in pairs:
        if (destination.exists() or destination.is_symlink()) and not (destination.is_symlink() and destination.resolve() == source.resolve()):
            raise RuntimeError(f"Refusing to replace an existing path: {destination}")
    for source, destination in pairs:
        install_link(source, destination)
    from fastener_varsets import library
    location = target / "FastenerVarSets"
    library.load_library(location)
    if not (location / "allowances.json").exists():
        library.write_json(location / "allowances.json", {"version": 1, "items": {}, "selected": []})
    print(f"Central library: {location / 'library.json'}")
    print("Restart FreeCAD and select the Fastener VarSets workbench.")


if __name__ == "__main__":
    main()
