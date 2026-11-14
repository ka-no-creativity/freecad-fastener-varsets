"""Lazy-loaded FreeCAD commands."""

from pathlib import Path

import FreeCADGui as Gui

COMMANDS = [
    ("FVS_Generate", "Choose fasteners…", "Choose fasteners and set per-item printing allowances", "generate"),
    ("FVS_Adjust", "Adjust allowances…", "Adjust selected fastener VarSets using their project snapshot dimensions", "adjust"),
    ("FVS_Export", "Export VarSets to JSON…", "Export selected VarSets, or all VarSets when none are selected", "export_json"),
    ("FVS_Import", "Import VarSets from JSON…", "Choose VarSets from a JSON file and import independent copies", "import_json"),
    ("FVS_Library", "Edit central library…", "Edit the human-readable base dimension library for future imports", "show_library"),
]


class Command:
    def __init__(self, title, tooltip, action):
        self.title, self.tooltip, self.action = title, tooltip, action

    def GetResources(self):
        return {"MenuText": self.title, "ToolTip": self.tooltip,
                "Pixmap": str(Path(__file__).with_name("icon.svg"))}

    def IsActive(self):
        return True

    def Activated(self):
        from . import ui
        getattr(ui, self.action)()


def register():
    for name, title, tooltip, action in COMMANDS:
        Gui.addCommand(name, Command(title, tooltip, action))
