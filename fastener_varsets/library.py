"""Readable library, per-item preferences, and dimension calculations (millimetres)."""

import copy
import json
import math
import os
from pathlib import Path
import tempfile

KINDS = {"socket_cap": "Socket head cap / DIN 912", "countersunk": "Countersunk / DIN 7991",
         "hex_nut": "Hex nut / DIN 934"}
# key, display label, initial value. All additions are total dimensions, not per side.
COMMON = [("HoleAllowance", "Through-hole diameter", 0.5)]
SCREW = [("HeadDiameterAllowance", "Head recess diameter", 0.5),
         ("HeadDepthAllowance", "Head recess depth", 0.2),
         ("TapHoleAllowance", "Tap-drill / Kernloch diameter", 0.0)]
NUT = [("LooseFitAllowance", "Loose pocket across flats", 0.3),
       ("PressFitAllowance", "Press pocket across flats", -0.1),
       ("NutDepthAllowance", "Nut pocket depth", 0.2)]


def fields(kind):
    return COMMON + (NUT if kind == "hex_nut" else SCREW)


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
        required = ["NominalDiameter", "Pitch"] + (
            ["NutAcrossFlats", "NutHeight"] if kind == "hex_nut"
            else ["HeadDiameter", "HeadHeight", "SocketAcrossFlats", "TapDrillDiameter"])
        if kind == "countersunk":
            required.append("CountersinkAngle")
        dims = item.get("dimensions", {})
        for name in required:
            if number(dims.get(name), f"{key}.{name}") <= 0:
                raise ValueError(f"{key}.{name} must be positive.")
        if kind == "countersunk" and not 0 < dims["CountersinkAngle"] < 180:
            raise ValueError(f"{key}: countersink angle must be between 0 and 180 degrees.")
    return data


def load_library(user_dir):
    path = Path(user_dir) / "library.json"
    if not path.exists():
        bundled = Path(__file__).with_name("library.json")
        write_json(path, read_json(bundled))
    return validate_library(read_json(path))


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
        return {"version": 1, "items": {}, "selected": []}
    data = read_json(path)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("items"), dict):
        raise ValueError(f"Invalid allowances file: {path}")
    if not isinstance(data.get("selected", []), list):
        raise ValueError(f"Invalid selection list: {path}")
    return data
