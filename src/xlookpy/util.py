"""Serialization, fingerprints and explicit unit conversion."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pint

UNITS = pint.UnitRegistry()
UNITS.define("unassigned = [unassigned_signal]")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def factor(source, target):
    try:
        q = UNITS.Quantity(1, source).to(target)
        zero = UNITS.Quantity(0, source).to(target)
    except (pint.PintError, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot convert {source!r} to {target!r}; check channel/calibration units.") from exc
    if zero.magnitude != 0:
        raise ValueError("Offset units are not supported in this prototype.")
    return float(q.magnitude)


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
