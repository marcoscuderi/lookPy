"""Calibration definitions are data; evaluation functions live here.

Polynomial coefficients always use descending powers. Elastic models describe
elastic displacement e(F), not a tangent stiffness polynomial.
"""
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import re
import numpy as np
from .util import canonical, digest, factor


class Calibration:
    def __init__(self, record):
        self._record = deepcopy(record)
        r = self._record
        required = {"schema_version", "id", "category", "apparatus", "sensor", "date",
                    "input_unit", "output_unit", "model", "parameters", "valid_range", "notes"}
        if not required <= r.keys() or r["schema_version"] != 1:
            raise ValueError(f"Calibration requires schema_version=1 and fields {sorted(required)}.")
        if not isinstance(r["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", r["id"]):
            raise ValueError("Calibration id must contain path segments using letters, numbers, _, - or .")
        if any(p in (".", "..") for p in r["id"].split("/")):
            raise ValueError("Calibration id cannot contain . or .. path segments.")
        for key in ("apparatus", "sensor", "notes"):
            if not isinstance(r[key], str):
                raise ValueError(f"{key} must be text.")
        date.fromisoformat(r["date"])
        if r["category"] not in ("sensor", "apparatus"):
            raise ValueError("category must be sensor or apparatus.")
        if r["model"] not in ("linear", "polynomial"):
            raise ValueError("model must be linear or polynomial.")
        if r["model"] == "linear":
            p = r["parameters"]
            if set(p) != {"slope", "intercept"}:
                raise ValueError("linear parameters are slope and intercept.")
            coefficients = [p["slope"], p["intercept"]]
        else:
            if set(r["parameters"]) != {"coefficients"}:
                raise ValueError("polynomial parameters contain coefficients, highest power first.")
            coefficients = r["parameters"]["coefficients"]
        c = np.asarray(coefficients, dtype=float)
        if c.ndim != 1 or len(c) < 2 or not np.isfinite(c).all():
            raise ValueError("Provide at least two finite coefficients, highest power first.")
        c.setflags(write=False)
        self._coefficients = c
        factor(r["input_unit"], r["input_unit"])
        factor(r["output_unit"], r["output_unit"])
        bounds = np.asarray(r["valid_range"], float)
        if bounds.shape != (2,) or not np.isfinite(bounds).all() or bounds[0] >= bounds[1]:
            raise ValueError("valid_range must be [lower, upper] in input units, lower < upper.")
        if r["category"] == "apparatus":
            factor(r["input_unit"], "kN")
            factor(r["output_unit"], "mm")
            # Positive tangent compliance throughout the declared polynomial domain.
            derivative = np.polyder(c)
            roots = np.roots(np.polyder(derivative)) if len(derivative) > 1 else []
            points = [*bounds, *[float(z.real) for z in roots if abs(z.imag) < 1e-9 and bounds[0] < z.real < bounds[1]]]
            if np.any(np.polyval(derivative, points) <= 0):
                raise ValueError("Apparatus e(F) must have positive compliance across valid_range.")
        canonical(r)  # Reject non-JSON values and non-finite coefficients in the record itself.

    @property
    def record(self):
        return deepcopy(self._record)

    @property
    def id(self):
        return self._record["id"]

    @property
    def fingerprint(self):
        return digest(self._record)

    def evaluate(self, values, *, outside="error"):
        if outside not in ("error", "mask", "clip", "extrapolate"):
            raise ValueError("outside must be error, mask, clip or extrapolate.")
        x = np.asarray(values, float)
        lo, hi = self._record["valid_range"]
        finite = np.isfinite(x)
        bad = finite & ((x < lo) | (x > hi))
        if bad.any() and outside == "error":
            raise ValueError(f"{self.id}: {bad.sum()} samples outside [{lo}, {hi}] {self._record['input_unit']}. Choose the interval or an explicit outside policy.")
        xx = np.clip(x, lo, hi) if outside == "clip" else x
        with np.errstate(over="ignore", invalid="ignore"):
            y = np.polyval(self._coefficients, xx)
        y = np.where(finite, y, np.nan)
        if outside == "mask":
            y = np.where(bad, np.nan, y)
        if np.any(finite & ~np.isfinite(y) & ~(bad & (outside == "mask"))):
            raise ValueError(f"{self.id}: calibration produced non-finite values; inspect coefficients/range.")
        return y, int(bad.sum())


class Registry:
    """Central user-managed folder. Import is exclusive; a revision is never overwritten."""
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("XLOOKPY_CALIBRATIONS", Path.home() / ".xlookpy" / "calibrations")).expanduser().resolve()

    def get(self, identifier):
        # Validate path independently before touching the filesystem.
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", identifier) or any(p in (".", "..") for p in identifier.split("/")):
            raise ValueError("Invalid calibration identifier.")
        # Append extension; revisions may themselves contain dots.
        path = Path(str(self.root.joinpath(*identifier.split("/"))) + ".json")
        if not path.is_file():
            raise FileNotFoundError(f"Calibration {identifier!r} is not installed in {self.root}. Import its JSON first.")
        cal = Calibration(json.loads(path.read_text(encoding="utf-8")))
        if cal.id != identifier:
            raise ValueError(f"Registry path and calibration id differ: {path}.")
        return cal

    def import_file(self, source):
        cal = Calibration(json.loads(Path(source).read_text(encoding="utf-8")))
        path = Path(str(self.root.joinpath(*cal.id.split("/"))) + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(cal.record, stream, indent=2, allow_nan=False)
                stream.write("\n")
        except FileExistsError:
            if self.get(cal.id).fingerprint != cal.fingerprint:
                raise ValueError(f"{cal.id} already exists with different values. Give the new calibration a new id/revision.") from None
        return cal

    def list(self):
        return [Calibration(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(self.root.rglob("*.json"))]
