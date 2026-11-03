"""Mutable working channels with immutable inputs and an append-only revision log."""
import json
import numpy as np
import pytest
from nptdms import TdmsWriter, ChannelObject
from xlookpy import Channel, Experiment, Registry, run
from xlookpy.io import write_dat, read_state


def test_inplace_transform_chain_preserves_raw_and_each_input_revision(tmp_path):
    original = np.array([2., 3., 4., 5., 6.])
    e = Experiment({"ADC/d": Channel(original, "um", {"role": "stored_tdms", "properties": {"Slope": 2., "Intercept": 1.}})})
    e.convert_acquisition("ADC/d", unit="um", output="displacement")
    e.convert("displacement", unit="mm")
    e.zero_at("displacement", record=1)
    e.shift("displacement", value=.001)
    e.offset("displacement", records=e.records(2, 3))
    assert e.channels == ("ADC/d", "displacement")
    np.testing.assert_array_equal(e["ADC/d"].values, original)
    np.testing.assert_allclose(e["displacement"].values, [.001, .001, .003, .003, .005])
    assert [op["revision"] for op in e.history] == [1, 2, 3, 4, 5]
    for op in e.history[1:]:
        assert op["replaces_revision"] == op["revision"]-1
        assert op["input_revisions"] == {"displacement": op["revision"]-1}
    json.dumps(e.history, allow_nan=False)
    path = tmp_path/"reduced.dat"
    write_dat(e, path, None)
    assert path.read_text().splitlines()[0] == "record_id\tdisplacement"
    assert "ADC/d" in e.plot_columns


def test_overwrite_invalidates_transitive_descendants_but_keeps_all_history():
    e = Experiment({"raw": Channel(np.arange(10.), "mm", {})})
    e.convert("raw", unit="mm", output="a")
    e.shift("a", value=1, output="b")
    e.shift("b", value=2, output="c")
    e.convert("raw", unit="mm", output="independent")
    prior = json.dumps(e.history, sort_keys=True)
    e.shift("a", value=3)
    assert e.channels == ("raw", "a", "independent")
    assert json.dumps(e.history[:-1], sort_keys=True) == prior
    assert set(e.history[-1]["invalidated_channels"]) == {"b", "c"}
    e.shift("a", value=1, output="b")
    assert e["b"].metadata["input_revisions"] == {"a": 5}
    assert len(e.history) == 6


def test_failed_overwrite_is_atomic_and_raw_never_overwritten():
    e = Experiment({"raw": Channel(np.arange(10.), "mm", {})})
    e.convert("raw", unit="mm", output="d")
    e.shift("d", value=1, output="other")
    previous = e["d"]
    for f in [lambda: e.shift("raw", value=1),
              lambda: e._put("d", [1], "mm", {"operation": "test", "input": "d"}),
              lambda: e.convert("d", unit="kN")]:
        with pytest.raises(ValueError):
            f()
    assert e["d"] is previous and "other" in e.channels and len(e.history) == 2


def test_correct_filter_mask_in_place_and_keep_raw_unchanged():
    t=np.arange(200)/100
    force=np.linspace(0, 10, len(t))
    e=Experiment({"raw_d": Channel(.02*t+force/100, "mm", {}),
                  "time": Channel(t, "s", {}), "force": Channel(force, "kN", {})})
    e.convert("raw_d", unit="mm", output="d")
    e.elastic_correct("d", load="force", stiffness=100, stiffness_unit="kN/mm", reference_record=0)
    np.testing.assert_allclose(e["d"].values, .02*t, atol=1e-14)
    e.low_pass("d", cutoff_Hz=3, order=2)
    assert e["d"].unit == "mm"
    e.mask("d", records=e.records(20, 22), reason="dropout")
    assert np.isnan(e["d"].values[20:23]).all()
    assert len(e.history) == 4


def test_profile_is_compact_and_inplace_reduction_replays_exactly(tmp_path):
    n=100
    columns={"Time": 100+np.arange(n)*.01, "Vertical Load": np.arange(n)*.2,
             "Horizontal Load": np.arange(n)*.3, "Vertical Displacement": np.arange(n)*100.,
             "Horizontal Displacement": -np.arange(n)*50., "AUX 6": np.arange(n)*.05}
    with TdmsWriter(tmp_path/"raw.tdms") as writer:
        writer.write_segment([ChannelObject("ADC", name, v, properties={"Slope":1., "Intercept":0.}) for name,v in columns.items()])
    script=tmp_path/"reduction.py"
    script.write_text('''# %% Load
exp = load("raw.tdms", profile="BRAVA")
# %% Process working values
exp.zero_at("vertical_displacement_mm", record=10)
exp.offset("vertical_displacement_mm", records=exp.records(20, 22))
exp.zero_at("vertical_load", record=10)
exp.stress("vertical_load", area_mm2=2500., surfaces=2, output="shear_stress")
save(exp)
''')
    registry=Registry(tmp_path/"registry")
    m=run(script,registry=registry)
    e=read_state(tmp_path/m["outputs"]["state"], m)
    assert len(e.channels) == 12  # Six original ADC, five profile outputs, one stress.
    assert {"absolute_time", "vertical_displacement_um", "horizontal_displacement_um"}.isdisjoint(e.channels)
    assert all(not c.startswith("ADC/") for c in m["outputs"]["channels"])
    assert "ADC/AUX 6" in e.plot_columns
    np.testing.assert_array_equal(e["ADC/Vertical Displacement"].values, columns["Vertical Displacement"])
    assert len([op for op in m["operations"] if op.get("output") == "vertical_displacement_mm"]) == 4
    assert e["vertical_displacement_mm"].values[10] == 0
    replay=run(script,registry=registry,replay_manifest=tmp_path/"experiment.json")
    assert m["outputs"]["dat_sha256"] == replay["outputs"]["dat_sha256"]


def test_explicit_outputs_and_raw_exports_remain_available(tmp_path):
    e=Experiment({"raw":Channel([1.,2.,3.],"mm",{})})
    e.convert("raw",unit="mm",output="one")
    e.zero_at("one",record=1,output="comparison")
    assert e.channels == ("raw","one","comparison")
    assert e.export_columns == ("one","comparison")
    path=tmp_path/"chosen.dat"
    write_dat(e,path,["raw","comparison"])
    assert path.read_text().splitlines()[0] == "record_id\traw\tcomparison"
