import json
from pathlib import Path
import shutil
import numpy as np
import pytest
from xlookpy import Experiment, Channel, Calibration, Registry, run
from xlookpy.io import load_file

ROOT = Path(__file__).resolve().parents[1]


def model(category="apparatus", **changes):
    r = {"schema_version": 1, "id": "test/frame/r1", "category": category,
         "apparatus": "test", "sensor": "frame", "date": "2026-10-01",
         "input_unit": "kN" if category == "apparatus" else "V", "output_unit": "mm" if category == "apparatus" else "kN",
         "model": "polynomial", "parameters": {"coefficients": [.002, .1, 0.]},
         "valid_range": [0., 100.], "notes": "test"}
    r.update(changes)
    return Calibration(r)


def experiment(**columns):
    return Experiment({k: Channel(values, unit, {}) for k, (values, unit) in columns.items()})


def test_non_linear_elastic_correction_recovers_known_slip():
    f = np.r_[np.linspace(2, 80, 100), np.linspace(80, 5, 80)]
    true_slip = np.linspace(0, 2, len(f))
    cal = model()
    deformation, _ = cal.evaluate(f)
    exp = experiment(force=(f, "kN"), measured=(true_slip+deformation, "mm"))
    exp.correct_displacement("measured", force="force", using=cal,
                             reference_record=0, output="slip")
    np.testing.assert_allclose(exp["slip"].values, true_slip, atol=1e-14)
    # Opposite displacement coordinate needs + e(F).
    other = experiment(force=(f*1000, "N"), measured=(true_slip-deformation, "mm"))
    other.correct_displacement("measured", force="force", using=cal,
                               reference_record=0, sign=1, output="slip")
    np.testing.assert_allclose(other["slip"].values, true_slip, atol=1e-14)


def test_ranges_units_and_readonly_sources():
    cal = model()
    with pytest.raises(ValueError, match="outside"):
        cal.evaluate([-1, 5])
    a, n = cal.evaluate([-1, 5], outside="mask")
    assert np.isnan(a[0]) and n == 1
    a, n = cal.evaluate([-1, 5], outside="clip")
    assert a[0] == 0 and n == 1
    exp = experiment(force=([5, 6], "V"), measured=([1, 2], "mm"))
    with pytest.raises(ValueError, match="Cannot convert"):
        exp.correct_displacement("measured", force="force", using=cal, reference_record=0, output="slip")
    with pytest.raises(ValueError):
        exp["force"].values[0] = 10
    with pytest.raises(ValueError, match="positive compliance"):
        model(parameters={"coefficients": [-1, 0]})


def test_stress_friction_invalid_intervals_and_record_lineage():
    exp = experiment(shear=([30, 30, 30, 30, 30], "kN"), normal=([25, 0, 25, 25, 25], "kN"))
    exp.stress("shear", area_mm2=2500., surfaces=2, output="tau")
    exp.stress("normal", area_mm2=2500., output="sigma")
    exp.friction("tau", "sigma", records=exp.records(0, 3))
    np.testing.assert_allclose(exp["friction"].values, [.6, np.nan, .6, .6, np.nan], equal_nan=True)
    reduced = exp.slice(exp.records(2, 4))
    np.testing.assert_array_equal(reduced.record_ids, [2, 3, 4])
    reduced.zero("shear", reference=reduced.records(3, 4), output="zeroed")
    with pytest.raises(ValueError, match="endpoints"):
        reduced.records(0, 1)
    with pytest.raises(ValueError, match="already exists"):
        exp.zero("shear", reference=exp.records(0, 0), output="shear")


def test_derivative_irregular_times_agrees_with_direct_regression_and_masks_gaps():
    rng = np.random.default_rng(7)
    t = np.cumsum(rng.uniform(.006, .013, 2000))
    y = .2*t + rng.normal(0, .004, len(t))
    y[500:550] = np.nan
    exp = experiment(time=(t, "s"), displacement=(y, "mm"))
    exp.derivative("displacement", window_s=.3, min_points=5, max_gap_s=.05, output="v")
    v = exp["v"].values
    assert np.isnan(v[500:550]).all()
    assert np.isnan(v[0]) and np.isnan(v[-1])
    for i in [50, 250, 800, 1500]:
        keep = (abs(t-t[i]) <= .15) & np.isfinite(y)
        expected = np.polyfit(t[keep]-t[i], y[keep], 1)[0]
        assert v[i] == pytest.approx(expected, abs=1e-8)
    assert np.nanstd(v-.2) < .03


def test_derivative_does_not_bridge_dropped_records_or_time_gaps():
    t = np.r_[np.arange(0, 1, .01), np.arange(3, 4, .01)]
    exp = experiment(time=(t, "s"), displacement=(3*t, "mm"))
    exp.derivative("displacement", window_s=.2, max_gap_s=.03, output="v")
    assert np.isnan(exp["v"].values[99:101]).all()
    np.testing.assert_allclose(exp["v"].values[np.isfinite(exp["v"].values)], 3, atol=1e-8)


def test_derivative_is_stable_for_long_dense_records():
    rng = np.random.default_rng(99)
    t = 20000 + np.arange(160000)*.001
    y = 50 + .002*(t-t[0]) + rng.normal(0, .00001, len(t))
    exp = experiment(time=(t, "s"), displacement=(y, "mm"))
    exp.derivative("displacement", window_s=.1, output="v")
    for i in [500, 79001, 158500]:
        keep = abs(t-t[i]) <= .05
        direct = np.polyfit(t[keep]-t[i], y[keep]-y[i], 1)[0]
        assert exp["v"].values[i] == pytest.approx(direct, abs=1e-9)


def test_registry_revisions_are_immutable(tmp_path):
    registry = Registry(tmp_path/"central")
    source = tmp_path/"cal.json"
    source.write_text(json.dumps(model().record))
    c = registry.import_file(source)
    assert registry.import_file(source).fingerprint == c.fingerprint
    changed = c.record
    changed["parameters"]["coefficients"][0] = .004
    source.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="new id"):
        registry.import_file(source)
    changed["id"] = "test/frame/r2"
    source.write_text(json.dumps(changed))
    registry.import_file(source)
    assert len(registry.list()) == 2
    with pytest.raises(ValueError):
        registry.get("../escape")


def test_acquisition_conversion_is_explicit_and_not_repeatable():
    exp = Experiment({"stored": Channel([1, 2], "dimensionless", {
        "role": "stored_tdms", "properties": {"Slope": 2, "Intercept": 3}})})
    exp.convert_acquisition("stored", unit="kN", output="force")
    np.testing.assert_array_equal(exp["force"].values, [5, 7])
    with pytest.raises(ValueError, match="original stored"):
        exp.convert_acquisition("force", unit="kN", output="again")
    exp.convert("force", unit="N", output="newtons")
    with pytest.raises(ValueError, match="already calibrated"):
        exp.calibrate("newtons", using=model("sensor"), output="twice")


def prepare_demo(tmp_path):
    project = tmp_path/"experiment"
    shutil.copytree(ROOT/"examples/demo", project, ignore=shutil.ignore_patterns("results", "experiment.json"))
    registry = Registry(tmp_path/"central")
    for source in (ROOT/"calibration_examples").glob("*.json"):
        registry.import_file(source)
    return project, registry


def test_fresh_runs_replay_without_central_registry_and_failed_run_retains_manifest(tmp_path):
    project, registry = prepare_demo(tmp_path)
    first = run(project/"reduction.py", registry=registry)
    manifest_before = (project/"experiment.json").read_bytes()
    second = run(project/"reduction.py", registry=registry)
    assert first["outputs"]["dat_sha256"] == second["outputs"]["dat_sha256"]
    assert first["calibrations"] and first["script"]["source"]
    shutil.rmtree(registry.root)
    replay = run(project/"reduction.py", registry=registry, replay_manifest=project/"experiment.json")
    assert replay["outputs"]["dat_sha256"] == first["outputs"]["dat_sha256"]
    manifest_before = (project/"experiment.json").read_bytes()
    script = project/"reduction.py"
    script.write_text(script.read_text()+"\nraise RuntimeError('deliberate failure')\n")
    with pytest.raises(RuntimeError, match="deliberate"):
        run(script, registry=registry)
    assert (project/"experiment.json").read_bytes() == manifest_before
    with pytest.raises(ValueError, match="script differs"):
        run(script, registry=registry, replay_manifest=project/"experiment.json")


def test_central_revision_tampering_is_detected(tmp_path):
    project, registry = prepare_demo(tmp_path)
    run(project/"reduction.py", registry=registry)
    path = registry.root/"demo/shear/2026-10-r1.json"
    content = json.loads(path.read_text())
    content["parameters"]["slope"] *= 1.01
    path.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="changed under the same ID"):
        run(project/"reduction.py", registry=registry)


def test_csv_missing_units_and_duplicate_names_are_rejected(tmp_path):
    path = tmp_path/"raw.csv"
    path.write_text("time,x\n0,1\n1,2\n")
    with pytest.raises(ValueError, match="Specify units"):
        load_file(path)
    path.write_text("time,time\n0,1\n1,2\n")
    with pytest.raises(ValueError, match="unique"):
        load_file(path, units={"time": "s"})
