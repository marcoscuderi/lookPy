"""Aligned channels with immutable source record IDs and explicit operations."""
from copy import deepcopy
from dataclasses import dataclass
import numpy as np
from .util import factor


@dataclass(frozen=True)
class Records:
    """Inclusive original zero-based record identifiers, never current positions."""
    start: int
    end: int

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) for v in (self.start, self.end)) or self.start < 0 or self.end < self.start:
            raise ValueError("Records require integer IDs with 0 <= start <= end (inclusive).")

    def json(self):
        return {"start": int(self.start), "end": int(self.end), "inclusive": True, "basis": "original_record_id"}


@dataclass(frozen=True)
class Channel:
    values: np.ndarray
    unit: str
    metadata: dict

    def __post_init__(self):
        a = np.array(self.values, dtype=float, copy=True)
        if a.ndim != 1:
            raise ValueError("Channels must be one-dimensional.")
        a.setflags(write=False)
        object.__setattr__(self, "values", a)
        object.__setattr__(self, "metadata", deepcopy(self.metadata))

    @property
    def valid(self):
        return np.isfinite(self.values)


class Experiment:
    def __init__(self, channels, *, metadata=None, record_ids=None, session=None):
        self._channels = dict(channels)
        lengths = {len(c.values) for c in channels.values()}
        if len(lengths) != 1 or not channels or next(iter(lengths)) < 1:
            raise ValueError("At least one nonempty channel is needed; all channels must have equal lengths.")
        n = next(iter(lengths))
        ids = np.arange(n, dtype=np.int64) if record_ids is None else np.array(record_ids, dtype=np.int64, copy=True)
        if ids.shape != (n,) or np.any(ids < 0) or np.any(np.diff(ids) <= 0):
            raise ValueError("Original record IDs must be nonnegative and strictly increasing.")
        ids.setflags(write=False)
        self.record_ids = ids
        self.metadata = deepcopy(metadata or {})
        self.history = []
        self._session = session

    def __len__(self):
        return len(self.record_ids)

    @property
    def channels(self):
        return tuple(self._channels)

    def __getitem__(self, name):
        try:
            return self._channels[name]
        except KeyError:
            raise KeyError(f"Unknown channel {name!r}. Available: {', '.join(self.channels)}") from None

    def records(self, start, end):
        r = Records(start, end)
        self._selection(r)
        return r

    def _selection(self, records):
        if records is None:
            return np.ones(len(self), dtype=bool)
        if not isinstance(records, Records):
            raise TypeError("Use exp.records(start, end); both endpoints are inclusive original IDs.")
        if not np.isin([records.start, records.end], self.record_ids).all():
            raise ValueError("Both selection endpoints must exist in this experiment's original record IDs.")
        return (self.record_ids >= records.start) & (self.record_ids <= records.end)

    def slice(self, records):
        keep = self._selection(records)
        result = Experiment({k: Channel(c.values[keep], c.unit, c.metadata) for k, c in self._channels.items()},
                            metadata=self.metadata, record_ids=self.record_ids[keep], session=self._session)
        result.history = deepcopy(self.history) + [{"operation": "slice", "records": records.json()}]
        return result

    def _put(self, output, values, unit, operation):
        if not isinstance(output, str) or not output or output == "record_id" or any(c in output for c in "\t\r\n"):
            raise ValueError("Choose a nonempty output channel name without tabs/newlines (record_id is reserved).")
        if output in self._channels:
            raise ValueError(f"Channel {output!r} already exists. Choose a new output name or run the script from the beginning.")
        factor(unit, unit)
        parent_names = [operation[k] for k in ("input", "force", "shear", "normal") if k in operation]
        calibrated = operation["operation"] in ("calibrate", "convert_acquisition") or any(
            self[name].metadata.get("sensor_calibrated", False) for name in parent_names)
        c = Channel(values, unit, {"role": "derived", "sensor_calibrated": calibrated, **deepcopy(operation)})
        if len(c.values) != len(self):
            raise ValueError("Operation output length differs from experiment length.")
        self._channels[output] = c
        self.history.append({**deepcopy(operation), "output": output, "unit": unit,
                             "finite_samples": int(c.valid.sum()), "invalid_samples": int((~c.valid).sum())})
        return self

    def _remember(self, cal):
        if self._session is not None:
            self._session._remember(cal)

    def convert_acquisition(self, source, *, unit, output):
        """Apply TDMS Slope/Intercept metadata once to a stored-value channel.

        npTDMS may already apply NI format scaling. This operation applies the
        separate custom Slope/Intercept properties; their meaning is operator-verified.
        """
        c = self[source]
        if c.metadata.get("role") != "stored_tdms":
            raise ValueError("Acquisition conversion requires an original stored TDMS channel; converted/derived channels are refused.")
        p = c.metadata.get("properties", {})
        if "Slope" not in p or "Intercept" not in p:
            raise ValueError(f"{source} has no Slope/Intercept properties. Use an explicit sensor calibration instead.")
        slope, intercept = float(p["Slope"]), float(p["Intercept"])
        if not np.isfinite([slope, intercept]).all():
            raise ValueError("Acquisition coefficients must be finite.")
        return self._put(output, c.values * slope + intercept, unit,
                         {"operation": "convert_acquisition", "input": source, "slope": slope,
                          "intercept": intercept, "unit_basis": "operator_supplied",
                          "note": "Custom TDMS properties applied to npTDMS reader values; NI scaling is separate."})

    def calibrate(self, source, *, using, output, outside="error"):
        c = self[source]
        r = using.record
        if r["category"] != "sensor":
            raise ValueError("calibrate() needs a sensor record. For an apparatus record use correct_displacement().")
        if c.metadata.get("sensor_calibrated", False):
            raise ValueError("This channel was already calibrated. Start from the stored source channel.")
        x = c.values * factor(c.unit, r["input_unit"])
        y, count = using.evaluate(x, outside=outside)
        self._remember(using)
        return self._put(output, y, r["output_unit"], {"operation": "calibrate", "input": source,
                         "calibration_id": using.id, "calibration_sha256": using.fingerprint,
                         "outside": outside, "outside_samples": count})

    def convert(self, source, *, unit, output, scale=1.0):
        """Convert compatible units and optionally invert a coordinate using scale=-1."""
        if not np.isfinite(scale) or scale == 0:
            raise ValueError("scale must be finite and nonzero.")
        c = self[source]
        return self._put(output, c.values * factor(c.unit, unit) * scale, unit,
                         {"operation": "convert", "input": source, "scale": float(scale)})

    def zero(self, source, *, reference, output):
        """Subtract the finite mean within an explicit reference interval; no clipping."""
        c = self[source]
        good = self._selection(reference) & c.valid
        if not good.any():
            raise ValueError("The reference interval contains no finite values.")
        offset = float(np.mean(c.values[good]))
        return self._put(output, c.values - offset, c.unit,
                         {"operation": "zero", "input": source, "reference": reference.json(), "offset": offset})

    def zero_at(self, source, *, record, output):
        """Set the picked contact sample to zero and force earlier samples to zero.

        At/after contact: output[i] = input[i] - input[contact]. Later negative
        values and NaNs are retained. Uses immutable original record IDs.
        """
        if isinstance(record, bool) or not isinstance(record, (int, np.integer)):
            raise ValueError("Contact record must be one integer original record ID, not a time or interval.")
        positions = np.flatnonzero(self.record_ids == record)
        if len(positions) != 1:
            raise ValueError(f"Contact record {record} is not present in this experiment. Pick an original record ID on the plot.")
        c = self[source]
        offset = float(c.values[positions[0]])
        if not np.isfinite(offset):
            raise ValueError(f"{source} is invalid at contact record {record}. Pick a finite contact sample.")
        values = c.values - offset
        before = self.record_ids < record
        values[before] = 0.0
        return self._put(output, values, c.unit, {"operation": "zero_at", "input": source,
                         "contact_record": int(record), "offset": offset,
                         "before_contact": "forced_zero", "zeroed_before_samples": int(before.sum()),
                         "after_contact": "input_minus_contact_value; negative values and missing samples retained"})

    def mask(self, source, *, records, output, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Explain the reason for masking the interval.")
        c = self[source]
        y = c.values.copy()
        y[self._selection(records)] = np.nan
        return self._put(output, y, c.unit, {"operation": "mask", "input": source,
                         "records": records.json(), "reason": reason})

    def stress(self, source, *, area_mm2, output, surfaces=1):
        if not np.isfinite(area_mm2) or area_mm2 <= 0 or isinstance(surfaces, bool) or not isinstance(surfaces, int) or surfaces < 1:
            raise ValueError("area_mm2 must be positive; surfaces must be a positive integer.")
        y = self[source].values * factor(self[source].unit, "N") / (area_mm2 * surfaces)
        return self._put(output, y, "MPa", {"operation": "stress", "input": source,
                         "area_mm2": float(area_mm2), "surfaces": surfaces})

    def friction(self, shear, normal, *, output="friction", min_normal_MPa=0.01, records=None):
        if not np.isfinite(min_normal_MPa) or min_normal_MPa < 0:
            raise ValueError("min_normal_MPa must be finite and nonnegative.")
        tau = self[shear].values * factor(self[shear].unit, "MPa")
        sigma = self[normal].values * factor(self[normal].unit, "MPa")
        good = np.isfinite(tau) & np.isfinite(sigma) & (sigma > min_normal_MPa) & self._selection(records)
        y = np.full(len(self), np.nan)
        np.divide(tau, sigma, out=y, where=good)
        return self._put(output, y, "dimensionless", {"operation": "friction", "shear": shear,
                         "normal": normal, "min_normal_MPa": float(min_normal_MPa),
                         "records": records.json() if records else None})

    def correct_displacement(self, source, *, force, using, output, reference_record, sign=-1, outside="error", records=None):
        """u_corrected = (u-u_ref) + sign * (e(F)-e(F_ref)).

        e(F) is the calibrated elastic deformation, in length units. sign=-1
        subtracts deformation when measured displacement increases with load.
        This reversible, single-valued model does not model apparatus hysteresis.
        With records= only that stage is corrected; other values become NaN.
        """
        r = using.record
        if r["category"] != "apparatus":
            raise ValueError("correct_displacement() needs an apparatus calibration e(F).")
        if sign not in (-1, 1):
            raise ValueError("sign must be -1 (subtract) or +1 (add).")
        positions = np.flatnonzero(self.record_ids == reference_record)
        if len(positions) != 1:
            raise ValueError("reference_record must be an original record ID present in the experiment.")
        i = positions[0]
        active = self._selection(records)
        if not active[i]:
            raise ValueError("reference_record must lie inside the correction interval.")
        f = self[force].values * factor(self[force].unit, r["input_unit"])
        e = np.full(len(self), np.nan)
        e[active], count = using.evaluate(f[active], outside=outside)
        e *= factor(r["output_unit"], self[source].unit)
        u = self[source].values
        if not np.isfinite([e[i], u[i]]).all():
            raise ValueError("The correction reference is invalid or outside the calibration range.")
        y = np.where(active, (u-u[i]) + sign*(e-e[i]), np.nan)
        self._remember(using)
        return self._put(output, y, self[source].unit, {"operation": "correct_displacement",
                         "input": source, "force": force, "reference_record": int(reference_record),
                         "sign": sign, "outside": outside, "outside_samples": count,
                         "records": records.json() if records else None,
                         "calibration_id": using.id, "calibration_sha256": using.fingerprint,
                         "algorithm": "reference-relative elastic deformation e(F); not tangent-stiffness integration"})

    def derivative(self, source, *, time="time", window_s, output, records=None, min_points=5, max_gap_s=None):
        """Local linear least-squares slope using a centred full-width window_s.

        Uses actual times, equal sample weights, >=min_points, full support at
        edges, and no bridging NaNs, excluded records, or gaps >max_gap_s.
        Choose window_s smaller than the event duration you want to resolve.
        """
        if not np.isfinite(window_s) or window_s <= 0 or isinstance(min_points, bool) or not isinstance(min_points, int) or min_points < 3:
            raise ValueError("window_s must be positive; min_points must be an integer >=3.")
        if max_gap_s is not None and (not np.isfinite(max_gap_s) or max_gap_s <= 0):
            raise ValueError("max_gap_s must be positive or None.")
        t = self[time].values * factor(self[time].unit, "s")
        if not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
            raise ValueError("Time must be finite and strictly increasing; select a valid acquisition segment.")
        y = self[source].values
        valid = np.isfinite(y) & self._selection(records)
        split = np.r_[True, ~valid[:-1] | ~valid[1:] | (np.diff(self.record_ids) != 1)]
        if max_gap_s is not None:
            split[1:] |= np.diff(t) > max_gap_s
        starts = np.flatnonzero(valid & split)
        result = np.full(len(self), np.nan)
        # Each valid segment is handled independently, without interpolating gaps.
        ends = np.r_[np.flatnonzero(valid[:-1] & split[1:]) + 1, len(self)]
        for start in starts:
            candidates = ends[ends > start]
            end = int(candidates[0]) if len(candidates) else len(self)
            bad = np.flatnonzero(~valid[start:end])
            if len(bad):
                end = start + int(bad[0])
            tt = t[start:end] - t[start]
            if len(tt) < min_points:
                continue
            # Recenter in blocks with a window halo. A single experiment-wide
            # prefix sum catastrophically cancels at long times/small windows.
            for b in range(0, len(tt), 4096):
                stop = min(b+4096, len(tt))
                targets = tt[b:stop]
                left = np.searchsorted(tt, targets-window_s/2, side="left")
                right = np.searchsorted(tt, targets+window_s/2, side="right")
                first, last = int(left[0]), int(right[-1])
                center = (first+last)//2
                tx = tt[first:last]-tt[center]
                yy = y[start+first:start+last]-y[start+center]
                n = right-left
                sums = [np.r_[0., np.cumsum(a)] for a in (tx, yy, tx*tx, tx*yy)]
                st, sy, stt, sty = [a[right-first]-a[left-first] for a in sums]
                with np.errstate(divide="ignore", invalid="ignore"):
                    numerator = sty-st*sy/n
                    denominator = stt-st*st/n
                    slopes = numerator/denominator
                good = (n >= min_points) & (targets >= window_s/2) & (targets <= tt[-1]-window_s/2) & (denominator > 0)
                result[start+b:start+stop][good] = slopes[good]
        return self._put(output, result, f"({self[source].unit})/s", {"operation": "derivative",
                         "input": source, "time": time, "window_s": float(window_s),
                         "min_points": min_points, "max_gap_s": max_gap_s,
                         "records": records.json() if records else None,
                         "algorithm": "centred local linear regression; equal sample weights; full-width support; no gap bridging"})

    def plot(self, *, x="time", left, right=None, title=None):
        for name in (x, left, right):
            if name is not None:
                self[name]
        spec = {"x": x, "left": left, "right": right, "title": title or left}
        if self._session is None:
            raise RuntimeError("Use a Session to record plots and open them in the desktop app.")
        self._session.plots.append(spec)
        return spec

    def summary(self):
        return [{"name": name, "unit": c.unit, "finite": int(c.valid.sum()),
                 "invalid": int((~c.valid).sum()), "metadata": deepcopy(c.metadata)}
                for name, c in self._channels.items()]
