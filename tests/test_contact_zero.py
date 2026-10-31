import json
from pathlib import Path
import numpy as np
import pytest
from nptdms import TdmsWriter, ChannelObject
from xlookpy import Experiment, Channel, Registry, run
from xlookpy.io import read_state
from test_engine import model


def test_contact_sample_is_exact_zero_and_only_earlier_samples_are_forced_zero():
    source = np.array([np.nan, 8., 10., 12., 9., np.nan])
    exp = Experiment({"force": Channel(source, "kN", {})})
    exp.zero_at("force", record=2, output="zeroed")
    np.testing.assert_allclose(exp["zeroed"].values, [0, 0, 0, 2, -1, np.nan], equal_nan=True)
    np.testing.assert_allclose(exp["force"].values, source, equal_nan=True)
    assert exp.history[-1]["contact_record"] == 2
    assert exp.history[-1]["offset"] == 10
    assert exp.history[-1]["before_contact"] == "forced_zero"


def test_zero_at_uses_original_ids_after_slicing_and_independent_ram_contacts():
    exp = Experiment({"v": Channel(np.arange(10)*2+3, "kN", {}),
                      "h": Channel(np.arange(10)*3+4, "kN", {})})
    part = exp.slice(exp.records(4, 9))
    part.zero_at("v", record=np.int64(6), output="shear")
    part.zero_at("h", record=5, output="normal")
    np.testing.assert_allclose(part["shear"].values, [0, 0, 0, 2, 4, 6])
    np.testing.assert_allclose(part["normal"].values, [0, 0, 3, 6, 9, 12])
    for bad in [True, 6., (6, 6), None]:
        with pytest.raises(ValueError, match="integer"):
            part.zero_at("v", record=bad, output="bad")
    with pytest.raises(ValueError, match="not present"):
        part.zero_at("v", record=3, output="bad")
    invalid = Experiment({"x": Channel([1, np.nan, 2], "mm", {})})
    with pytest.raises(ValueError, match="invalid at contact"):
        invalid.zero_at("x", record=1, output="bad")


def test_template_inspection_then_picked_contacts_and_elastic_correction(tmp_path):
    project = tmp_path/"experiment"
    project.mkdir()
    template = Path(__file__).resolve().parents[1]/"examples/your_experiment/reduction.py"
    script = project/"reduction.py"
    script.write_text(template.read_text())
    n = 120
    vertical = np.r_[np.full(10, 3.), 3+.2*np.arange(n-10)]
    horizontal = np.r_[np.full(4, 6.), 6+.3*np.arange(n-4)]
    columns = {"Time": np.arange(n)*.01,
               "Vertical Load": vertical, "Horizontal Load": horizontal,
               "Vertical Displacement": np.arange(n)*100.,
               "Horizontal Displacement": -np.arange(n)*50.}
    with TdmsWriter(project/"eq_phys_demo.tdms") as writer:
        writer.write_segment([ChannelObject("ADC", name, values,
                              properties={"Slope": 1., "Intercept": 0.}) for name, values in columns.items()])
    first = run(script)
    assert first["config"]["mode"] == "contact_inspection_only"
    assert "friction" not in first["outputs"]["channels"]
    assert len(first["plots"]) == 2
    script.write_text(script.read_text().replace("VERTICAL_CONTACT_RECORD = None", "VERTICAL_CONTACT_RECORD = 10")
                      .replace("HORIZONTAL_CONTACT_RECORD = None", "HORIZONTAL_CONTACT_RECORD = 4"))
    result = run(script)
    exp = read_state(project/result["outputs"]["state"], result)
    np.testing.assert_allclose(exp["shear_force"].values[:11], 0)
    np.testing.assert_allclose(exp["normal_force"].values[:5], 0)
    np.testing.assert_allclose(exp["measured_relative"].values[:11], 0)
    np.testing.assert_allclose(exp["normal_displacement_mm"].values[:5], 0)
    assert exp["shear_force"].values[11] == pytest.approx(.2)
    assert exp["measured_relative"].values[11] == pytest.approx(.1)
    assert np.isnan(exp["slip_velocity"].values[:11]).all()
    assert result["config"]["vertical_contact_record"] == 10
    assert result["config"]["horizontal_contact_record"] == 4
    operations = [o for o in result["operations"] if o["operation"] == "zero_at"]
    assert len(operations) == 4
    calibration = tmp_path/"frame.json"
    calibration.write_text(json.dumps(model().record))
    registry = Registry(tmp_path/"registry")
    registry.import_file(calibration)
    script.write_text(script.read_text().replace("FRAME_CALIBRATION_ID = None", 'FRAME_CALIBRATION_ID = "test/frame/r1"'))
    corrected = run(script, registry=registry)
    exp = read_state(project/corrected["outputs"]["state"], corrected)
    np.testing.assert_allclose(exp["slip"].values[:11], 0)
    f = exp["shear_force"].values
    expected = exp["measured_relative"].values-(.002*f**2+.1*f)
    np.testing.assert_allclose(exp["slip"].values, expected, atol=1e-14)
    assert corrected["calibrations"]
