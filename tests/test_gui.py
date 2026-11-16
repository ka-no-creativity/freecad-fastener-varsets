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
assert dialog.short_object_names.isChecked()
assert dialog.short_dimension_names.isChecked()
dialog.check_all(False)
for key, prop, value in [("DIN912_M4", "HoleAllowance", 1),
                          ("DIN934_M4", "PressFitAllowance", -.2),
                          ("DIN7991_M5", "HeadDepthAllowance", .3)]:
    row = row_for(dialog, key)
    row.setCheckState(0, QtCore.Qt.Checked)
    dialog.tree.setCurrentItem(row)
    dialog.widgets[prop].setValue(value)
    assert dialog.entries[key]["offsets"][prop] == value
# Insert allowances start at zero and accept signed diameter/depth changes.
row = row_for(dialog, "CNCKITCHEN_M4")
row.setCheckState(0, QtCore.Qt.Checked)
dialog.tree.setCurrentItem(row)
assert dialog.widgets["InsertDiameterAllowance"].value() == 0
assert dialog.widgets["InsertDepthAllowance"].value() == 0
for prop, value in (("HoleAllowance", -.1), ("InsertDiameterAllowance", -.2), ("InsertDepthAllowance", -.5)):
    assert dialog.widgets[prop].minimum() < 0
    dialog.widgets[prop].setValue(value)
assert not dialog.validation.text()
assert "M4_Heat.InsertDia" in [dialog.preview.item(i, 2).text() for i in range(dialog.preview.rowCount())]
dialog.widgets["InsertDepthAllowance"].setValue(-1.1)
assert "at least" in dialog.validation.text()
assert dialog.preview.rowCount() == 0
dialog.widgets["InsertDepthAllowance"].setValue(-.5)
dialog.apply()
assert len(doc.Objects) == 4
assert doc.M4_Cap.HoleDia.Value == 5
assert abs(doc.M4_Nut.PressAF.Value - 6.8) < 1e-9
assert abs(doc.M4_Heat.InsertDepth.Value - 8.6) < 1e-9
assert abs(doc.M4_Heat.InsertDia.Value - 5.5) < 1e-9
assert len(Gui.Selection.getSelection()) == 4
assert doc.UndoMode == 1

# Remembered defaults are distinct per item, and are selected next time.
next_dialog = ui.FastenerDialog()
assert next_dialog.entries["DIN912_M4"]["offsets"]["HoleAllowance"] == 1
assert next_dialog.entries["DIN912_M5"]["offsets"]["HoleAllowance"] == .5
assert sum(e["checked"] for e in next_dialog.entries.values()) == 4
assert next_dialog.entries["CNCKITCHEN_M4"]["offsets"]["InsertDepthAllowance"] == -.5
next_dialog.reject()

# The library editor reloads valid JSON without dropping the current allowances.
editor = ui.LibraryEditor()
assert "DIN 912" in editor.editor.toPlainText()
editor.save()
next_dialog = ui.FastenerDialog()
next_dialog.read_library()
next_dialog.populate()
assert len(next_dialog.entries) == 20
next_dialog.reject()

# The edit dialog reads the document's saved base values, not the current library.
doc.M4_Cap.__HeadDiameter = 7.2
edit = ui.FastenerDialog([doc.M4_Cap])
assert edit.entries["M4_Cap"]["item"]["dimensions"]["HeadDiameter"] == 7.2
edit.widgets["HoleAllowance"].setValue(.8)
edit.apply()
assert doc.M4_Cap.HoleDia.Value == 4.8
assert doc.M4_Cap.__HeadDiameter.Value == 7.2
doc.undo()
assert doc.M4_Cap.HoleDia.Value == 5

# Each independent naming combination is previewed, applied and remembered.
naming_dialogs = []
for short_objects in (False, True):
    for short_dimensions in (False, True):
        naming = ui.FastenerDialog()
        naming_dialogs.append(naming)
        naming.check_all(False)
        row = row_for(naming, "CNCKITCHEN_M3")
        row.setCheckState(0, QtCore.Qt.Checked)
        naming.tree.setCurrentItem(row)
        naming.short_object_names.setChecked(short_objects)
        naming.short_dimension_names.setChecked(short_dimensions)
        base_name = "M3_Heat" if short_objects else "M3_HeatInsert"
        expected_name = doc.getUniqueObjectName(base_name)
        dimension = "InsertDia" if short_dimensions else "InsertHoleDiameter"
        refs = [naming.preview.item(i, 2).text() for i in range(naming.preview.rowCount())]
        assert f"{expected_name}.{dimension}" in refs
        naming.apply()
        obj = doc.getObject(expected_name)
        assert obj is not None and dimension in obj.PropertiesList
        assert len(Gui.Selection.getSelection()) == 1
        remembered = lib.load_preferences(ui.user_dir())
        assert remembered["short_object_names"] == short_objects
        assert remembered["short_dimension_names"] == short_dimensions
        reopened = ui.FastenerDialog()
        naming_dialogs.append(reopened)
        assert reopened.short_object_names.isChecked() == short_objects
        assert reopened.short_dimension_names.isChecked() == short_dimensions
        reopened.reject()

# Adjustment previews saved full dimension names even when creation uses short names.
full = next(obj for obj in doc.Objects if obj.Name.startswith("M3_HeatInsert") and "InsertHoleDiameter" in obj.PropertiesList)
full_edit = ui.FastenerDialog([full])
assert not hasattr(full_edit, "short_dimension_names")
assert f"{full.Name}.InsertHoleDiameter" in [full_edit.preview.item(i, 2).text() for i in range(full_edit.preview.rowCount())]
full_edit.widgets["InsertDepthAllowance"].setValue(-.75)
full_edit.apply()
assert abs(full.InsertPocketDepth.Value - 5.95) < 1e-9
assert lib.load_preferences(ui.user_dir())["short_dimension_names"]

# Legacy unprefixed projects also keep their names in the adjustment preview.
legacy, *_ = io.import_varsets(doc, lib.read_json(root / "tests/fixtures/legacy-varsets.json"))
legacy_edit = ui.FastenerDialog([legacy])
assert f"{legacy.Name}.HoleDiameter" in [legacy_edit.preview.item(i, 2).text() for i in range(legacy_edit.preview.rowCount())]
legacy_edit.widgets["HoleAllowance"].setValue(-.2)
legacy_edit.apply()
assert abs(legacy.HoleDiameter.Value - 3.8) < 1e-9
assert "__HoleAllowance" not in legacy.PropertiesList

# JSON chooser imports only the checked records.
data = io.export_varsets(doc.Objects)
chooser = ui.SnapshotChooser(data)
for i in range(chooser.items.count()):
    chooser.items.item(i).setCheckState(QtCore.Qt.Checked if i == 0 else QtCore.Qt.Unchecked)
chosen = chooser.chosen()
assert len(chosen["varsets"]) == 1
chooser.reject()

# Capture the actual dialog for a visual check, showing insert dimensions.
App.newDocument("Preview")
preview = ui.FastenerDialog()
preview.check_all(False)
preview_row = row_for(preview, "CNCKITCHEN_M4")
preview_row.setCheckState(0, QtCore.Qt.Checked)
preview.tree.setCurrentItem(preview_row)
preview.show()
QtWidgets.QApplication.processEvents()
preview.grab().save(str(root / "preview.png"))
preview.reject()

for name in list(App.listDocuments()):
    App.closeDocument(name)
# Embedded FreeCAD queues viewer destruction. Drain it while Python callbacks
# are still alive, rather than leaving Qt deferred deletes for interpreter exit.
for widget in (dialog, next_dialog, editor, edit, full_edit, legacy_edit, chooser, preview, *naming_dialogs):
    widget.deleteLater()
QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
QtWidgets.QApplication.processEvents()
Gui.getMainWindow().close()
QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
QtWidgets.QApplication.processEvents()
print("GUI PASS: workbench, insert controls, all naming combinations, expression previews, remembered signed allowances and names, legacy/full/short adjustment, library reload, undo, JSON selection.", flush=True)
