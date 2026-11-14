"""FreeCAD discovers this file in the user Mod directory."""

import FreeCADGui as Gui
from pathlib import Path
import fastener_varsets


class FastenerVarSetsWorkbench(Gui.Workbench):
    MenuText = "Fastener VarSets"
    ToolTip = "Fastener dimension snapshots and per-item allowances for printed parts"
    Icon = str(Path(fastener_varsets.__file__).with_name("icon.svg"))

    def Initialize(self):
        from fastener_varsets.commands import COMMANDS, register
        register()
        commands = [entry[0] for entry in COMMANDS]
        self.appendToolbar("Fastener VarSets", commands)
        self.appendMenu("Fastener VarSets", commands)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(FastenerVarSetsWorkbench())
