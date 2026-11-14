"""Native VarSets with local expressions; portable, typed JSON snapshots."""

import re
from contextlib import contextmanager

from .library import allowances, calculate, fields, number

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
DOCS = {
    "NominalDiameter": "Nominal metal thread diameter, without print allowance.",
    "Pitch": "Metric coarse thread pitch.",
    "TapDrillDiameter": "Base tap-drill diameter (Kernloch) for a cutting tap. Not a forming-tap hole or the theoretical minor diameter.",
    "TapHoleDiameter": "Hole to model before cutting the thread: tap drill plus this item's tap allowance.",
    "HoleDiameter": "Through-hole diameter: nominal diameter plus total hole allowance.",
    "LooseFitDiameter": "Loose pocket diameter across CORNERS. Use half for a hexagon's circumradius or use as a round pocket diameter.",
    "PressFitDiameter": "Press pocket diameter across CORNERS. Use half for a hexagon's circumradius or use as a round pocket diameter.",
    "LooseFitAcrossFlats": "Loose hex pocket width across opposite FLATS.",
    "PressFitAcrossFlats": "Press hex pocket width across opposite FLATS.",
    "NutAcrossCorners": "Ideal regular hexagon across corners, computed from nominal across flats; not catalog e minimum.",
}


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
    else:
        result["TapHoleDiameter"] = "TapDrillDiameter + TapHoleAllowance"
        result["HeadPocketDiameter"] = "HeadDiameter + HeadDiameterAllowance"
        result["HeadPocketDepth"] = "HeadHeight + HeadDepthAllowance"
        if kind == "countersunk":
            result["HeadPocketDiameter"] += " + 2 * HeadDepthAllowance * tan(CountersinkAngle / 2)"
            result["HeadPocketDepth"] = "(HeadPocketDiameter - HoleDiameter) / (2 * tan(CountersinkAngle / 2))"
    return result


def add(obj, name, value, group, type_id=LENGTH, description=""):
    obj.addProperty(type_id, name, group, description or DOCS.get(name, name))
    setattr(obj, name, value)


def create_fasteners(doc, requests):
    """Always create new objects; collisions never overwrite existing references."""
    prepared = [(item, allowances(item, a), calculate(item, a)) for item, a in requests]
    if not prepared:
        raise ValueError("Select at least one fastener to create.")
    result = []
    with transaction(doc, "Create fastener VarSets"):
        for item, a, calculated in prepared:
            name = f'{item["size"]}_{dict(socket_cap="SocketCap", countersunk="Countersunk", hex_nut="Nut")[item["kind"]]}'
            obj = doc.addObject("App::VarSet", name)
            obj.Label = name
            for key, value in {"LibraryId": item["id"], "FastenerKind": item["kind"],
                               "Standard": item["standard"], "ThreadSize": item["size"]}.items():
                add(obj, key, value, "Source", STRING)
            for key, value in item["dimensions"].items():
                add(obj, key, value, "Dimensions", ANGLE if key == "CountersinkAngle" else LENGTH)
            for key, label, _ in fields(item["kind"]):
                add(obj, key, a[key], "Allowances", DISTANCE,
                    f"{label}: total mm added to this dimension, not per side. Negative values reduce it.")
            for key in expressions(item["kind"]):
                description = DOCS.get(key, key)
                if item["kind"] == "countersunk" and key.startswith("HeadPocket"):
                    description = "90-degree (or selected angle) countersink geometry. Depth allowance expands the mouth while preserving the cone angle."
                add(obj, key, calculated[key], "Cutouts", description=description)
            for key, expression in expressions(item["kind"]).items():
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
    if obj.TypeId != "App::VarSet" or not hasattr(obj, "FastenerKind"):
        raise ValueError("Select a VarSet created by Fastener VarSets.")
    kind = obj.FastenerKind
    if kind not in ("socket_cap", "countersunk", "hex_nut"):
        raise ValueError(f"Unsupported fastener kind: {kind}")
    names = ["NominalDiameter", "Pitch"] + (
        ["NutAcrossFlats", "NutHeight"] if kind == "hex_nut"
        else ["HeadDiameter", "HeadHeight", "SocketAcrossFlats", "TapDrillDiameter"])
    if kind == "countersunk":
        names.append("CountersinkAngle")
    item = {"id": obj.LibraryId, "label": obj.Label, "kind": kind,
            "standard": obj.Standard, "size": obj.ThreadSize,
            "dimensions": {key: getattr(obj, key).Value for key in names}}
    a = {key: getattr(obj, key).Value for key, _, _ in fields(kind)}
    return item, a


def update_allowances(doc, requests):
    for obj, values in requests:
        item, _ = item_from_object(obj)
        calculate(item, values)
    with transaction(doc, "Adjust fastener allowances"):
        for obj, values in requests:
            for key, value in values.items():
                if key not in {field[0] for field in fields(obj.FastenerKind)}:
                    raise ValueError(f"Unknown allowance: {key}")
                obj.setExpression(key, None)
                setattr(obj, key, value)
        doc.recompute()
        check_objects([obj for obj, _ in requests])


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
