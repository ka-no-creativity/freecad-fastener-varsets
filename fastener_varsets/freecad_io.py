"""Native VarSets with local expressions; portable, typed JSON snapshots."""

import re
from contextlib import contextmanager

from .library import KINDS, allowances, calculate, dimension_fields, fields, number

LENGTH = "App::PropertyLength"
DISTANCE = "App::PropertyDistance"
STRING = "App::PropertyString"
ANGLE = "App::PropertyAngle"
SCALARS = {LENGTH, DISTANCE, ANGLE, "App::PropertyFloat", "App::PropertyInteger",
           "App::PropertyBool", STRING, "App::PropertyEnumeration"}
LISTS = {"App::PropertyFloatList", "App::PropertyIntegerList", "App::PropertyStringList",
         "App::PropertyBoolList"}
TYPES = SCALARS | LISTS | {"App::PropertyVector"}
BASE = {"ExpressionEngine", "Label", "Label2", "Visibility"}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHORT_DIMENSIONS = {
    "HoleDiameter": "HoleDia", "HeadPocketDiameter": "HeadDia",
    "HeadPocketDepth": "HeadDepth", "TapHoleDiameter": "TapDia",
    "LooseFitAcrossFlats": "LooseAF", "PressFitAcrossFlats": "PressAF",
    "LooseFitDiameter": "LooseDia", "PressFitDiameter": "PressDia",
    "NutPocketDepth": "NutDepth", "InsertHoleDiameter": "InsertDia",
    "InsertPocketDepth": "InsertDepth",
}
DOCS = {
    "LibraryId": "Canonical entry ID in the source library; this project holds an independent snapshot.",
    "FastenerKind": "Fastener family used to interpret this project's saved dimensions and allowances.",
    "Standard": "Dimension standard or manufacturer source for this fastener.",
    "ThreadSize": "Metric thread designation.",
    "Manufacturer": "Manufacturer of this insert.",
    "Model": "Manufacturer's insert type and nominal length in millimetres.",
    "NominalDiameter": "Nominal metal thread diameter, without print allowance.",
    "Pitch": "Metric coarse thread pitch.",
    "HeadDiameter": "Nominal metal screw head diameter, without print allowance.",
    "HeadHeight": "Catalog head height. For countersinks this is not the full cone depth to the through-hole intersection.",
    "SocketAcrossFlats": "Nominal hex-key socket width across opposite flats.",
    "CountersinkAngle": "Included cone angle of the countersunk head, in degrees.",
    "HeadPocketDiameter": "Head recess diameter: nominal head diameter plus total diameter allowance.",
    "HeadPocketDepth": "Head recess depth: nominal head height plus total depth allowance.",
    "NutAcrossFlats": "Nominal metal nut width across opposite flats, without print allowance.",
    "NutHeight": "Nominal metal nut height, without print allowance.",
    "NutPocketDepth": "Nut pocket depth: nominal nut height plus total depth allowance.",
    "TapDrillDiameter": "Base tap-drill diameter (Kernloch) for a cutting tap. Not a forming-tap hole or the theoretical minor diameter.",
    "TapHoleDiameter": "Hole to model before cutting the thread: tap drill plus this item's tap allowance.",
    "HoleDiameter": "Through-hole diameter: nominal diameter plus total hole allowance.",
    "LooseFitDiameter": "Loose pocket diameter across CORNERS. Use half for a hexagon's circumradius or use as a round pocket diameter.",
    "PressFitDiameter": "Press pocket diameter across CORNERS. Use half for a hexagon's circumradius or use as a round pocket diameter.",
    "LooseFitAcrossFlats": "Loose hex pocket width across opposite FLATS.",
    "PressFitAcrossFlats": "Press hex pocket width across opposite FLATS.",
    "NutAcrossCorners": "Ideal regular hexagon across corners, computed from nominal across flats; not catalog e minimum.",
    "InsertLength": "Nominal metal insert length in millimetres (CNC Kitchen L).",
    "InsertOutsideDiameter": "Nominal metal insert outside diameter (CNC Kitchen D1).",
    "RecommendedHoleDiameter": "Manufacturer's recommended installation-hole diameter (CNC Kitchen D2), before print allowance.",
    "RecommendedHoleDepth": "Base blind-hole depth: insert length plus 1 mm for displaced plastic.",
    "MinimumWallThickness": "Manufacturer's minimum surrounding wall thickness (CNC Kitchen W).",
    "InsertHoleDiameter": "Installation-hole diameter: recommended hole diameter plus total insert diameter allowance. Must stay between thread and insert outside diameters.",
    "InsertPocketDepth": "Insert pocket depth: recommended blind-hole depth plus total insert depth allowance. Must be at least the insert length.",
}


def object_name(item, short_object_names=True):
    suffix = ({"socket_cap": "Cap", "countersunk": "Csk", "hex_nut": "Nut", "heat_insert": "Heat"}
              if short_object_names else
              {"socket_cap": "SocketCap", "countersunk": "Countersunk", "hex_nut": "Nut", "heat_insert": "HeatInsert"})
    return f'{item["size"]}_{suffix[item["kind"]]}'


def property_name(canonical, short_dimension_names=True):
    """Only cutout dimensions are public. All base/source/allowance names are internal."""
    if canonical in SHORT_DIMENSIONS:
        return SHORT_DIMENSIONS[canonical] if short_dimension_names else canonical
    return "__" + canonical


def existing_property(obj, canonical):
    """Resolve saved names without renaming legacy objects or their properties."""
    for name in ("__" + canonical, canonical, SHORT_DIMENSIONS.get(canonical)):
        if name and name in obj.PropertiesList:
            return name
    raise ValueError(f"{obj.Label}: missing fastener property {canonical}.")


@contextmanager
def transaction(doc, label):
    previous = doc.UndoMode
    if not previous:
        doc.UndoMode = 1  # abortTransaction also needs undo recording in headless documents.
    doc.openTransaction(label)
    try:
        yield
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    finally:
        if not previous:
            doc.UndoMode = previous


def expressions(kind):
    result = {"HoleDiameter": "NominalDiameter + HoleAllowance"}
    if kind == "hex_nut":
        result.update({
            "NutAcrossCorners": "NutAcrossFlats * 2 / sqrt(3)",
            "LooseFitAcrossFlats": "NutAcrossFlats + LooseFitAllowance",
            "PressFitAcrossFlats": "NutAcrossFlats + PressFitAllowance",
            "LooseFitDiameter": "LooseFitAcrossFlats * 2 / sqrt(3)",
            "PressFitDiameter": "PressFitAcrossFlats * 2 / sqrt(3)",
            "NutPocketDepth": "NutHeight + NutDepthAllowance",
        })
    elif kind == "heat_insert":
        result.update({
            "InsertHoleDiameter": "RecommendedHoleDiameter + InsertDiameterAllowance",
            "InsertPocketDepth": "RecommendedHoleDepth + InsertDepthAllowance",
        })
    else:
        result["TapHoleDiameter"] = "TapDrillDiameter + TapHoleAllowance"
        result["HeadPocketDiameter"] = "HeadDiameter + HeadDiameterAllowance"
        result["HeadPocketDepth"] = "HeadHeight + HeadDepthAllowance"
        if kind == "countersunk":
            result["HeadPocketDiameter"] += " + 2 * HeadDepthAllowance * tan(CountersinkAngle / 2)"
            result["HeadPocketDepth"] = "(HeadPocketDiameter - HoleDiameter) / (2 * tan(CountersinkAngle / 2))"
    return result


def mapped_expressions(kind, short_dimension_names=True):
    canonical = expressions(kind)
    names = dimension_fields(kind) + [key for key, _, _ in fields(kind)] + list(canonical)
    mapping = {key: property_name(key, short_dimension_names) for key in names}
    return {mapping[key]: re.sub(r"[A-Za-z_][A-Za-z0-9_]*",
                                lambda match: mapping.get(match[0], match[0]), expression)
            for key, expression in canonical.items()}


def add(obj, name, value, group, type_id=LENGTH, description=""):
    obj.addProperty(type_id, name, group, description or DOCS.get(name, name))
    setattr(obj, name, value)


def create_fasteners(doc, requests, *, short_object_names=True, short_dimension_names=True):
    """Always create new objects; collisions never overwrite existing references."""
    prepared = [(item, allowances(item, a), calculate(item, a)) for item, a in requests]
    if not prepared:
        raise ValueError("Select at least one fastener to create.")
    result = []
    with transaction(doc, "Create fastener VarSets"):
        for item, a, calculated in prepared:
            name = object_name(item, short_object_names)
            obj = doc.addObject("App::VarSet", name)
            obj.Label = name
            source = {"LibraryId": item["id"], "FastenerKind": item["kind"],
                      "Standard": item["standard"], "ThreadSize": item["size"]}
            for key in ("manufacturer", "model"):
                if key in item:
                    source[key.title()] = item[key]
            for key, value in source.items():
                add(obj, property_name(key), value, "Source", STRING, DOCS[key])
            for key, value in item["dimensions"].items():
                add(obj, property_name(key), value, "Dimensions", ANGLE if key == "CountersinkAngle" else LENGTH,
                    DOCS.get(key, key))
            for key, label, _ in fields(item["kind"]):
                add(obj, property_name(key), a[key], "Allowances", DISTANCE,
                    f"{label}: total mm added to this dimension, not per side. Negative values reduce it.")
            for key in expressions(item["kind"]):
                description = DOCS.get(key, key)
                if item["kind"] == "countersunk" and key.startswith("HeadPocket"):
                    description = "90-degree (or selected angle) countersink geometry. Depth allowance expands the mouth while preserving the cone angle."
                add(obj, property_name(key, short_dimension_names), calculated[key],
                    "Dimensions" if key == "NutAcrossCorners" else "Cutouts", description=description)
            for key, expression in mapped_expressions(item["kind"], short_dimension_names).items():
                obj.setExpression(key, expression)
            result.append(obj)
        doc.recompute()
        check_objects(result)
    return result


def check_objects(objects):
    for obj in objects:
        if not obj.isValid():
            raise ValueError(f"{obj.Label}: FreeCAD reported an invalid expression or value: {obj.State}")
        for name in obj.PropertiesList:
            kind = obj.getTypeIdOfProperty(name)
            value = getattr(obj, name)
            if kind in (LENGTH, DISTANCE, ANGLE):
                number(value.Value, f"{obj.Label}.{name}")
            elif kind == "App::PropertyFloat":
                number(value, f"{obj.Label}.{name}")


def item_from_object(obj):
    if obj.TypeId != "App::VarSet":
        raise ValueError("Select a VarSet created by Fastener VarSets.")
    kind = getattr(obj, existing_property(obj, "FastenerKind"))
    if kind not in KINDS:
        raise ValueError(f"Unsupported fastener kind: {kind}")
    item = {"label": obj.Label, "kind": kind,
            "dimensions": {key: getattr(obj, existing_property(obj, key)).Value
                           for key in dimension_fields(kind)}}
    for attr, key in (("id", "LibraryId"), ("standard", "Standard"), ("size", "ThreadSize")):
        item[attr] = getattr(obj, existing_property(obj, key))
    for key in ("Manufacturer", "Model"):
        if "__" + key in obj.PropertiesList or key in obj.PropertiesList:
            item[key.lower()] = getattr(obj, existing_property(obj, key))
    a = {key: getattr(obj, existing_property(obj, key)).Value for key, _, _ in fields(kind)}
    return item, a


def update_allowances(doc, requests):
    prepared = []
    for obj, values in requests:
        item, current = item_from_object(obj)
        if set(values) - set(current):
            raise ValueError(f"Unknown allowance: {', '.join(sorted(set(values) - set(current)))}")
        current.update(values)
        calculate(item, current)
        prepared.append((obj, allowances(item, current)))
    with transaction(doc, "Adjust fastener allowances"):
        for obj, values in prepared:
            for key, value in values.items():
                saved_name = existing_property(obj, key)
                obj.setExpression(saved_name, None)
                setattr(obj, saved_name, value)
        doc.recompute()
        check_objects([obj for obj, _ in prepared])


def local_expression(expression, names):
    # Keep a conservative subset of local expressions. External document/object
    # references become evaluated values, keeping imports independent.
    if any(token in expression for token in ("#", ".", "<<", ">>", '"', "'")):
        # Decimal points are harmless; object.property references are not.
        if any(token in expression for token in ("#", "<<", ">>", '"', "'")) or re.search(r"[A-Za-z_]\w*\s*\.", expression):
            return False
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression))
    return identifiers <= set(names) | {"sqrt", "tan", "sin", "cos", "abs", "min", "max", "pi", "mm", "deg"}


def export_varsets(objects):
    if not objects:
        raise ValueError("No VarSets to export.")
    records = []
    flattened = []
    for obj in objects:
        if obj.TypeId != "App::VarSet":
            raise ValueError(f"{obj.Label} is not a VarSet.")
        names = [n for n in obj.PropertiesList if n not in BASE]
        exprs = dict(obj.ExpressionEngine)
        props = []
        for name in names:
            type_id = obj.getTypeIdOfProperty(name)
            if type_id not in TYPES:
                raise ValueError(f"{obj.Label}.{name}: export does not yet support {type_id}. Nothing was exported.")
            value = getattr(obj, name)
            if type_id in (LENGTH, DISTANCE, ANGLE):
                value = value.Value
            elif type_id in LISTS:
                value = list(value)
            elif type_id == "App::PropertyVector":
                value = [value.x, value.y, value.z]
            prop = {"name": name, "type": type_id, "group": obj.getGroupOfProperty(name),
                    "description": obj.getDocumentationOfProperty(name), "value": value}
            if type_id in (LENGTH, DISTANCE):
                prop["unit"] = "mm"
            elif type_id == ANGLE:
                prop["unit"] = "deg"
            if type_id == "App::PropertyEnumeration":
                prop["choices"] = obj.getEnumerationsOfProperty(name)
            if name in exprs:
                if local_expression(exprs[name], names):
                    prop["expression"] = exprs[name]
                else:
                    prop["source_expression"] = exprs[name]
                    flattened.append(f"{obj.Label}.{name}")
            props.append(prop)
        records.append({"name": obj.Name, "label": obj.Label, "properties": props})
    return {"format": "freecad-varsets", "version": 1,
            "notes": "Snapshot values use mm and degrees. Local expressions are retained; external expressions are flattened.",
            "varsets": records, "flattened_expressions": flattened}


def validate_snapshot(data):
    if not isinstance(data, dict) or data.get("format") != "freecad-varsets" or data.get("version") != 1:
        raise ValueError("Expected a FreeCAD VarSets JSON snapshot, version 1.")
    if not isinstance(data.get("varsets"), list) or not data["varsets"]:
        raise ValueError("Snapshot needs a non-empty varsets list.")
    for record in data["varsets"]:
        if not isinstance(record, dict) or not isinstance(record.get("name"), str) or not IDENTIFIER.fullmatch(record["name"]):
            raise ValueError("Each VarSet needs a valid object name.")
        if not isinstance(record.get("label"), str) or not isinstance(record.get("properties"), list):
            raise ValueError("Each VarSet needs a label and properties list.")
        names = set()
        for prop in record["properties"]:
            if not isinstance(prop, dict):
                raise ValueError("Each property must be an object.")
            name, kind = prop.get("name"), prop.get("type")
            if not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or name in BASE or name in names:
                raise ValueError(f"Invalid or duplicate property name: {name}")
            if kind not in TYPES:
                raise ValueError(f"Unsupported property type: {kind}")
            names.add(name)
            for attr in ("group", "description"):
                if not isinstance(prop.get(attr, ""), str):
                    raise ValueError(f"{name}: {attr} must be text.")
            value = prop.get("value")
            if kind in (LENGTH, DISTANCE, ANGLE, "App::PropertyFloat"):
                number(value, name)
                if kind == LENGTH and value < 0:
                    raise ValueError(f"{name}: length cannot be negative.")
                if kind in (LENGTH, DISTANCE, ANGLE) and prop.get("unit") != ("deg" if kind == ANGLE else "mm"):
                    raise ValueError(f"{name}: expected {'deg' if kind == ANGLE else 'mm'} units.")
            elif kind == "App::PropertyInteger":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"{name}: expected integer.")
            elif kind == "App::PropertyBool":
                if not isinstance(value, bool):
                    raise ValueError(f"{name}: expected boolean.")
            elif kind in (STRING, "App::PropertyEnumeration"):
                if not isinstance(value, str):
                    raise ValueError(f"{name}: expected text.")
                if kind == "App::PropertyEnumeration":
                    choices = prop.get("choices")
                    if not isinstance(choices, list) or not choices or not all(isinstance(c, str) for c in choices) or value not in choices:
                        raise ValueError(f"{name}: invalid enumeration choices.")
            else:
                if not isinstance(value, list):
                    raise ValueError(f"{name}: expected a list.")
                if kind == "App::PropertyVector" and len(value) != 3:
                    raise ValueError(f"{name}: vector requires three coordinates.")
                for v in value:
                    if kind == "App::PropertyStringList":
                        valid = isinstance(v, str)
                    elif kind == "App::PropertyBoolList":
                        valid = isinstance(v, bool)
                    elif kind == "App::PropertyIntegerList":
                        valid = isinstance(v, int) and not isinstance(v, bool)
                    else:
                        number(v, name)
                        valid = True
                    if not valid:
                        raise ValueError(f"{name}: invalid list element.")
        for prop in record["properties"]:
            if "expression" in prop and (not isinstance(prop["expression"], str) or not local_expression(prop["expression"], names)):
                raise ValueError(f'{prop["name"]}: only local expressions are supported in independent snapshots.')
    return data


def import_varsets(doc, data):
    validate_snapshot(data)
    result = []
    with transaction(doc, "Import VarSets JSON"):
        for record in data["varsets"]:
            obj = doc.addObject("App::VarSet", record["name"])
            obj.Label = record["label"]
            for prop in record["properties"]:
                value = prop["value"]
                if prop["type"] == "App::PropertyVector":
                    import FreeCAD
                    value = FreeCAD.Vector(*value)
                add(obj, prop["name"], prop.get("choices", value), prop.get("group", ""),
                    prop["type"], prop.get("description", ""))
                if prop["type"] == "App::PropertyEnumeration":
                    setattr(obj, prop["name"], value)
            for prop in record["properties"]:
                if "expression" in prop:
                    obj.setExpression(prop["name"], prop["expression"])
            result.append(obj)
        doc.recompute()
        check_objects(result)
    return result
