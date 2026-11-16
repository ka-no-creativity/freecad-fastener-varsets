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
        self.assertEqual(len(objects), 20)
        for obj, (item, _) in zip(objects, requests):
            expected = lib.calculate(item)
            for name, value in expected.items():
                self.assertAlmostEqual(getattr(obj, io.property_name(name)).Value, value, places=8, msg=f"{obj.Name}.{name}")
            self.assertNotIn("Invalid", obj.State)
        self.assertEqual(getattr(self.doc.M8_Cap, "__HeadHeight").Value, 8)
        self.assertEqual(getattr(self.doc.M5_Nut, "__NutHeight").Value, 4)
        self.assertEqual(getattr(self.doc.M8_Nut, "__NutHeight").Value, 6.5)

    def test_total_offsets_and_each_item_independent(self):
        m4 = self.item("DIN912_M4")
        m5 = self.item("DIN912_M5")
        a, b = io.create_fasteners(self.doc, [(m4, {"HoleAllowance": 1}), (m5, {"HoleAllowance": .3})])
        self.assertEqual(a.HoleDia.Value, 5)
        self.assertAlmostEqual(b.HoleDia.Value, 5.3)
        setattr(a, "__HoleAllowance", .75)
        setattr(a, "__TapHoleAllowance", .1)
        self.doc.recompute()
        self.assertEqual(a.HoleDia.Value, 4.75)
        self.assertAlmostEqual(a.TapDia.Value, 3.4)
        self.assertAlmostEqual(b.HoleDia.Value, 5.3)

    def test_hex_fit_geometry_and_negative_allowance(self):
        obj, = io.create_fasteners(self.doc, [(self.item("DIN934_M4"), {"LooseFitAllowance": .4, "PressFitAllowance": -.2})])
        self.assertAlmostEqual(obj.LooseAF.Value, 7.4)
        self.assertAlmostEqual(obj.PressAF.Value, 6.8)
        self.assertAlmostEqual(obj.LooseDia.Value, 7.4 * 2 / math.sqrt(3))
        self.assertAlmostEqual(obj.PressDia.Value, 6.8 * 2 / math.sqrt(3))

    def test_snapshots_roundtrip_and_persist_without_addon(self):
        objects = io.create_fasteners(self.doc, [(item, None) for item in self.library["items"]])
        data = io.export_varsets(objects)
        path = Path(self.temp.name) / "varsets.json"
        lib.write_json(path, data)
        other = App.newDocument("Other")
        copied = io.import_varsets(other, lib.read_json(path))
        self.assertEqual(io.export_varsets(copied)["varsets"], data["varsets"])
        setattr(copied[1], "__HoleAllowance", 1)
        other.recompute()
        self.assertEqual(copied[1].HoleDia.Value, 5)
        self.assertEqual(objects[1].HoleDia.Value, 4.5)
        cad_path = str(Path(self.temp.name) / "snapshot.FCStd")
        other.saveAs(cad_path)
        App.closeDocument(other.Name)
        restored = App.openDocument(cad_path)
        setattr(restored.M4_Cap, "__HoleAllowance", 1.25)
        restored.recompute()
        self.assertEqual(restored.M4_Cap.HoleDia.Value, 5.25)
        self.assertFalse(hasattr(restored.M4_Cap, "Proxy"))

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
        self.assertEqual(first.HoleDia.Value, 4.5)
        self.assertEqual(second.HoleDia.Value, 5)

    def test_adjust_keeps_references(self):
        obj, = io.create_fasteners(self.doc, [(self.item("DIN912_M4"), None)])
        other = self.doc.addObject("App::VarSet", "Dependent")
        other.addProperty(io.LENGTH, "Dimension")
        other.setExpression("Dimension", f"{obj.Name}.HoleDia")
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
            if prop["name"] == "HoleDia":
                prop["expression"] = "__NominalDiameter / 0"
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

    def test_all_naming_combinations_roundtrip_and_reopen(self):
        for short_objects in (True, False):
            for short_dimensions in (True, False):
                with self.subTest(objects=short_objects, dimensions=short_dimensions):
                    source = App.newDocument("Naming")
                    objects = io.create_fasteners(source, [(item, None) for item in self.library["items"]],
                                                  short_object_names=short_objects,
                                                  short_dimension_names=short_dimensions)
                    for obj, item in zip(objects, self.library["items"]):
                        self.assertEqual(obj.Name, io.object_name(item, short_objects))
                        for key, value in lib.calculate(item).items():
                            name = io.property_name(key, short_dimensions)
                            self.assertAlmostEqual(getattr(obj, name).Value, value, places=8)
                            self.assertTrue(obj.getDocumentationOfProperty(name))
                        public = {key for key in obj.PropertiesList if key not in io.BASE and not key.startswith("__")}
                        self.assertEqual(public, {io.property_name(key, short_dimensions)
                                                 for key in io.expressions(item["kind"]) if key != "NutAcrossCorners"})
                        for key, _, _ in lib.fields(item["kind"]):
                            self.assertEqual(obj.getTypeIdOfProperty("__" + key), io.DISTANCE)
                    data = io.export_varsets(objects)
                    self.assertFalse(data["flattened_expressions"])
                    other = App.newDocument("NamingCopy")
                    copied = io.import_varsets(other, data)
                    self.assertEqual(io.export_varsets(copied)["varsets"], data["varsets"])
                    # Import keeps the exported layout; adjustment changes values only.
                    for obj in copied:
                        io.update_allowances(other, [(obj, {"HoleAllowance": -.2})])
                    saved = io.export_varsets(copied)
                    path = str(Path(self.temp.name) / f"naming-{short_objects}-{short_dimensions}.FCStd")
                    other.saveAs(path)
                    App.closeDocument(other.Name)
                    restored = App.openDocument(path)
                    self.assertEqual(io.export_varsets(restored.Objects)["varsets"], saved["varsets"])
                    for obj in restored.Objects:
                        self.assertFalse(hasattr(obj, "Proxy"))
                        self.assertEqual(getattr(obj, "__HoleAllowance").Value, -.2)
                    App.closeDocument(restored.Name)
                    App.closeDocument(source.Name)

    def test_exact_short_and_full_names(self):
        expected = {"socket_cap": ("M3_Cap", "M3_SocketCap"),
                    "countersunk": ("M3_Csk", "M3_Countersunk"),
                    "hex_nut": ("M3_Nut", "M3_Nut"),
                    "heat_insert": ("M3_Heat", "M3_HeatInsert")}
        for kind, names in expected.items():
            for short, name in zip((True, False), names):
                self.assertEqual(io.object_name({"size": "M3", "kind": kind}, short), name)
        self.assertEqual(io.SHORT_DIMENSIONS, {
            "HoleDiameter": "HoleDia", "HeadPocketDiameter": "HeadDia", "HeadPocketDepth": "HeadDepth",
            "TapHoleDiameter": "TapDia", "LooseFitAcrossFlats": "LooseAF", "PressFitAcrossFlats": "PressAF",
            "LooseFitDiameter": "LooseDia", "PressFitDiameter": "PressDia", "NutPocketDepth": "NutDepth",
            "InsertHoleDiameter": "InsertDia", "InsertPocketDepth": "InsertDepth"})

    def test_every_allowance_accepts_negative_zero_and_positive_values(self):
        objects = []
        for item in self.library["items"]:
            for key, _, _ in lib.fields(item["kind"]):
                for value in (-.05, 0, .05):
                    with self.subTest(item=item["id"], allowance=key, value=value):
                        values = {key: value}
                        # Loose width still needs to be at least press width.
                        if key == "LooseFitAllowance":
                            values["PressFitAllowance"] = -.1
                        obj, = io.create_fasteners(self.doc, [(item, values)])
                        self.assertAlmostEqual(getattr(obj, "__" + key).Value, value)
                        for name, expected in lib.calculate(item, values).items():
                            self.assertAlmostEqual(getattr(obj, io.property_name(name)).Value, expected, places=8)
                        objects.append(obj)
        data = io.export_varsets(objects)
        other = App.newDocument("Signed")
        imported = io.import_varsets(other, data)
        self.assertEqual(io.export_varsets(imported)["varsets"], data["varsets"])
        path = str(Path(self.temp.name) / "signed.FCStd")
        other.saveAs(path)
        App.closeDocument(other.Name)
        restored = App.openDocument(path)
        self.assertEqual(io.export_varsets(restored.Objects)["varsets"], data["varsets"])

    def test_insert_published_dimensions_and_independent_allowances(self):
        # CNC Kitchen Dimensions & Design Guidelines, page 2: metric L, D1, D2, W.
        published = {3: (5.7, 4.6, 4.0, 1.6), 4: (8.1, 6.3, 5.7, 2.1),
                     5: (9.5, 7.1, 6.5, 2.6), 6: (12.7, 8.7, 8.1, 3.3),
                     8: (12.7, 10.2, 9.7, 4.5)}
        for size, (length, outside, hole, wall) in published.items():
            item = self.item(f"CNCKITCHEN_M{size}")
            d = item["dimensions"]
            self.assertEqual([d[key] for key in ("InsertLength", "InsertOutsideDiameter",
                                                 "RecommendedHoleDiameter", "MinimumWallThickness")],
                             [length, outside, hole, wall])
            self.assertEqual(d["RecommendedHoleDepth"], length + 1)
            self.assertEqual(lib.allowances(item)["InsertDiameterAllowance"], 0)
            self.assertEqual(lib.allowances(item)["InsertDepthAllowance"], 0)
            obj, = io.create_fasteners(self.doc, [(item, {"InsertDiameterAllowance": -.2,
                                                        "InsertDepthAllowance": -1, "HoleAllowance": -.1})])
            self.assertAlmostEqual(obj.InsertDia.Value, hole - .2)
            self.assertAlmostEqual(obj.InsertDepth.Value, length)
            self.assertAlmostEqual(obj.HoleDia.Value, size - .1)
            self.assertEqual(getattr(obj, "__Manufacturer"), "CNC Kitchen")
            self.assertEqual(getattr(obj, "__Model"), item["model"])
            restored_item, offsets = io.item_from_object(obj)
            self.assertEqual(restored_item["dimensions"], item["dimensions"])
            self.assertEqual(restored_item["manufacturer"], item["manufacturer"])
            self.assertEqual(offsets["InsertDepthAllowance"], -1)

    def test_invalid_resulting_geometry_is_atomic(self):
        cases = {"DIN912_M4": [{"HoleAllowance": -4}, {"HeadDiameterAllowance": -4},
                                {"HeadDepthAllowance": -4}, {"TapHoleAllowance": -3.3},
                                {"TapHoleAllowance": .7}],
                 "DIN7991_M4": [{"HeadDepthAllowance": -3}, {"HeadDiameterAllowance": -4}],
                 "DIN934_M4": [{"NutDepthAllowance": -3.2}, {"PressFitAllowance": -7},
                                {"LooseFitAllowance": -.5, "PressFitAllowance": 0}],
                 "CNCKITCHEN_M4": [{"InsertDiameterAllowance": -1.7}, {"InsertDiameterAllowance": .6},
                                     {"InsertDepthAllowance": -1.01}, {"HoleAllowance": -4}]}
        for key, invalid_values in cases.items():
            obj, = io.create_fasteners(self.doc, [(self.item(key), None)])
            before = io.export_varsets([obj])
            count = len(self.doc.Objects)
            for values in invalid_values:
                with self.subTest(item=key, values=values):
                    with self.assertRaises(ValueError):
                        io.create_fasteners(self.doc, [(self.item(key), None), (self.item(key), values)])
                    self.assertEqual(len(self.doc.Objects), count)
                    with self.assertRaises(ValueError):
                        io.update_allowances(self.doc, [(obj, values)])
                    self.assertEqual(io.export_varsets([obj]), before)

    def test_legacy_snapshot_adjustment_preserves_names_and_references(self):
        data = lib.read_json(Path(__file__).with_name("fixtures") / "legacy-varsets.json")
        objects = io.import_varsets(self.doc, data)
        self.assertEqual(io.export_varsets(objects)["varsets"], data["varsets"])
        dependent = self.doc.addObject("App::VarSet", "Dependent")
        for index, obj in enumerate(objects):
            dependent.addProperty(io.LENGTH, f"Hole{index}")
            dependent.setExpression(f"Hole{index}", f"{obj.Name}.HoleDiameter")
            names, expressions = list(obj.PropertiesList), list(obj.ExpressionEngine)
            item, values = io.item_from_object(obj)
            values["HoleAllowance"] = -.1
            io.update_allowances(self.doc, [(obj, values)])
            self.assertAlmostEqual(getattr(dependent, f"Hole{index}").Value, 3.9)
            self.assertEqual(obj.PropertiesList, names)
            self.assertEqual(obj.ExpressionEngine, expressions)
            self.assertEqual(item["dimensions"]["NominalDiameter"], 4)
            self.assertNotIn("__FastenerKind", obj.PropertiesList)
        saved = io.export_varsets(objects)
        other = App.newDocument("LegacyCopy")
        copied = io.import_varsets(other, saved)
        self.assertEqual(io.export_varsets(copied)["varsets"], saved["varsets"])

    def test_undo_creation_adjustment_and_import(self):
        self.doc.UndoMode = 1
        obj, = io.create_fasteners(self.doc, [(self.item("CNCKITCHEN_M4"), None)])
        name = obj.Name
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(name))
        self.doc.redo()
        obj = self.doc.getObject(name)
        io.update_allowances(self.doc, [(obj, {"InsertDepthAllowance": -.5})])
        self.assertAlmostEqual(obj.InsertDepth.Value, 8.6)
        self.doc.undo()
        self.assertAlmostEqual(obj.InsertDepth.Value, 9.1)
        self.doc.redo()
        self.assertAlmostEqual(obj.InsertDepth.Value, 8.6)
        imported, = io.import_varsets(self.doc, io.export_varsets([obj]))
        self.assertNotEqual(imported.Name, name)
        self.doc.undo()
        self.assertEqual([o.Name for o in self.doc.Objects], [name])

    def test_partial_adjustment_validates_saved_allowances(self):
        item = self.item("DIN934_M4")
        obj, = io.create_fasteners(self.doc, [(item, {"PressFitAllowance": -.8})])
        io.update_allowances(self.doc, [(obj, {"LooseFitAllowance": -.7})])
        self.assertAlmostEqual(obj.LooseAF.Value, 6.3)
        self.assertAlmostEqual(obj.PressAF.Value, 6.2)
        with self.assertRaises(ValueError):
            io.update_allowances(self.doc, [(obj, {"PressFitAllowance": -.6})])
        with self.assertRaises(ValueError):
            io.update_allowances(self.doc, [(obj, {"Unknown": 0})])

    def test_library_upgrade_preserves_custom_values_and_deletions(self):
        path = Path(self.temp.name) / "library.json"
        old = copy.deepcopy(self.library)
        old.pop("upgrades")
        old["items"] = [item for item in old["items"] if item["kind"] != "heat_insert"]
        old["sources"] = [source for source in old["sources"] if source["standard"] != "CNC Kitchen"]
        old["items"][0]["dimensions"]["HeadDiameter"] = 5.6
        custom = copy.deepcopy(self.item("CNCKITCHEN_M4"))
        custom["dimensions"]["RecommendedHoleDiameter"] = 5.6
        old["items"].append(custom)
        lib.write_json(path, old)
        upgraded = lib.load_library(self.temp.name)
        self.assertEqual(len(upgraded["items"]), 20)
        self.assertEqual(upgraded["items"][0], old["items"][0])
        self.assertIn(custom, upgraded["items"])
        self.assertIn(lib.INSERT_UPGRADE, upgraded["upgrades"])
        self.assertEqual(sum(s["standard"] == "CNC Kitchen" for s in upgraded["sources"]), 1)
        upgraded["items"] = [item for item in upgraded["items"] if item["id"] != "CNCKITCHEN_M3"]
        lib.write_json(path, upgraded)
        before = path.read_bytes()
        self.assertEqual(lib.load_library(self.temp.name), upgraded)
        self.assertEqual(path.read_bytes(), before)

    def test_preferences_upgrade_defaults_and_signed_values(self):
        defaults = lib.load_preferences(self.temp.name)
        self.assertTrue(defaults["short_object_names"])
        self.assertTrue(defaults["short_dimension_names"])
        data = {"version": 1, "items": {"CNCKITCHEN_M4": {"InsertDepthAllowance": -.5}},
                "selected": ["CNCKITCHEN_M4"]}
        path = Path(self.temp.name) / "allowances.json"
        lib.write_json(path, data)
        loaded = lib.load_preferences(self.temp.name)
        self.assertEqual(loaded["items"], data["items"])
        self.assertTrue(loaded["short_object_names"])
        loaded.update(short_object_names=False, short_dimension_names=False)
        lib.write_json(path, loaded)
        self.assertEqual(lib.load_preferences(self.temp.name), loaded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
