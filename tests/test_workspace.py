"""Cell semantics, legacy conversion and reproducible top-level scripts."""
import json
from pathlib import Path
import numpy as np
import pytest
from xlookpy import run, Registry
from xlookpy.io import read_state
from xlookpy.workflow import using_session
from xlookpy.workspace import Workspace, cells, convert_legacy
from test_engine import prepare_demo


def script(tmp_path):
    (tmp_path/"raw.csv").write_text("time,d\n0,5\n1,6\n2,7\n3,8\n4,9\n")
    source = '''# %% Load
exp = load("raw.csv", units={"time": "s", "d": "mm"})
contact = 1
# %% Zero
exp.zero_at("d", record=contact, output="slip")
# %% Velocity
exp.running_slope("slip", x="time", window=1, output="v")
# %% Export
save(exp, channels=["time", "slip", "v"])
'''
    path = tmp_path/"reduction.py"
    path.write_text(source)
    return path, source


def test_parser_ignores_markers_inside_multiline_strings_and_indented_comments():
    source = 'title = """text\n# %% not a cell\n"""\n#%% Second\na = 1\nif True:\n    # %% not top level\n    pass\n'
    parsed = cells(source)
    assert len(parsed) == 2
    assert parsed[0].start == 0 and parsed[1].start == 3
    assert parsed[1].title == "Second"
    assert len(cells("# %% Incomplete\nx = (")) == 1


def test_sequential_cells_rerun_rebuild_and_stale_dependencies(tmp_path):
    path, source = script(tmp_path)
    w = Workspace(path, Registry(tmp_path/"registry"))
    with pytest.raises(ValueError, match="Earlier cells"):
        w.execute(source, 2)
    w.execute(source, 0)
    w.execute(source, 1)
    w.execute(source, 2)
    np.testing.assert_array_equal(w.namespace["exp"]["slip"].values, [0, 0, 1, 2, 3])
    w.execute(source, 1)  # Rebuild load+zero; no accumulated zeroing or stale velocity.
    assert "v" not in w.namespace["exp"].channels
    assert w.statuses == ["executed", "executed", "pending", "pending"]
    changed = source.replace("contact = 1", "contact = 2")
    w.update(changed)
    assert w.statuses[0] == "outdated"
    w.execute(changed, 1, through=True)
    np.testing.assert_array_equal(w.namespace["exp"]["slip"].values, [0, 0, 0, 1, 2])
    assert not (tmp_path/"experiment.json").exists()


def test_console_replaces_only_derived_channels_and_invalidates_dependents(tmp_path):
    path, source = script(tmp_path)
    w = Workspace(path, Registry(tmp_path/"registry"))
    w.execute(source, 2, through=True)
    e = w.namespace["exp"]
    w.session._allow_replace = True
    e.zero_at("d", record=2, output="slip")
    assert "v" not in e.channels
    np.testing.assert_array_equal(e["slip"].values, [0, 0, 0, 1, 2])
    with pytest.raises(ValueError, match="already exists"):
        e.zero_at("d", record=1, output="d")
    with pytest.raises(ValueError, match="different output"):
        e.zero_at("slip", record=2, output="slip")
    w.session._allow_replace = False
    w.dirty = True
    w.namespace["console_only"] = 10
    w.execute(source, 2)
    assert "console_only" not in w.namespace
    np.testing.assert_array_equal(w.namespace["exp"]["slip"].values, [0, 0, 1, 2, 3])


def test_failed_cell_marks_partial_state_and_rebuild_restores_it(tmp_path):
    path, source = script(tmp_path)
    w = Workspace(path, Registry(tmp_path/"registry"))
    broken = source.replace('# %% Velocity', 'raise RuntimeError("failure after put")\n# %% Velocity')
    w.execute(broken, 0)
    with pytest.raises(RuntimeError):
        w.execute(broken, 1)
    assert w.failed and w.statuses[1] == "failed"
    assert "slip" in w.namespace["exp"].channels  # Explicitly partial, not claimed rollback.
    w.execute(source, 2, through=True)
    assert not w.failed and "v" in w.namespace["exp"].channels


def test_run_all_excludes_console_edits_and_publishes_saved_source(tmp_path):
    path, source = script(tmp_path)
    w = Workspace(path, Registry(tmp_path/"registry"))
    w.execute(source, 2, through=True)
    w.session._allow_replace = True
    w.namespace["exp"].zero_at("d", record=3, output="slip")
    w.session._allow_replace = False
    w.dirty = True
    manifest = w.run_all(source)
    e = read_state(tmp_path/manifest["outputs"]["state"], manifest)
    np.testing.assert_array_equal(e["slip"].values, [0, 0, 1, 2, 3])
    assert not w.dirty and w.state()["published"]
    assert manifest["script"]["source"] == source
    original = (tmp_path/"experiment.json").read_bytes()
    with pytest.raises(ValueError, match="Save"):
        w.run_all(source+"\n# unsaved")
    assert (tmp_path/"experiment.json").read_bytes() == original
    manifest2 = run(path, registry=w.registry)
    assert manifest["outputs"]["dat_sha256"] == manifest2["outputs"]["dat_sha256"]


def test_converted_existing_demo_matches_legacy_export_and_replay(tmp_path):
    project, registry = prepare_demo(tmp_path)
    before = run(project/"reduction.py", registry=registry)
    source = (project/"reduction.py").read_text()
    converted = convert_legacy(source)
    assert "def reduce(" not in converted and "calibration(" in converted
    path = project/"reduction_cells.py"
    path.write_text(converted)
    after = run(path, registry=registry)
    assert after["outputs"]["dat_sha256"] == before["outputs"]["dat_sha256"]
    replay = run(path, registry=registry, replay_manifest=project/"experiment.json")
    assert replay["outputs"]["dat_sha256"] == after["outputs"]["dat_sha256"]


def test_conversion_preserves_inspection_early_return_comments_and_unicode():
    source = '''# initial\nCONTACT = None\ndef reduce(session):
    # %% Load
    label = "é"
    exp = session.load("raw.csv", units={"x":"mm"})
    if CONTACT is None:
        session.export(exp)
        return  # inspection
    # %% Analysis
    def nested():
        return 3
    print(nested())
'''
    converted = convert_legacy(source)
    assert 'exp = load("raw.csv"' in converted
    assert 'save(exp)' in converted and 'stop()  # inspection' in converted
    assert '    return 3' in converted
    assert [c.title for c in cells(converted)] == ["Setup", "Load", "Analysis"]
    with pytest.raises(ValueError, match="return value"):
        convert_legacy('def reduce(session):\n    return 3\n')


def test_stop_inspection_and_edited_contacts_restart_prefix(tmp_path):
    path, source = script(tmp_path)
    source = source.replace('# %% Zero', 'if contact is None:\n    save(exp)\n    stop()\n# %% Zero').replace('contact = 1', 'contact = None')
    path.write_text(source)
    w = Workspace(path, Registry(tmp_path/"registry"))
    w.execute(source, 3, through=True)
    assert w.halted and w.completed == 1
    manifest = w.run_all(source)
    assert len(manifest["channels"]) == 2
    fixed = source.replace('contact = None', 'contact = 1')
    w.execute(fixed, 2, through=True)
    assert not w.halted and "v" in w.namespace["exp"].channels


def test_ipython_hooks_share_namespace_report_trials_and_restore_on_replay(tmp_path):
    InteractiveShell = pytest.importorskip("IPython.core.interactiveshell").InteractiveShell
    from xlookpy.kernel_runtime import KernelRuntime, MIME
    shell = InteractiveShell()
    reports = []
    # Capture the exact messages that the real kernel publishes over IOPub.
    shell.display_pub.publish = lambda data, **kwargs: reports.append(data[MIME]) if MIME in data else None
    path, source = script(tmp_path)
    cache = tmp_path/"cache"
    cache.mkdir()
    runtime = KernelRuntime(path, tmp_path/"registry", cache, shell)
    try:
        runtime.dispatch("through", source, 2)
        assert "v" in shell.user_ns["exp"].channels
        shell.run_cell('exp.zero_at("d", record=2, output="slip")')
        assert reports[-1]["dirty"] and not reports[-1]["error"]
        assert "v" not in shell.user_ns["exp"].channels
        np.testing.assert_array_equal(shell.user_ns["exp"]["slip"].values, [0, 0, 0, 1, 2])
        runtime.dispatch("all", source)
        assert reports[-1]["published"] and not reports[-1]["dirty"]
        np.testing.assert_array_equal(shell.user_ns["exp"]["slip"].values, [0, 0, 1, 2, 3])
        saved = (tmp_path/"experiment.json").read_bytes()
        shell.run_cell('raise ValueError("trial failed")')
        assert reports[-1]["failed"]
        assert (tmp_path/"experiment.json").read_bytes() == saved
    finally:
        shell.events.unregister("pre_run_cell", runtime.before_console)
        shell.events.unregister("post_run_cell", runtime.after_console)


def test_brava_profile_maps_units_signs_and_records_full_definition(tmp_path):
    from nptdms import TdmsWriter, ChannelObject
    values = {"Time": np.arange(10)+100., "Vertical Load": np.arange(10)*.2,
              "Horizontal Load": np.arange(10)*.3, "Vertical Displacement": np.arange(10)*100.,
              "Horizontal Displacement": -np.arange(10)*50.}
    with TdmsWriter(tmp_path/"raw.tdms") as writer:
        writer.write_segment([ChannelObject("ADC", n, v, properties={"Slope": 1., "Intercept": 0.})
                              for n, v in values.items()])
    path = tmp_path/"reduction.py"
    path.write_text('# %% Load\nexp = load("raw.tdms", profile="BRAVA")\nsave(exp)\n')
    manifest = run(path)
    e = read_state(tmp_path/manifest["outputs"]["state"], manifest)
    np.testing.assert_allclose(e["time"].values, np.arange(10))
    np.testing.assert_allclose(e["vertical_displacement_mm"].values, np.arange(10)*.1)
    np.testing.assert_allclose(e["horizontal_displacement_mm"].values, np.arange(10)*.05)
    assert manifest["config"]["acquisition_profile"]["definition"]["horizontal_displacement_scale"] == -1
    assert len(manifest["config"]["acquisition_profile"]["sha256"]) == 64


def test_converted_real_template_preserves_contact_inspection_and_reduced_values(tmp_path):
    from nptdms import TdmsWriter, ChannelObject
    values = {"Time": np.arange(100)*.1, "Vertical Load": np.maximum(np.arange(100)-10, 0)*.2,
              "Horizontal Load": np.maximum(np.arange(100)-4, 0)*.3,
              "Vertical Displacement": np.arange(100)*100., "Horizontal Displacement": -np.arange(100)*50.}
    with TdmsWriter(tmp_path/"eq_phys_demo.tdms") as writer:
        writer.write_segment([ChannelObject("ADC", n, v, properties={"Slope": 1., "Intercept": 0.})
                              for n, v in values.items()])
    template = Path(__file__).resolve().parents[1]/"examples/your_experiment/reduction.py"
    path = tmp_path/"reduction.py"
    source = template.read_text()
    for text in [source, source.replace("VERTICAL_CONTACT_RECORD = None", "VERTICAL_CONTACT_RECORD = 10").replace("HORIZONTAL_CONTACT_RECORD = None", "HORIZONTAL_CONTACT_RECORD = 4")]:
        path.write_text(text)
        original = run(path)
        converted = tmp_path/"reduction_cells.py"
        converted.write_text(convert_legacy(text))
        result = run(converted)
        assert original["outputs"]["dat_sha256"] == result["outputs"]["dat_sha256"]
