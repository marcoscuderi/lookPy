"""Channel operations corresponding to the rawPy laboratory workflow.

Selections use inclusive original record IDs. Raw inputs are protected; working
transformations update in place unless a separate output name is supplied.
"""
import numpy as np
from .util import factor, json_value


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")
    return int(value)


class AnalysisOperations:
    def _position(self, record):
        _integer(record, "record", 0)
        pos = np.flatnonzero(self.record_ids == record)
        if len(pos) != 1:
            raise ValueError(f"Original record {record} is not present in this experiment.")
        return int(pos[0])

    def shift(self, source, *, value, output=None, unit=None, records=None):
        """Add a constant in compatible units, optionally within one interval."""
        output = source if output is None else output
        c = self[source]
        if not np.isfinite(value):
            raise ValueError("Shift value must be finite.")
        delta = float(value) * factor(unit or c.unit, c.unit)
        y = c.values.copy()
        y[self._selection(records)] += delta
        return self._put(output, y, c.unit, {"operation": "shift", "input": source,
                         "value": delta, "records": records.json() if records else None})

    def offset(self, source, *, records, output=None):
        """Flatten [start,end] at the start value; shift all later data to reconnect.

        This removes the measured change between the two endpoints, not a trend.
        """
        output = source if output is None else output
        self._selection(records)
        a, b = self._position(records.start), self._position(records.end)
        c = self[source]
        if not np.isfinite(c.values[[a, b]]).all():
            raise ValueError("Offset endpoints must both have finite values.")
        y = c.values.copy()
        y[a:b+1] = c.values[a]
        y[b+1:] += c.values[a] - c.values[b]
        return self._put(output, y, c.unit, {"operation": "offset", "input": source,
                         "records": records.json(), "removed_change": float(c.values[b]-c.values[a]),
                         "algorithm": "flatten interval; shift subsequent samples; earlier samples unchanged"})

    def elastic_correct(self, source, *, load, stiffness, stiffness_unit, reference_record, output=None):
        """Constant stiffness: (u-u_ref) - (load-load_ref)/k.

        load can be force or stress; stiffness_unit must then be force/length
        or stress/length, respectively. Prefer correct_displacement(using=...)
        for centrally managed calibrations and nonlinear apparatus models.
        """
        output = source if output is None else output
        if not np.isfinite(stiffness) or stiffness <= 0:
            raise ValueError("Stiffness must be finite and positive.")
        i = self._position(reference_record)
        c, f = self[source], self[load]
        factor(c.unit, "mm")
        # Reject arbitrary dimensional combinations even if their quotient is length.
        from .util import UNITS
        if not (UNITS.Unit(f.unit).is_compatible_with("N") or UNITS.Unit(f.unit).is_compatible_with("MPa")):
            raise ValueError("Elastic correction load must have force or stress units.")
        k = float(stiffness)*factor(stiffness_unit, f"({f.unit})/({c.unit})")
        if not np.isfinite([c.values[i], f.values[i]]).all():
            raise ValueError("Elastic correction reference must be finite.")
        y = c.values-c.values[i]-(f.values-f.values[i])/k
        return self._put(output, y, c.unit, {"operation": "elastic_correct", "input": source,
                         "force": load, "stiffness": float(stiffness), "stiffness_unit": stiffness_unit,
                         "reference_record": int(reference_record),
                         "algorithm": "constant stiffness; reference-relative displacement minus load/k"})

    def layer_thickness(self, source, *, reference_record, thickness, output,
                        unit="mm", layers=2, closure_sign=-1):
        """Per-layer thickness = measured reference thickness + sign*(u-u_ref)/layers.

        closure_sign=-1 when positive displacement closes the assembly; +1 for
        a displacement coordinate increasing with assembly thickness.
        """
        layers = _integer(layers, "layers")
        if closure_sign not in (-1, 1) or isinstance(closure_sign, bool):
            raise ValueError("closure_sign must be -1 or +1.")
        if not np.isfinite(thickness) or thickness <= 0:
            raise ValueError("Reference thickness must be finite and positive.")
        factor(unit, "mm")
        c = self[source]
        i = self._position(reference_record)
        if not np.isfinite(c.values[i]):
            raise ValueError("Thickness reference displacement must be finite.")
        y = float(thickness)+closure_sign*(c.values-c.values[i])*factor(c.unit, unit)/layers
        if np.any(y[np.isfinite(y)] <= 0):
            raise ValueError("Calculated layer thickness is nonpositive. Check sign, reference and layer count.")
        return self._put(output, y, unit, {"operation": "layer_thickness", "input": source,
                         "reference_record": int(reference_record), "reference_thickness": float(thickness),
                         "layers": layers, "closure_sign": closure_sign})

    def shear_strain(self, source, *, thickness, reference_record, output="shear_strain"):
        """Accumulate delta slip / mean adjacent thickness, from a picked reference.

        Before reference: NaN. A missing increment breaks the cumulative result;
        it is never silently bridged. Use a new interval/reference after a gap.
        """
        i = self._position(reference_record)
        c, h = self[source], self[thickness]
        factor(c.unit, "mm")
        hh = h.values*factor(h.unit, c.unit)
        if np.any(hh[np.isfinite(hh)] <= 0):
            raise ValueError("Shear strain requires strictly positive layer thickness.")
        if not np.isfinite([c.values[i], hh[i]]).all():
            raise ValueError("Strain reference displacement and thickness must be finite.")
        increments = np.diff(c.values[i:])/((hh[i+1:]+hh[i:-1])/2)
        increments[np.diff(self.record_ids[i:]) != 1] = np.nan
        y = np.full(len(self), np.nan)
        y[i:] = np.r_[0., np.cumsum(increments)]
        return self._put(output, y, "dimensionless", {"operation": "shear_strain", "input": source,
                         "thickness": thickness, "reference_record": int(reference_record),
                         "algorithm": "incremental slip / arithmetic mean adjacent thickness; cumulative, no gap bridging"})

    def geometrical_thinning(self, source, *, thickness, block_length, output,
                            unit="mm", reference_record=None, model="rawpy_triangular"):
        """Reproduce rawPy.rgt's triangular recurrence, including lagged thickness.

        h_corrected[0]=h[0]; h_corrected[i]=h[i-1] +
        sum(j=1..i, h[j-1]*(d[j]-d[j-1])/(2*L)).
        This named legacy model is supplied for comparison, not reinterpreted as
        a validated updated physical law. Signed displacement increments are used.
        """
        if model != "rawpy_triangular":
            raise ValueError("Available model: rawpy_triangular (legacy rawPy recurrence).")
        if not np.isfinite(block_length) or block_length <= 0:
            raise ValueError("Block length must be finite and positive.")
        factor(unit, "mm")
        i = 0 if reference_record is None else self._position(reference_record)
        d = self[source].values[i:]*factor(self[source].unit, unit)
        h = self[thickness].values[i:]*factor(self[thickness].unit, unit)
        if not np.isfinite(d).all() or not np.isfinite(h).all() or np.any(h <= 0):
            raise ValueError("Geometrical thinning needs finite displacement and positive finite thickness from the reference.")
        if np.any(np.diff(self.record_ids[i:]) != 1):
            raise ValueError("Geometrical thinning cannot integrate across dropped records.")
        y = np.full(len(self), np.nan)
        y[i] = h[0]
        y[i+1:] = h[:-1]+np.cumsum(h[:-1]*np.diff(d)/(2*block_length))
        return self._put(output, y, unit, {"operation": "geometrical_thinning", "input": source,
                         "thickness": thickness, "block_length": float(block_length),
                         "reference_record": int(self.record_ids[i]), "model": model,
                         "note": "Exact legacy rawPy recurrence, including previous-sample thickness; validate scientific applicability separately."})

    def fit(self, x, y, *, records, output, degree=1):
        """Stable polynomial fit on an interval; return diagnostics, add fitted channel.

        Ascending coefficients use the original x coordinate. Evaluation uses a
        centered/scaled Polynomial for stability. Output outside selection is NaN.
        """
        from numpy.polynomial import Polynomial
        degree = _integer(degree, "degree", 0)
        xx, yy = self[x].values, self[y].values
        active = self._selection(records)
        good = active & np.isfinite(xx) & np.isfinite(yy)
        if good.sum() <= degree or np.unique(xx[good]).size <= degree:
            raise ValueError("Fit needs more finite samples and distinct x values than the polynomial degree.")
        if degree == 0:
            poly = Polynomial([float(np.mean(yy[good]))])
        else:
            poly, stats = Polynomial.fit(xx[good], yy[good], degree, full=True)
            if stats[1] < degree+1:
                raise ValueError("Polynomial fit is rank deficient; reduce degree or change the interval.")
        predicted = poly(xx[good])
        residual = yy[good]-predicted
        sse = float(residual@residual)
        total = float(np.sum((yy[good]-np.mean(yy[good]))**2))
        result = {"coefficients": poly.convert().coef.tolist(), "coefficient_order": "ascending",
                  "normalized_coefficients": poly.coef.tolist(), "domain": poly.domain.tolist(),
                  "window": poly.window.tolist(), "degree": degree, "n_points": int(good.sum()),
                  "rmse": float(np.sqrt(sse/good.sum())), "r_squared": 1-sse/total if total > 0 else None,
                  "x_unit": self[x].unit, "y_unit": self[y].unit,
                  "coefficient_units": [f"({self[y].unit})/({self[x].unit})**{j}" for j in range(degree+1)]}
        result = json_value(result)
        if result["coefficients"] is None or any(v is None for v in result["coefficients"]):
            raise ValueError("Fit coefficients overflow; re-reference x or reduce degree.")
        fitted = np.full(len(self), np.nan)
        fitted[active & np.isfinite(xx)] = poly(xx[active & np.isfinite(xx)])
        self._put(output, fitted, self[y].unit, {"operation": "fit", "input": y, "x": x,
                  "records": records.json(), "fit": result})
        return result

    def running_slope(self, source, *, x="time", window, output, records=None, min_points=2):
        """Local linear regression over window samples each side, shortened at edges.

        Works on arbitrary x coordinates. NaNs and dropped original records split
        segments. Constant-x windows yield NaN. No fixed sample rate is assumed.
        """
        window = _integer(window, "window")
        min_points = _integer(min_points, "min_points", 2)
        if min_points > 2*window+1:
            raise ValueError("min_points cannot exceed 2*window+1.")
        xx, yy = self[x].values, self[source].values
        valid = self._selection(records) & np.isfinite(xx) & np.isfinite(yy)
        starts = np.flatnonzero(valid & np.r_[True, ~valid[:-1] | (np.diff(self.record_ids) != 1)])
        ends = np.flatnonzero(valid & np.r_[~valid[1:] | (np.diff(self.record_ids) != 1), True])+1
        result = np.full(len(self), np.nan)
        for a, b in zip(starts, ends):
            nseg = b-a
            for start in range(0, nseg, 2048):
                targets = np.arange(start, min(start+2048, nseg))
                left, right = np.maximum(0, targets-window), np.minimum(nseg, targets+window+1)
                first, last = int(left[0]), int(right[-1])
                mid = (first+last)//2
                tx, ty = xx[a+first:a+last]-xx[a+mid], yy[a+first:a+last]-yy[a+mid]
                sums = [np.r_[0., np.cumsum(v)] for v in (tx, ty, tx*tx, tx*ty)]
                sx, sy, sxx, sxy = [v[right-first]-v[left-first] for v in sums]
                count = right-left
                denominator = sxx-sx*sx/count
                # Scaling local sums avoids the large absolute-coordinate error.
                with np.errstate(divide="ignore", invalid="ignore"):
                    slopes = (sxy-sx*sy/count)/denominator
                keep = (count >= min_points) & (denominator > np.finfo(float).eps*np.maximum(sxx, 1e-300)*32)
                result[a+targets[keep]] = slopes[keep]
        return self._put(output, result, f"({self[source].unit})/({self[x].unit})",
                         {"operation": "running_slope", "input": source, "x": x,
                          "half_window_samples": window, "min_points": min_points,
                          "records": records.json() if records else None,
                          "algorithm": "centered sample-window OLS; shortened edge windows; finite contiguous segments"})

    def low_pass(self, source, *, time="time", cutoff_Hz, output=None, records=None,
                 order=1, fs_Hz=None, uniform_rtol=0.001):
        """Zero-phase SOS Butterworth filtering on one uniformly sampled interval.

        Outside the interval values are unchanged. Reject gaps, NaNs, mixed
        sampling rates and insufficient padding length rather than bridging them.
        """
        output = source if output is None else output
        from scipy.signal import butter, sosfiltfilt
        order = _integer(order, "order")
        if not np.isfinite(uniform_rtol) or not 0 <= uniform_rtol <= 0.1:
            raise ValueError("uniform_rtol must be between 0 and 0.1.")
        active = self._selection(records)
        pos = np.flatnonzero(active)
        t = self[time].values[pos]*factor(self[time].unit, "s")
        values = self[source].values[pos]
        dt = np.diff(t)
        if len(t) < 3 or not np.isfinite(t).all() or not np.isfinite(values).all() or np.any(dt <= 0):
            raise ValueError("Filter interval needs finite values and strictly increasing finite time, with >=3 samples.")
        if np.any(np.diff(self.record_ids[pos]) != 1) or not np.allclose(dt, np.median(dt), rtol=uniform_rtol, atol=0):
            raise ValueError("Filter interval must be contiguous and uniformly sampled. Select one acquisition-rate segment.")
        measured_fs = 1/float(np.median(dt))
        fs = measured_fs if fs_Hz is None else float(fs_Hz)
        if not np.isfinite(fs) or fs <= 0 or not np.isclose(fs, measured_fs, rtol=uniform_rtol, atol=0):
            raise ValueError("fs_Hz must agree with the selected interval's actual sample rate.")
        if not np.isfinite(cutoff_Hz) or not 0 < cutoff_Hz < fs/2:
            raise ValueError("cutoff_Hz must be positive and below the Nyquist frequency fs/2.")
        sos = butter(order, cutoff_Hz, fs=fs, output="sos")
        try:
            filtered = sosfiltfilt(sos, values)
        except ValueError as exc:
            raise ValueError("Filter interval is too short for forward/backward padding; select more samples or reduce order.") from exc
        y = self[source].values.copy()
        y[pos] = filtered
        return self._put(output, y, self[source].unit, {"operation": "low_pass", "input": source,
                         "time": time, "cutoff_Hz": float(cutoff_Hz), "fs_Hz": fs,
                         "order": order, "uniform_rtol": uniform_rtol,
                         "records": records.json() if records else None,
                         "algorithm": "Butterworth SOS forward/backward; zero phase, effective magnitude response squared; outside interval unchanged",
                         "note": "Padding and interval joins may have edge transients; inspect boundaries."})
