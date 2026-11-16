"""Readable library, per-item preferences, and dimension calculations (millimetres)."""

import copy
import json
import math
import os
from pathlib import Path
import tempfile

KINDS = {"socket_cap": "Socket head cap / DIN 912", "countersunk": "Countersunk / DIN 7991",
         "hex_nut": "Hex nut / DIN 934", "heat_insert": "Heat insert / CNC Kitchen"}
# key, display label, initial value. All additions are total dimensions, not per side.
COMMON = [("HoleAllowance", "Through-hole diameter", 0.5)]
SCREW = [("HeadDiameterAllowance", "Head recess diameter", 0.5),
         ("HeadDepthAllowance", "Head recess depth", 0.2),
         ("TapHoleAllowance", "Tap-drill / Kernloch diameter", 0.0)]
NUT = [("LooseFitAllowance", "Loose pocket across flats", 0.3),
       ("PressFitAllowance", "Press pocket across flats", -0.1),
       ("NutDepthAllowance", "Nut pocket depth", 0.2)]
INSERT = [("InsertDiameterAllowance", "Insert installation-hole diameter", 0.0),
          ("InsertDepthAllowance", "Insert pocket depth", 0.0)]
INSERT_UPGRADE = "cnc-kitchen-standard-inserts-v1"


def fields(kind):
    common = [("HoleAllowance", "Screw clearance-hole diameter", 0.5)] if kind == "heat_insert" else COMMON
    return common + {"hex_nut": NUT, "heat_insert": INSERT,
                     "socket_cap": SCREW, "countersunk": SCREW}[kind]


def dimension_fields(kind):
    """Canonical base dimensions, shared by library validation and project reads."""
    result = ["NominalDiameter", "Pitch"]
    if kind == "hex_nut":
        return result + ["NutAcrossFlats", "NutHeight"]
    if kind == "heat_insert":
        return result + ["InsertLength", "InsertOutsideDiameter", "RecommendedHoleDiameter",
                         "RecommendedHoleDepth", "MinimumWallThickness"]
    result += ["HeadDiameter", "HeadHeight", "SocketAcrossFlats", "TapDrillDiameter"]
    return result + (["CountersinkAngle"] if kind == "countersunk" else [])


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    return float(value)


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path, data):
    """Atomic replacement, so a failed write cannot truncate a user's library."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_library(data):
    if not isinstance(data, dict) or data.get("format") != "fastener-varsets-library" or data.get("version") != 1:
        raise ValueError("Expected a Fastener VarSets library, version 1.")
    if data.get("units") != "mm" or not isinstance(data.get("items"), list) or not data["items"]:
        raise ValueError("The library needs units 'mm' and a non-empty items list.")
    ids = set()
    for item in data["items"]:
        if not isinstance(item, dict):
            raise ValueError("Each library item must be an object.")
        key, kind = item.get("id"), item.get("kind")
        if not isinstance(key, str) or not key or key in ids or kind not in KINDS:
            raise ValueError("Library item IDs must be unique; each item needs a supported kind.")
        ids.add(key)
        for attr in ("label", "standard", "size"):
            if not isinstance(item.get(attr), str) or not item[attr]:
                raise ValueError(f"{key}: missing {attr}.")
        dims = item.get("dimensions", {})
        if not isinstance(dims, dict):
            raise ValueError(f"{key}: dimensions must be an object.")
        for name in dimension_fields(kind):
            if number(dims.get(name), f"{key}.{name}") <= 0:
                raise ValueError(f"{key}.{name} must be positive.")
        if kind == "countersunk" and not 0 < dims["CountersinkAngle"] < 180:
            raise ValueError(f"{key}: countersink angle must be between 0 and 180 degrees.")
        if kind == "heat_insert":
            for attr in ("manufacturer", "model"):
                if not isinstance(item.get(attr), str) or not item[attr]:
                    raise ValueError(f"{key}: missing {attr}.")
            calculate(item, {key: 0 for key, _, _ in fields(kind)})
    if not isinstance(data.get("upgrades", []), list):
        raise ValueError("Library upgrades must be a list.")
    return data


def load_library(user_dir):
    path = Path(user_dir) / "library.json"
    bundled = read_json(Path(__file__).with_name("library.json"))
    if not path.exists():
        write_json(path, bundled)
    data = validate_library(read_json(path))
    if INSERT_UPGRADE not in data.get("upgrades", []):
        # Record the migration in the same atomic write as its additions. A user
        # can then remove an insert intentionally without it returning next load.
        ids = {item["id"] for item in data["items"]}
        data["items"].extend(copy.deepcopy(item) for item in bundled["items"]
                             if item["kind"] == "heat_insert" and item["id"] not in ids)
        sources = data.setdefault("sources", [])
        urls = {source.get("url") for source in sources}
        sources.extend(copy.deepcopy(source) for source in bundled["sources"]
                       if source["standard"] == "CNC Kitchen" and source["url"] not in urls)
        data.setdefault("upgrades", []).append(INSERT_UPGRADE)
        validate_library(data)
        write_json(path, data)
    return data


def allowances(item, overrides=None):
    result = {key: default for key, _, default in fields(item["kind"])}
    for key in result:
        if overrides and key in overrides:
            result[key] = number(overrides[key], key)
    return result


def calculate(item, offsets=None):
    a = allowances(item, offsets)
    d = copy.deepcopy(item["dimensions"])
    d["HoleDiameter"] = d["NominalDiameter"] + a["HoleAllowance"]
    if item["kind"] == "hex_nut":
        factor = 2 / math.sqrt(3)
        d["NutAcrossCorners"] = d["NutAcrossFlats"] * factor
        for fit in ("Loose", "Press"):
            d[f"{fit}FitAcrossFlats"] = d["NutAcrossFlats"] + a[f"{fit}FitAllowance"]
            d[f"{fit}FitDiameter"] = d[f"{fit}FitAcrossFlats"] * factor
        d["NutPocketDepth"] = d["NutHeight"] + a["NutDepthAllowance"]
        if d["LooseFitAcrossFlats"] < d["PressFitAcrossFlats"]:
            raise ValueError("Loose-fit pocket must be at least as wide as the press-fit pocket.")
    elif item["kind"] == "heat_insert":
        d["InsertHoleDiameter"] = d["RecommendedHoleDiameter"] + a["InsertDiameterAllowance"]
        d["InsertPocketDepth"] = d["RecommendedHoleDepth"] + a["InsertDepthAllowance"]
        if not d["NominalDiameter"] < d["InsertHoleDiameter"] < d["InsertOutsideDiameter"]:
            raise ValueError("Insert installation-hole diameter must be between the thread and outside diameters.")
        if d["InsertPocketDepth"] < d["InsertLength"]:
            raise ValueError("Insert pocket depth must be at least the insert length.")
    else:
        d["TapHoleDiameter"] = d["TapDrillDiameter"] + a["TapHoleAllowance"]
        d["HeadPocketDiameter"] = d["HeadDiameter"] + a["HeadDiameterAllowance"]
        if item["kind"] == "countersunk":
            slope = math.tan(math.radians(d["CountersinkAngle"] / 2))
            d["HeadPocketDiameter"] += 2 * a["HeadDepthAllowance"] * slope
            d["HeadPocketDepth"] = (d["HeadPocketDiameter"] - d["HoleDiameter"]) / (2 * slope)
        else:
            d["HeadPocketDepth"] = d["HeadHeight"] + a["HeadDepthAllowance"]
        if d["HeadPocketDiameter"] <= d["HoleDiameter"]:
            raise ValueError("Head pocket diameter must exceed the through-hole diameter.")
        if d["TapHoleDiameter"] >= d["NominalDiameter"]:
            raise ValueError("Tap hole must be smaller than the nominal thread diameter.")
    for name, value in d.items():
        if number(value, name) <= 0:
            raise ValueError(f"{name} must remain positive after adding the allowance.")
    return d


def load_preferences(user_dir):
    path = Path(user_dir) / "allowances.json"
    if not path.exists():
        return {"version": 1, "items": {}, "selected": [],
                "short_object_names": True, "short_dimension_names": True}
    data = read_json(path)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("items"), dict):
        raise ValueError(f"Invalid allowances file: {path}")
    if not isinstance(data.get("selected", []), list):
        raise ValueError(f"Invalid selection list: {path}")
    for key in ("short_object_names", "short_dimension_names"):
        data.setdefault(key, True)
        if not isinstance(data[key], bool):
            raise ValueError(f"Invalid naming setting {key}: {path}")
    return data
