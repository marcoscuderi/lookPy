"""Scientific and I/O regression checks for the rawPy workflow port."""
import importlib.util
import json
from pathlib import Path
import struct
import numpy as np
import pytest
from xlookpy import Experiment, Channel, Records, run, Registry
from xlookpy.io import load_file, write_dat, read_state

ROOT = Path(__file__).resolve().parents[1]


def exp(**columns):
    return Experiment({k: Channel(v, u, {}) for k, (v, u) in columns.items()})


def test_offset_removes_reset_and_preserves_source_and_original_ids():
    e = exp(d=([0, 1, 2, 10, 11, 12], "mm")).slice(Records(1, 5))
    e.offset("d", records=e.records(2, 4), output="repaired")
    np.testing.assert_array_equal(e["repaired"].values, [1, 2, 2, 2, 3])
    np.testing.assert_array_equal(e["d"].values, [1, 2, 10, 11, 12])
    assert e.history[-1]["removed_change"] == 9
    e.shift("repaired", value=1000, unit="micrometer", records=e.records(3, 5), output="shifted")
    np.testing.assert_array_equal(e["shifted"].values, [1, 2, 3, 3, 4])


def test_constant_stiffness_force_and_stress_forms_recover_same_slip():
    f = np.r_[np.linspace(1, 90, 100), np.linspace(90, 2, 100)]
    slip = np.linspace(0, 1, len(f))
    e = exp(f=(f, "kN"), tau=(f/5, "MPa"), d=(5+slip+f/400, "mm"))
    e.elastic_correct("d", load="f", stiffness=400, stiffness_unit="kN/mm", reference_record=0, output="s1")
    e.elastic_correct("d", load="tau", stiffness=80, stiffness_unit="MPa/mm", reference_record=0, output="s2")
    np.testing.assert_allclose(e["s1"].values, slip, atol=1e-14)
    np.testing.assert_allclose(e["s2"].values, slip, atol=1e-14)
    with pytest.raises(ValueError, match="Cannot convert"):
        e.elastic_correct("d", load="f", stiffness=400, stiffness_unit="MPa/mm", reference_record=0, output="bad")


def test_thickness_and_strain_with_mixed_length_units_and_reference():
    e = exp(u=([0, .02, .04, .06], "mm"), slip=([0, 100, 200, 300], "micrometer"))
    e.layer_thickness("u", reference_record=1, thickness=1, layers=2, closure_sign=-1, output="h")
    np.testing.assert_allclose(e["h"].values, [1.01, 1, .99, .98])
    e.shear_strain("slip", thickness="h", reference_record=1)
    np.testing.assert_allclose(e["shear_strain"].values, [np.nan, 0, .1/.995, .1/.995+.1/.985], equal_nan=True)
    with pytest.raises(ValueError, match="nonpositive"):
        e.layer_thickness("u", reference_record=0, thickness=.001, layers=2, output="bad")


def test_strain_does_not_bridge_missing_data():
    e = exp(slip=([0, 1, np.nan, 3, 4], "mm"), h=([1]*5, "mm"))
    e.shear_strain("slip", thickness="h", reference_record=0)
    np.testing.assert_allclose(e["shear_strain"].values, [0, 1, np.nan, np.nan, np.nan], equal_nan=True)


def test_geometrical_thinning_preserves_legacy_lagged_recurrence():
    d, h = np.array([0., .1, .3, .6]), np.array([1., .9, .8, .7])
    e = exp(d=(d, "mm"), h=(h*1000, "micrometer"))
    e.geometrical_thinning("d", thickness="h", block_length=50, output="rgt")
    # Explicit legacy rawPy result, not an independently proposed physical model.
    np.testing.assert_allclose(e["rgt"].values, [1., 1.001, .9028, .8052])
    e.geometrical_thinning("d", thickness="h", block_length=50, reference_record=1, output="later")
    np.testing.assert_allclose(e["later"].values, [np.nan, .9, .9018, .8042], equal_nan=True)
    with pytest.raises(ValueError, match="Available model"):
        e.geometrical_thinning("d", thickness="h", block_length=50, output="bad", model="unknown")


@pytest.mark.parametrize("degree", [1, 4])
def test_polynomial_fit_has_ascending_coefficients_and_serializable_diagnostics(degree):
    x = np.linspace(-2, 2, 101)
    coefs = np.arange(1, degree+2, dtype=float)
    y = np.polynomial.polynomial.polyval(x, coefs)
    y[50] = np.nan
    e = exp(x=(x, "mm"), y=(y, "MPa"))
    result = e.fit("x", "y", records=e.records(10, 90), degree=degree, output="fit")
    np.testing.assert_allclose(result["coefficients"], coefs, atol=1e-11)
    assert result["n_points"] == 80 and result["r_squared"] == pytest.approx(1)
    assert np.isnan(e["fit"].values[:10]).all()
    assert np.isfinite(e["fit"].values[50])
    json.dumps(e.history, allow_nan=False)


def test_fit_constant_output_and_degenerate_input():
    e = exp(x=([0, 1, 2, 3], "s"), y=([4]*4, "mm"), repeated=([1]*4, "s"))
    result = e.fit("x", "y", records=e.records(0, 3), degree=0, output="constant")
    assert result["r_squared"] is None and result["coefficients"] == [4]
    with pytest.raises(ValueError, match="distinct"):
        e.fit("repeated", "y", records=e.records(0, 3), output="bad")


def test_running_slope_matches_direct_local_fits_on_long_irregular_coordinates():
    rng = np.random.default_rng(8)
    x = 20000+np.cumsum(rng.uniform(.0008, .0012, 10000))
    y = 50+.002*(x-x[0])+rng.normal(0, .00001, len(x))
    e = exp(t=(x, "s"), d=(y, "mm"))
    e.running_slope("d", x="t", window=20, output="v")
    for i in [0, 1, 100, 2047, 6000, 9999]:
        a, b = max(0, i-20), min(len(x), i+21)
        direct = np.polyfit(x[a:b]-x[i], y[a:b]-y[i], 1)[0]
        assert e["v"].values[i] == pytest.approx(direct, abs=1e-9)


def test_running_slope_gaps_constant_x_and_short_segments():
    e = exp(x=(np.arange(10), "s"), y=([0, 2, 4, np.nan, 8, 10, 12, 14, 16, 18], "mm"))
    e.running_slope("y", x="x", window=100, output="v")
    np.testing.assert_allclose(e["v"].values, [2, 2, 2, np.nan, 2, 2, 2, 2, 2, 2], equal_nan=True)
    c = exp(x=([1]*5, "s"), y=(np.arange(5), "mm"))
    c.running_slope("y", x="x", window=2, output="v")
    assert np.isnan(c["v"].values).all()
    with pytest.raises(ValueError, match="integer"):
        c.running_slope("y", x="x", window=True, output="bad")


def test_filter_suppresses_high_frequency_preserves_low_frequency_and_outside_interval():
    t = np.arange(4000)/100
    low, high = np.sin(2*np.pi*.5*t), .5*np.sin(2*np.pi*20*t)
    e = exp(time=(t, "s"), y=(low+high, "mm"))
    e.low_pass("y", cutoff_Hz=2, order=4, records=e.records(500, 3500), output="filtered")
    filtered = e["filtered"].values
    np.testing.assert_array_equal(filtered[:500], (low+high)[:500])
    np.testing.assert_array_equal(filtered[3501:], (low+high)[3501:])
    assert np.std(filtered[800:3200]-low[800:3200]) < .003
    assert abs(filtered[-1]-(low+high)[-1]) < 1e-14


def test_filter_whole_signal_includes_last_sample_and_rejects_mixed_rates():
    t = np.arange(100)/10
    e = exp(time=(t, "s"), y=(np.sin(t)+.5*(-1.)**np.arange(100), "mm"))
    e.low_pass("y", cutoff_Hz=1, output="f")
    assert e.history[-1]["records"] is None
    # Endpoint is processed too (not silently excluded by a -1 slice).
    from scipy.signal import butter, sosfiltfilt
    np.testing.assert_allclose(e["f"].values, sosfiltfilt(butter(1, 1, fs=10, output="sos"), e["y"].values))
    mixed = exp(time=(np.r_[np.arange(10), 10+np.arange(20)*.1], "s"), y=(np.arange(30), "mm"))
    with pytest.raises(ValueError, match="uniformly"):
        mixed.low_pass("y", cutoff_Hz=.1, output="bad")
    with pytest.raises(ValueError, match="sample rate"):
        e.low_pass("y", cutoff_Hz=1, fs_Hz=20, output="bad")
    with pytest.raises(ValueError, match="Nyquist"):
        e.low_pass("y", cutoff_Hz=10, output="bad")
    with pytest.raises(ValueError, match="too short"):
        e.low_pass("y", cutoff_Hz=1, records=e.records(0, 3), order=4, output="bad")


def test_text_export_roundtrip_restores_nonzero_original_ids_and_units(tmp_path):
    e = exp(time=([0, 1, 2, 3], "s"), slip=([1, 2, 3, 4], "mm")).slice(Records(1, 3))
    path = tmp_path/"reduced.dat"
    write_dat(e, path, ["time", "slip"])
    loaded = load_file(path)
    np.testing.assert_array_equal(loaded.record_ids, [1, 2, 3])
    np.testing.assert_array_equal(loaded["slip"].values, [2, 3, 4])
    assert loaded["slip"].unit == "mm"
    legacy = tmp_path/"brava_no_extension"
    legacy.write_text("Time\tRecord\tmu\ns\tna\tna\n0\t1\t.6\n1\t2\t.7\n")
    assert load_file(legacy)["mu"].unit == "dimensionless"


def binary_file(path, endian="little"):
    content = struct.pack(">20s4i", b"test", 3, 2, 0, 0)
    for name, unit, n in [(b"Time", b"s", 3), (b"load", b"kN", 2)]+[(b"no_val", b"na", 0)]*30:
        content += struct.pack(">13s13si50si", name, unit, 0, b"", n)
    content += np.array([0, 1, 2, 4, 5], dtype="<f8" if endian == "little" else ">f8").tobytes()
    path.write_bytes(content)


@pytest.mark.parametrize("endian", ["little", "big"])
def test_legacy_binary_header_endianness_short_channels_and_truncation(tmp_path, endian):
    path = tmp_path/"old.bin"
    binary_file(path, endian)
    e = load_file(path, dataendianness=endian)
    np.testing.assert_array_equal(e["Time"].values, [0, 1, 2])
    np.testing.assert_allclose(e["load"].values, [4, 5, np.nan], equal_nan=True)
    assert e["load"].unit == "kN"
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError, match="payload length"):
        load_file(path)


def test_mock_runs_repeatably_exports_reimports_and_replays(tmp_path):
    spec = importlib.util.spec_from_file_location("setup_mock", ROOT/"tools/setup_rawpy_mock.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    project = setup.create(tmp_path/"mock")
    registry = Registry(tmp_path/"registry")
    first = run(project/"reduction.py", registry=registry)
    second = run(project/"reduction.py", registry=registry)
    assert first["outputs"]["dat_sha256"] == second["outputs"]["dat_sha256"]
    assert len(second["channels"]) == 27
    assert second["software"]["scipy"]
    replay = run(project/"reduction.py", registry=registry, replay_manifest=project/"experiment.json")
    assert replay["outputs"]["dat_sha256"] == second["outputs"]["dat_sha256"]
    state = read_state(project/replay["outputs"]["state"], replay)
    np.testing.assert_array_equal(state["normal_force"].values[:21], np.zeros(21))
    assert state["layer_thickness"].values[200] == pytest.approx(.8)
    assert state["slip"].values[80] == 0
    loaded = load_file(project/replay["outputs"]["dat"])
    np.testing.assert_array_equal(loaded.record_ids, state.record_ids)
    np.testing.assert_allclose(loaded["slip"].values, state["slip"].values)
    with pytest.raises(FileExistsError):
        setup.create(project)
    previous = (project/"experiment.json").read_bytes()
    script = project/"reduction.py"
    script.write_text(script.read_text().replace('cutoff_Hz=2.', 'cutoff_Hz=200.'))
    with pytest.raises(ValueError, match="Nyquist"):
        run(script, registry=registry)
    assert (project/"experiment.json").read_bytes() == previous
