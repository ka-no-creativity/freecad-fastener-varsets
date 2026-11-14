"""FreeCAD dialogs. No running observers, document links, or custom proxies."""

import copy
import json
from pathlib import Path
import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from . import freecad_io as io
from . import library as lib


def user_dir():
    return Path(App.getUserAppDataDir()) / "FastenerVarSets"


def execute(dialog):
    return dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()


def error(exc, parent=None):
    QtWidgets.QMessageBox.warning(parent or Gui.getMainWindow(), "Fastener VarSets", str(exc))


def selected_varsets():
    return [obj for obj in Gui.Selection.getSelection() if obj.TypeId == "App::VarSet"]


def select_created(objects):
    Gui.Selection.clearSelection()
    for obj in objects:
        Gui.Selection.addSelection(obj)
    App.Console.PrintMessage(f"Fastener VarSets: {len(objects)} VarSet(s) ready.\n")


class LibraryEditor(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Central fastener library — JSON")
        self.resize(850, 650)
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel("Edit the base dimensions here. Values are millimetres (angles: degrees).\n"
                                "Saving affects future imports; existing projects keep their snapshots.")
        layout.addWidget(note)
        self.path = user_dir() / "library.json"
        layout.addWidget(QtWidgets.QLabel(str(self.path)))
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setPlainText(self.path.read_text(encoding="utf-8"))
        layout.addWidget(self.editor)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            data = lib.validate_library(json.loads(self.editor.toPlainText()))
            lib.write_json(self.path, data)
            self.accept()
        except Exception as exc:
            error(exc, self)


class FastenerDialog(QtWidgets.QDialog):
    def __init__(self, objects=None, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.editing = bool(objects)
        self.doc = objects[0].Document if self.editing else App.ActiveDocument
        self.preferences = lib.load_preferences(user_dir())
        self.entries = {}
        self.current_key = None
        self.widgets = {}
        self.setWindowTitle("Adjust fastener allowances" if self.editing else "Fastener VarSets")
        self.resize(1020, 760)
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel("Check the items to create. Select a row to adjust that item's allowances.\n"
                                "Each allowance is a TOTAL addition: M4 + 1 mm = a 5 mm hole. Negative values make a pocket smaller."
                                if not self.editing else
                                "Adjust the checked project VarSets using their own saved dimensions.\n"
                                "Each allowance is a TOTAL addition. Other projects and base library values stay independent.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter, 1)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Fastener", "Standard"])
        self.tree.setColumnWidth(0, 210)
        self.tree.currentItemChanged.connect(self.changed_item)
        self.tree.itemChanged.connect(self.remember_checks)
        left_layout.addWidget(self.tree)
        selection = QtWidgets.QHBoxLayout()
        for label, checked in (("Check all", True), ("Uncheck all", False)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _=False, value=checked: self.check_all(value))
            selection.addWidget(button)
        left_layout.addLayout(selection)
        if not self.editing:
            library_button = QtWidgets.QPushButton("Edit central library JSON…")
            library_button.clicked.connect(self.edit_library)
            left_layout.addWidget(library_button)
        splitter.addWidget(left)
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        self.title = QtWidgets.QLabel()
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        right_layout.addWidget(self.title)
        self.form_box = QtWidgets.QGroupBox("Allowances for this item")
        self.form = QtWidgets.QFormLayout(self.form_box)
        right_layout.addWidget(self.form_box)
        self.detail = QtWidgets.QLabel()
        self.detail.setWordWrap(True)
        right_layout.addWidget(self.detail)
        self.preview = QtWidgets.QTableWidget(0, 2)
        self.preview.setHorizontalHeaderLabels(["Dimension", "Result"])
        self.preview.horizontalHeader().setStretchLastSection(True)
        self.preview.setColumnWidth(0, 235)
        self.preview.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.preview.verticalHeader().setVisible(False)
        right_layout.addWidget(self.preview, 1)
        self.validation = QtWidgets.QLabel()
        self.validation.setWordWrap(True)
        right_layout.addWidget(self.validation)
        splitter.addWidget(right)
        splitter.setSizes([350, 630])
        self.footer = QtWidgets.QLabel()
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        if not self.editing:
            remember = QtWidgets.QPushButton("Save allowances only")
            remember.clicked.connect(self.remember_only)
            buttons.addWidget(remember)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.submit = QtWidgets.QPushButton("Apply to checked VarSets" if self.editing else "Create checked VarSets")
        self.submit.setDefault(True)
        self.submit.clicked.connect(self.apply)
        buttons.addWidget(self.submit)
        layout.addLayout(buttons)
        if self.editing:
            for obj in objects:
                item, offsets = io.item_from_object(obj)
                self.entries[obj.Name] = {"item": item, "offsets": offsets, "object": obj, "checked": True}
        else:
            self.read_library()
        self.populate()

    def read_library(self):
        library = lib.load_library(user_dir())
        old = self.entries
        self.entries = {}
        for item in library["items"]:
            key = item["id"]
            previous = old.get(key)
            values = previous["offsets"] if previous else self.preferences["items"].get(key, {})
            self.entries[key] = {"item": item, "offsets": lib.allowances(item, values),
                                 "checked": previous["checked"] if previous else key in self.preferences.get("selected", [])}

    def populate(self):
        self.current_key = None
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}
        first = None
        for key, entry in self.entries.items():
            kind = entry["item"]["kind"]
            if kind not in groups:
                groups[kind] = QtWidgets.QTreeWidgetItem(self.tree, [lib.KINDS[kind]])
                groups[kind].setFlags(groups[kind].flags() & ~QtCore.Qt.ItemIsSelectable)
                groups[kind].setExpanded(True)
            item = entry["item"]
            row = QtWidgets.QTreeWidgetItem(groups[kind], [item["label"] if self.editing else item["size"], item["standard"]])
            row.setData(0, QtCore.Qt.UserRole, key)
            row.setFlags(row.flags() | QtCore.Qt.ItemIsUserCheckable)
            row.setCheckState(0, QtCore.Qt.Checked if entry["checked"] else QtCore.Qt.Unchecked)
            first = first or row
        self.tree.setCurrentItem(first)
        self.tree.blockSignals(False)
        self.changed_item(first, None)

    def remember_checks(self, *_):
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            row = iterator.value()
            key = row.data(0, QtCore.Qt.UserRole)
            if key in self.entries:
                self.entries[key]["checked"] = row.checkState(0) == QtCore.Qt.Checked
            iterator += 1
        count = sum(entry["checked"] for entry in self.entries.values())
        self.footer.setText(f"{count} item(s) checked. Allowances are remembered separately for every type and size.\n"
                            "Starting allowances are editable examples; tune them to your printer and actual metal fasteners.")

    def check_all(self, checked):
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            row = iterator.value()
            if row.data(0, QtCore.Qt.UserRole) in self.entries:
                row.setCheckState(0, QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
            iterator += 1

    def changed_item(self, row, _previous):
        key = row.data(0, QtCore.Qt.UserRole) if row else None
        if key not in self.entries:
            return
        self.current_key = key
        while self.form.rowCount():
            self.form.removeRow(0)
        self.widgets = {}
        entry = self.entries[key]
        self.title.setText(entry["item"]["label"])
        for prop, label, _ in lib.fields(entry["item"]["kind"]):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setRange(-100, 100)
            spin.setSingleStep(0.05)
            spin.setSuffix(" mm")
            spin.setValue(entry["offsets"][prop])
            spin.setToolTip("Total addition to this dimension, not per side. Negative values reduce it.")
            self.form.addRow(label + " +", spin)
            self.widgets[prop] = spin
            spin.valueChanged.connect(self.update_preview)
        kind = entry["item"]["kind"]
        self.detail.setText(
            "Nut fit allowances apply across FLATS. Diameters across CORNERS are calculated from the resulting hexagon.\n"
            "For Sketcher's polygon circumradius use LooseFitDiameter / 2 or PressFitDiameter / 2."
            if kind == "hex_nut" else
            "Countersink depth and mouth diameter stay consistent with the head angle. Extra depth also widens the mouth.\n"
            "Tap hole = base cutting-tap drill + this item's tap allowance."
            if kind == "countersunk" else
            "Tap hole = base cutting-tap drill (Kernloch) + this item's tap allowance.\n"
            "Head recess diameter and depth have independent allowances.")
        self.update_preview()
        self.remember_checks()

    def update_preview(self, *_):
        if self.current_key is None:
            return
        entry = self.entries[self.current_key]
        entry["offsets"] = {key: spin.value() for key, spin in self.widgets.items()}
        try:
            result = lib.calculate(entry["item"], entry["offsets"])
            self.validation.clear()
        except ValueError as exc:
            self.validation.setText(str(exc))
            self.preview.setRowCount(0)
            return
        self.preview.setRowCount(len(result))
        # Cutout dimensions first, followed by the unmodified library dimensions.
        base = entry["item"]["dimensions"]
        ordered = [key for key in result if key not in base] + list(base)
        for i, key in enumerate(ordered):
            label = " ".join(re.findall("[A-Z][a-z]*|[0-9]+", key))
            self.preview.setItem(i, 0, QtWidgets.QTableWidgetItem(label))
            self.preview.setItem(i, 1, QtWidgets.QTableWidgetItem(f'{result[key]:.3f} {"°" if key == "CountersinkAngle" else "mm"}'))

    def save_preferences(self):
        data = copy.deepcopy(self.preferences)
        for entry in self.entries.values():
            if not self.editing or entry["checked"]:
                data["items"][entry["item"]["id"]] = entry["offsets"]
        if not self.editing:
            data["selected"] = [key for key, entry in self.entries.items() if entry["checked"]]
        lib.write_json(user_dir() / "allowances.json", data)
        self.preferences = data

    def remember_only(self):
        try:
            for entry in self.entries.values():
                lib.calculate(entry["item"], entry["offsets"])
            self.save_preferences()
            self.footer.setText("Saved per-item allowances for next time. No project objects were changed.")
        except Exception as exc:
            error(exc, self)

    def edit_library(self):
        try:
            if execute(LibraryEditor(self)):
                self.read_library()
                self.populate()
        except Exception as exc:
            error(exc, self)

    def apply(self):
        try:
            checked = [entry for entry in self.entries.values() if entry["checked"]]
            if not checked:
                raise ValueError("Check at least one item on the left.")
            for entry in checked:
                lib.calculate(entry["item"], entry["offsets"])
            self.save_preferences()
            if self.editing:
                io.update_allowances(self.doc, [(entry["object"], entry["offsets"]) for entry in checked])
                result = [entry["object"] for entry in checked]
            else:
                if self.doc is None:
                    self.doc = App.newDocument("Fasteners")
                result = io.create_fasteners(self.doc, [(entry["item"], entry["offsets"]) for entry in checked])
            select_created(result)
            self.accept()
        except Exception as exc:
            error(exc, self)


class SnapshotChooser(QtWidgets.QDialog):
    def __init__(self, data):
        super().__init__(Gui.getMainWindow())
        self.setWindowTitle("Import VarSets from JSON")
        self.resize(750, 530)
        self.data = data
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Check the VarSets to import as independent copies. Existing objects are kept."))
        self.items = QtWidgets.QListWidget()
        for record in data["varsets"]:
            item = QtWidgets.QListWidgetItem(record["label"])
            item.setCheckState(QtCore.Qt.Checked)
            self.items.addItem(item)
        layout.addWidget(self.items)
        self.preview = QtWidgets.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.items.currentRowChanged.connect(self.preview_record)
        layout.addWidget(self.preview, 1)
        layout.addWidget(QtWidgets.QLabel("After import, use Adjust allowances on generated fastener VarSets, or edit their Data properties."))
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Import checked VarSets")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.items.setCurrentRow(0)

    def preview_record(self, index):
        if index >= 0:
            self.preview.setPlainText(json.dumps(self.data["varsets"][index], indent=2, ensure_ascii=False))

    def chosen(self):
        data = dict(self.data)
        data["varsets"] = [record for i, record in enumerate(self.data["varsets"])
                           if self.items.item(i).checkState() == QtCore.Qt.Checked]
        return data


def generate():
    try:
        execute(FastenerDialog())
    except Exception as exc:
        error(exc)


def adjust():
    try:
        objects = selected_varsets()
        if not objects:
            raise ValueError("Select one or more generated fastener VarSets in the project tree first.")
        if len({obj.Document.Name for obj in objects}) != 1:
            raise ValueError("Select VarSets from one project at a time.")
        for obj in objects:
            io.item_from_object(obj)
        execute(FastenerDialog(objects))
    except Exception as exc:
        error(exc)


def export_json():
    try:
        objects = selected_varsets()
        if not objects and App.ActiveDocument:
            objects = [obj for obj in App.ActiveDocument.Objects if obj.TypeId == "App::VarSet"]
        data = io.export_varsets(objects)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(Gui.getMainWindow(), "Export VarSets", "varsets.json", "JSON files (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        lib.write_json(path, data)
        note = f'Exported {len(objects)} VarSet(s) to {path}.'
        if data["flattened_expressions"]:
            note += "\nExternal expressions were saved as evaluated values:\n" + "\n".join(data["flattened_expressions"])
        QtWidgets.QMessageBox.information(Gui.getMainWindow(), "Fastener VarSets", note)
    except Exception as exc:
        error(exc)


def import_json():
    try:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(Gui.getMainWindow(), "Import VarSets", "", "JSON files (*.json)")
        if not path:
            return
        data = io.validate_snapshot(lib.read_json(path))
        chooser = SnapshotChooser(data)
        if not execute(chooser):
            return
        data = chooser.chosen()
        io.validate_snapshot(data)
        doc = App.ActiveDocument or App.newDocument("Fasteners")
        result = io.import_varsets(doc, data)
        select_created(result)
    except Exception as exc:
        error(exc)


def show_library():
    try:
        lib.load_library(user_dir())
        execute(LibraryEditor(Gui.getMainWindow()))
    except Exception as exc:
        error(exc)
