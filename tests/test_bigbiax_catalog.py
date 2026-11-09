"""Synthetic calibrations only; no laboratory coefficients are distributed."""
import json
from pathlib import Path
import numpy as np
import pytest
from nptdms import ChannelObject, TdmsWriter
from xlookpy import Catalog, Registry, run
from xlookpy.cli import main


def record(identifier='BigBiax/frame/vertical/test/r1', **changes):
    data = dict(schema_version=1, id=identifier, category='apparatus', apparatus='BigBiax',
                sensor='vertical frame', date='2026-11-04', input_unit='kN', output_unit='um',
                model='polynomial', parameters={'coefficients': [0.2, 2., 0.]},
                valid_range=[0., 100.], notes='SYNTHETIC test coefficients',
                purpose='elastic', configuration='test fixture', source='synthetic test')
    data.update(changes)
    return data


def test_catalog_history_validation_and_transaction(tmp_path):
    cat = Catalog(tmp_path/'BigBiax.json')
    cat.initialize()
    assert not cat.list()
    r = record()
    cat.add(r)
    before = cat.path.read_bytes()
    cat.add(r)
    assert cat.path.read_bytes() == before
    with pytest.raises(ValueError, match='new revision'):
        cat.add(record(parameters={'coefficients': [0.3, 2., 0.]}))
    with pytest.raises(ValueError, match='gain'):
        cat.add(record('BigBiax/aux/test/r1', category='sensor', purpose='auxiliary'))
    with pytest.raises(ValueError, match='positive compliance'):
        cat.add(record('BigBiax/frame/test/r2', parameters={'coefficients': [-1., 0.]}))
    assert cat.path.read_bytes() == before
    second = record('BigBiax/frame/vertical/test/r2')
    cat.add(second)
    cat.suggest('vertical_frame', second['id'])
    assert cat.read()['suggested_defaults']['vertical_frame'] == second['id']
    assert cat.get(r['id']).record == r
    with pytest.raises(ValueError):
        cat.suggest('horizontal_frame', 'missing')
    lock = cat.path.with_name(cat.path.name+'.lock')
    lock.touch()
    try:
        with pytest.raises(ValueError, match='locked'):
            cat.add(record('BigBiax/frame/vertical/test/r3'))
    finally:
        lock.unlink()
    assert len(cat.list()) == 2
    assert Registry(cat.path).get(r['id']).record == r
    assert Registry(tmp_path).get(r['id']).record == r
    assert len(Registry(tmp_path).list()) == 2


def test_catalog_cli(tmp_path, capsys, monkeypatch):
    path = str(tmp_path/'BigBiax.json')
    def command(*args):
        return main(['catalog', *args, '--file', path])
    assert command('init') == 0
    source = tmp_path/'record.json'
    source.write_text(json.dumps(record()))
    assert command('import', str(source)) == 0
    assert command('list') == 0
    assert command('show', record()['id']) == 0
    assert command('curve', record()['id'], '--points', '3') == 0
    assert '100\t2200' in capsys.readouterr().out
    assert command('suggest', 'vertical_frame', record()['id']) == 0
    assert command('curve', record()['id'], '--points', '1') == 1
    before = Path(path).read_bytes()
    answers = iter(['elastic', 'BigBiax/frame/test/r9', 'frame', 'test', '', 'synthetic', '', '', '', '1 0', '0', '10', 'test', 'n'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    assert command('add') == 0
    assert Path(path).read_bytes() == before


def write_tdms(path, n=101):
    f = np.linspace(10., 90., n)
    slip = np.linspace(0., 50., n)
    deformation = .2*f*f+2*f
    values = {'Time': np.linspace(20., 30., n), 'Vertical Load': f,
              'Horizontal Load': f/2, 'Vertical Displacement': deformation+slip,
              'Horizontal Displacement': np.linspace(100., 200., n)}
    with TdmsWriter(path) as writer:
        writer.write_segment([ChannelObject('ADC', name, (v-3.)/2.,
                              properties={'Slope': 2., 'Intercept': 3.})
                              for name, v in values.items()] +
                             [ChannelObject('ADC', 'AUX 6', np.linspace(0., 1., n))])
    return slip, values


def test_bigbiax_tdms_nonlinear_micron_reduction_and_replay(tmp_path):
    cat = Catalog(tmp_path/'central'/'BigBiax.json')
    cat.initialize()
    cat.add(record())
    aux = record('BigBiax/aux/P01/low/r1', category='sensor', purpose='auxiliary',
                 gain='low', sensor='P01', input_unit='V', output_unit='MPa',
                 model='linear', parameters={'slope': 10., 'intercept': 0.}, valid_range=[0., 1.])
    cat.add(aux)
    slip, values = write_tdms(tmp_path/'raw.tdms')
    script = tmp_path/'reduction.py'
    script.write_text('''from xlookpy import load, calibration, save
exp = load('raw.tdms', profile='BigBiax', units={'ADC/AUX 6': 'V'})
exp.calibrate('ADC/AUX 6', using=calibration('BigBiax/aux/P01/low/r1'), output='pressure')
exp.correct_displacement('vertical_displacement_um', force='vertical_load',
    using=calibration('BigBiax/frame/vertical/test/r1'), reference_record=0)
save(exp)
''')
    run(script, registry=cat.path)
    manifest = json.loads((tmp_path/'experiment.json').read_text())
    from xlookpy.io import read_state
    # Manifest declares the published cache filename.
    state_file = tmp_path/manifest['outputs']['state']
    exp = read_state(state_file, manifest)
    assert exp['vertical_displacement_um'].unit == 'um'
    np.testing.assert_allclose(exp['vertical_displacement_um'].values, slip, atol=1e-10)
    np.testing.assert_allclose(exp['horizontal_displacement_um'].values, values['Horizontal Displacement'])
    np.testing.assert_allclose(exp['time'].values, values['Time']-values['Time'][0])
    np.testing.assert_allclose(exp['ADC/Vertical Load'].values, (values['Vertical Load']-3)/2)
    assert exp['ADC/Vertical Load'].unit == 'V'
    assert len(manifest['calibrations']) == 2
    assert manifest['config']['tdms_acquisition_calibrations']['ADC/Vertical Load']['slope'] == 2
    assert 'ADC/' not in (tmp_path/manifest['outputs']['dat']).read_text().splitlines()[0]
    original = (tmp_path/manifest['outputs']['dat']).read_bytes()
    cat.path.unlink()  # Replay uses snapshots, including um models, independently of catalog.
    replayed = run(script, registry=cat.path, replay_manifest=tmp_path/'experiment.json')
    manifest = replayed
    assert (tmp_path/manifest['outputs']['dat']).read_bytes() == original


def test_tdms_header_import_and_unit_pipeline(tmp_path, monkeypatch, capsys):
    tdms = tmp_path/'test.tdms'
    write_tdms(tdms)
    catalog = tmp_path/'BigBiax.json'
    assert main(['catalog', 'init', '--file', str(catalog)]) == 0
    answers = iter(['BigBiax/load/V01/low/r1', 'V01', 'fixture A', '2026-11-01',
                    'V', 'kN', 'low', '0', '50', 'synthetic', 'y'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    assert main(['catalog', 'add', '--file', str(catalog), '--tdms', str(tdms),
                 '--channel', 'Vertical Load']) == 0
    cal = Catalog(catalog).get('BigBiax/load/V01/low/r1')
    assert cal.record['parameters'] == {'slope': 2., 'intercept': 3.}
    assert len(cal.record['provenance']['tdms_sha256']) == 64
    assert cal.record['purpose'] == 'acquisition'
    assert main(['catalog', 'list', '--tdms', str(tdms), '--file', str(catalog)]) == 1
    # Existing operators combine mm sample dimensions with micron displacement.
    from xlookpy import Experiment, Channel
    exp = Experiment({'u': Channel([0., 100., 200.], 'um', {'role': 'derived'}),
                      'time': Channel([0., 1., 2.], 's', {})})
    exp.layer_thickness('u', reference_record=0, thickness=2., unit='mm', output='h')
    exp.shear_strain('u', thickness='h', reference_record=0)
    np.testing.assert_allclose(exp['h'].values, [2., 1.95, 1.9])
    assert exp['shear_strain'].values[-1] == pytest.approx(100/1975 + 100/1925)
    exp.derivative('u', window_s=2., min_points=3, output='v')
    assert exp['v'].values[1] == pytest.approx(100.)
    assert exp['v'].unit == '(um)/s'


def test_catalog_old_definition_conflict(tmp_path):
    cat = Catalog(tmp_path/'BigBiax.json')
    cat.initialize()
    r = record()
    cat.add(r)
    legacy = tmp_path/(r['id']+'.json')
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(record(notes='a different definition under the same ID')))
    with pytest.raises(ValueError, match='Conflicting'):
        Registry(tmp_path).get(r['id'])
    with pytest.raises(ValueError, match='Conflicting'):
        Registry(tmp_path).list()


def test_bigbiax_bad_metadata_before_conversion(tmp_path):
    from xlookpy import Session
    from xlookpy.workflow import using_session, load
    with TdmsWriter(tmp_path/'bad.tdms') as writer:
        writer.write_segment([ChannelObject('ADC', name, [0., 1.],
            properties={'Slope': 1., 'Intercept': 0.} if name != 'Horizontal Displacement' else {})
            for name in ['Time', 'Vertical Load', 'Horizontal Load', 'Vertical Displacement', 'Horizontal Displacement']])
    session = Session(tmp_path)
    with using_session(session), pytest.raises(ValueError, match='Slope/Intercept'):
        load('bad.tdms', profile='BigBiax')
    assert not session.experiment.history
    session = Session(tmp_path)
    with using_session(session), pytest.raises(ValueError, match='expects'):
        load('bad.tdms', profile='BigBiax', units={'ADC/Vertical Load': 'kN'})
