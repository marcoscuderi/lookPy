"""Regenerate deterministic teaching data and clearly labelled calibration examples."""
from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    t = np.r_[np.arange(0., 80., .01), np.arange(80., 100., .002), np.arange(100., 160.001, .01)]
    phase = np.mod(t, 8.)
    # Slow reload for 7.7 seconds, fast stress drop over the last .3 seconds.
    mu = np.where(phase < 7.7, .50 + .12*phase/7.7, .62 - .12*(phase-7.7)/.3)
    normal = np.full(len(t), 25.)
    shear = mu * 2 * normal
    rng = np.random.default_rng(42)
    slip = .002*t + .003*np.floor(t/8.) + .003*np.clip((phase-7.7)/.3, 0, 1)
    measured = slip + .003*shear + .000008*shear**2 + rng.normal(0, .00002, len(t))
    data = np.column_stack([t, shear/10, normal/10, measured])
    np.savetxt(ROOT/"examples/demo/raw.csv", data, delimiter=",", header="time,shear_voltage,normal_voltage,displacement_voltage", comments="", fmt="%.17g")
    for name, category, unit, model, parameters, bounds in [
        ("shear", "sensor", "kN", "linear", {"slope": 10., "intercept": 0.}, [-10., 10.]),
        ("normal", "sensor", "kN", "linear", {"slope": 10., "intercept": 0.}, [-10., 10.]),
        ("displacement", "sensor", "mm", "linear", {"slope": 1., "intercept": 0.}, [-10., 10.]),
        ("frame", "apparatus", "mm", "polynomial", {"coefficients": [.000008, .003, 0.]}, [0., 100.]),
    ]:
        record = {"schema_version": 1, "id": f"demo/{name}/2026-10-r1", "category": category,
                  "apparatus": "SYNTHETIC teaching apparatus", "sensor": name, "date": "2026-10-01",
                  "input_unit": "kN" if category == "apparatus" else "V", "output_unit": unit,
                  "model": model, "parameters": parameters, "valid_range": bounds,
                  "notes": "SYNTHETIC EXAMPLE ONLY. Do not use these values for laboratory data."}
        (ROOT/f"calibration_examples/{name}.json").write_text(json.dumps(record, indent=2)+"\n")


if __name__ == "__main__":
    main()
