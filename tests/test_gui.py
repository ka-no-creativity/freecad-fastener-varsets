"""Real FreeCAD GUI integration, rendered offscreen with isolated preferences."""

import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
temporary = tempfile.TemporaryDirectory(prefix="fvs-gui-")
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic", QT_STYLE_OVERRIDE="Fusion",
                  XDG_CONFIG_HOME=temporary.name + "/config", XDG_DATA_HOME=temporary.name + "/data",
                  XDG_CACHE_HOME=temporary.name + "/cache")
sys.path.insert(0, "/usr/lib/freecad/lib")
sys.path.insert(0, str(root))

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

Gui.showMainWindow()
Gui.getMainWindow().hide()
exec(compile((root / "InitGui.py").read_text(), str(root / "InitGui.py"), "exec"))
Gui.activateWorkbench("FastenerVarSetsWorkbench")
assert Gui.activeWorkbench().name() == "FastenerVarSetsWorkbench"

from fastener_varsets import ui
from fastener_varsets import library as lib
from fastener_varsets import freecad_io as io

ui.user_dir = lambda: Path(temporary.name) / "library"


def raise_errors(exc, parent=None):
    raise exc


ui.error = raise_errors


def row_for(dialog, key):
    iterator = QtWidgets.QTreeWidgetItemIterator(dialog.tree)
    while iterator.value():
        row = iterator.value()
        if row.data(0, QtCore.Qt.UserRole) == key:
            return row
        iterator += 1
    raise AssertionError(f"Missing row {key}")


doc = App.newDocument("UITest")
doc.UndoMode = 1
dialog = ui.FastenerDialog()
dialog.check_all(False)
for key, prop, value in [("DIN912_M4", "HoleAllowance", 1),
                          ("DIN934_M4", "PressFitAllowance", -.2),
                          ("DIN7991_M5", "HeadDepthAllowance", .3)]:
    row = row_for(dialog, key)
    row.setCheckState(0, QtCore.Qt.Checked)
    dialog.tree.setCurrentItem(row)
    dialog.widgets[prop].setValue(value)
    assert dialog.entries[key]["offsets"][prop] == value
dialog.apply()
assert len(doc.Objects) == 3
assert doc.M4_SocketCap.HoleDiameter.Value == 5
assert abs(doc.M4_Nut.PressFitAcrossFlats.Value - 6.8) < 1e-9
assert len(Gui.Selection.getSelection()) == 3
assert doc.UndoMode == 1

# Remembered defaults are distinct per item, and are selected next time.
next_dialog = ui.FastenerDialog()
assert next_dialog.entries["DIN912_M4"]["offsets"]["HoleAllowance"] == 1
assert next_dialog.entries["DIN912_M5"]["offsets"]["HoleAllowance"] == .5
assert sum(e["checked"] for e in next_dialog.entries.values()) == 3
next_dialog.reject()

# The library editor reloads valid JSON without dropping the current allowances.
editor = ui.LibraryEditor()
assert "DIN 912" in editor.editor.toPlainText()
editor.save()
next_dialog = ui.FastenerDialog()
next_dialog.read_library()
next_dialog.populate()
assert len(next_dialog.entries) == 15
next_dialog.reject()

# The edit dialog reads the document's saved base values, not the current library.
doc.M4_SocketCap.HeadDiameter = 7.2
edit = ui.FastenerDialog([doc.M4_SocketCap])
assert edit.entries["M4_SocketCap"]["item"]["dimensions"]["HeadDiameter"] == 7.2
edit.widgets["HoleAllowance"].setValue(.8)
edit.apply()
assert doc.M4_SocketCap.HoleDiameter.Value == 4.8
assert doc.M4_SocketCap.HeadDiameter.Value == 7.2
doc.undo()
assert doc.M4_SocketCap.HoleDiameter.Value == 5

# JSON chooser imports only the checked records.
data = io.export_varsets(doc.Objects)
chooser = ui.SnapshotChooser(data)
for i in range(chooser.items.count()):
    chooser.items.item(i).setCheckState(QtCore.Qt.Checked if i == 0 else QtCore.Qt.Unchecked)
chosen = chooser.chosen()
assert len(chosen["varsets"]) == 1
chooser.reject()

# Capture the actual dialog for a visual check, showing the nut fit dimensions.
preview = ui.FastenerDialog()
preview.tree.setCurrentItem(row_for(preview, "DIN934_M4"))
preview.show()
QtWidgets.QApplication.processEvents()
preview.grab().save(str(root / "preview.png"))
preview.reject()

for name in list(App.listDocuments()):
    App.closeDocument(name)
# Embedded FreeCAD queues viewer destruction. Drain it while Python callbacks
# are still alive, rather than leaving Qt deferred deletes for interpreter exit.
for widget in (dialog, next_dialog, editor, edit, chooser, preview):
    widget.deleteLater()
QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
QtWidgets.QApplication.processEvents()
Gui.getMainWindow().close()
QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
QtWidgets.QApplication.processEvents()
print("GUI PASS: workbench, checkbox selection, per-item edits, remembered allowances, library reload, snapshot edit, undo, JSON selection.", flush=True)
