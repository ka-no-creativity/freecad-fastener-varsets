"""Run with system Python and the installed FreeCAD module (no desktop needed)."""

import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, "/usr/lib/freecad/lib")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import FreeCAD as App

from fastener_varsets import freecad_io as io
from fastener_varsets import library as lib


class FastenerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.library = lib.load_library(self.temp.name)
        self.doc = App.newDocument("Test")

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        self.temp.cleanup()

    def item(self, key):
        return next(item for item in self.library["items"] if item["id"] == key)

    def test_all_dimensions_match_freecad_expressions(self):
        requests = [(item, None) for item in self.library["items"]]
        objects = io.create_fasteners(self.doc, requests)
        self.assertEqual(len(objects), 15)
        for obj, (item, _) in zip(objects, requests):
            expected = lib.calculate(item)
            for name, value in expected.items():
                self.assertAlmostEqual(getattr(obj, name).Value, value, places=8, msg=f"{obj.Name}.{name}")
            self.assertNotIn("Invalid", obj.State)
        self.assertEqual(self.doc.M8_SocketCap.HeadHeight.Value, 8)
        self.assertEqual(self.doc.M5_Nut.NutHeight.Value, 4)
        self.assertEqual(self.doc.M8_Nut.NutHeight.Value, 6.5)

    def test_total_offsets_and_each_item_independent(self):
        m4 = self.item("DIN912_M4")
        m5 = self.item("DIN912_M5")
        a, b = io.create_fasteners(self.doc, [(m4, {"HoleAllowance": 1}), (m5, {"HoleAllowance": .3})])
        self.assertEqual(a.HoleDiameter.Value, 5)
        self.assertAlmostEqual(b.HoleDiameter.Value, 5.3)
        a.HoleAllowance = .75
        a.TapHoleAllowance = .1
        self.doc.recompute()
        self.assertEqual(a.HoleDiameter.Value, 4.75)
        self.assertAlmostEqual(a.TapHoleDiameter.Value, 3.4)
        self.assertAlmostEqual(b.HoleDiameter.Value, 5.3)

    def test_hex_fit_geometry_and_negative_allowance(self):
        obj, = io.create_fasteners(self.doc, [(self.item("DIN934_M4"), {"LooseFitAllowance": .4, "PressFitAllowance": -.2})])
        self.assertAlmostEqual(obj.LooseFitAcrossFlats.Value, 7.4)
        self.assertAlmostEqual(obj.PressFitAcrossFlats.Value, 6.8)
        self.assertAlmostEqual(obj.LooseFitDiameter.Value, 7.4 * 2 / math.sqrt(3))
        self.assertAlmostEqual(obj.PressFitDiameter.Value, 6.8 * 2 / math.sqrt(3))

    def test_snapshots_roundtrip_and_persist_without_addon(self):
        objects = io.create_fasteners(self.doc, [(item, None) for item in self.library["items"]])
        data = io.export_varsets(objects)
        path = Path(self.temp.name) / "varsets.json"
        lib.write_json(path, data)
        other = App.newDocument("Other")
        copied = io.import_varsets(other, lib.read_json(path))
        self.assertEqual(io.export_varsets(copied)["varsets"], data["varsets"])
        copied[1].HoleAllowance = 1
        other.recompute()
        self.assertEqual(copied[1].HoleDiameter.Value, 5)
        self.assertEqual(objects[1].HoleDiameter.Value, 4.5)
        cad_path = str(Path(self.temp.name) / "snapshot.FCStd")
        other.saveAs(cad_path)
        App.closeDocument(other.Name)
        restored = App.openDocument(cad_path)
        restored.M4_SocketCap.HoleAllowance = 1.25
        restored.recompute()
        self.assertEqual(restored.M4_SocketCap.HoleDiameter.Value, 5.25)
        self.assertFalse(hasattr(restored.M4_SocketCap, "Proxy"))

    def test_external_expressions_flattened(self):
        source = self.doc.addObject("App::VarSet", "Source")
        source.addProperty(io.LENGTH, "Size")
        source.Size = 11
        obj = self.doc.addObject("App::VarSet", "Custom")
        obj.addProperty(io.LENGTH, "Diameter")
        obj.setExpression("Diameter", "Source.Size + 1 mm")
        self.doc.recompute()
        data = io.export_varsets([obj])
        self.assertEqual(data["flattened_expressions"], ["Custom.Diameter"])
        self.assertNotIn("expression", data["varsets"][0]["properties"][0])
        other = App.newDocument("Other")
        result, = io.import_varsets(other, data)
        self.assertEqual(result.Diameter.Value, 12)

    def test_common_custom_property_types_roundtrip(self):
        obj = self.doc.addObject("App::VarSet", "Custom")
        props = {"Length": (io.LENGTH, 12.5), "Offset": (io.DISTANCE, -.2), "Angle": (io.ANGLE, 90),
                 "Count": ("App::PropertyInteger", 4), "Ratio": ("App::PropertyFloat", .5),
                 "Enabled": ("App::PropertyBool", True), "Notes": (io.STRING, "Mutter äöü"),
                 "Sizes": ("App::PropertyFloatList", [1, 2.5]), "Counts": ("App::PropertyIntegerList", [1, 3]),
                 "Names": ("App::PropertyStringList", ["one", "two"]),
                 "Vector": ("App::PropertyVector", App.Vector(1, 2, 3))}
        for name, (kind, value) in props.items():
            io.add(obj, name, value, "Custom", kind, "My tooltip")
        io.add(obj, "Choice", ["A", "B"], "Custom", "App::PropertyEnumeration")
        obj.Choice = "B"
        data = io.export_varsets([obj])
        other = App.newDocument("Other")
        result = io.import_varsets(other, data)
        self.assertEqual(io.export_varsets(result)["varsets"], data["varsets"])

    def test_name_collisions_preserve_old_objects(self):
        item = self.item("DIN912_M4")
        first, = io.create_fasteners(self.doc, [(item, {"HoleAllowance": .5})])
        second, = io.create_fasteners(self.doc, [(item, {"HoleAllowance": 1})])
        self.assertNotEqual(first.Name, second.Name)
        data = io.export_varsets([first])
        third, = io.import_varsets(self.doc, data)
        self.assertNotEqual(first.Name, third.Name)
        self.assertEqual(first.HoleDiameter.Value, 4.5)
        self.assertEqual(second.HoleDiameter.Value, 5)

    def test_adjust_keeps_references(self):
        obj, = io.create_fasteners(self.doc, [(self.item("DIN912_M4"), None)])
        other = self.doc.addObject("App::VarSet", "Dependent")
        other.addProperty(io.LENGTH, "Dimension")
        other.setExpression("Dimension", f"{obj.Name}.HoleDiameter")
        item, offsets = io.item_from_object(obj)
        offsets["HoleAllowance"] = 1
        io.update_allowances(self.doc, [(obj, offsets)])
        self.assertEqual(other.Dimension.Value, 5)
        self.assertEqual(item["dimensions"]["HeadDiameter"], 7)

    def test_bad_input_has_no_partial_import(self):
        original, = io.create_fasteners(self.doc, [(self.item("DIN912_M4"), None)])
        data = io.export_varsets([original])
        bad = copy.deepcopy(data)
        bad["varsets"].append(copy.deepcopy(bad["varsets"][0]))
        bad["varsets"][1]["properties"][0]["type"] = "App::PropertyLink"
        count = len(self.doc.Objects)
        with self.assertRaises(ValueError):
            io.import_varsets(self.doc, bad)
        self.assertEqual(len(self.doc.Objects), count)
        bad = copy.deepcopy(data)
        for prop in bad["varsets"][0]["properties"]:
            if prop["name"] == "HoleDiameter":
                prop["expression"] = "NominalDiameter / 0"
        with self.assertRaises(Exception):
            io.import_varsets(self.doc, bad)
        self.assertEqual(len(self.doc.Objects), count)

    def test_invalid_allowances_rejected(self):
        for values in ({"HoleAllowance": -5}, {"TapHoleAllowance": 1}, {"HoleAllowance": float("nan")}):
            with self.assertRaises(ValueError):
                io.create_fasteners(self.doc, [(self.item("DIN912_M4"), values)])
        with self.assertRaises(ValueError):
            lib.calculate(self.item("DIN934_M4"), {"LooseFitAllowance": -.5, "PressFitAllowance": 0})
        self.assertEqual(len(self.doc.Objects), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
