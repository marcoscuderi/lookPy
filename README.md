# lookPy

Script-driven experimental reduction, inspired by Xlook's interactive workflow.

The `main` branch includes the embedded Monokai editor, contact-onset zeroing,
manual plot tabs with original record IDs, rawPy-style reduction operations,
and a shared cell and IPython workspace.
The repository is named lookPy; the Python package and launch command remain
`xlookpy`, so existing reduction scripts continue to work.

## Install with Anaconda

Clone into a permanent local folder, preferably outside Google Drive. Keep raw
experiments and operator reduction scripts in their own experiment directories.

```bash
git clone https://github.com/marcoscuderi/lookPy.git
cd lookPy
conda activate xlook
python -m pip install -e ".[gui]"
python -m xlookpy gui
```

If you do not yet have the environment, run `conda env create -f environment.yml`
before activating it. The editable installation uses this checkout directly.
In the GUI, open your existing experiment's reduction script.

## Try the synthetic teaching example

```bash
python tools/setup_demo.py
python -m xlookpy gui examples/demo/reduction.py
```

Click **Run all** to load/reduce; no plot tabs open automatically. Choose X,
LEFT and optional RIGHT channels, then click **New plot tab**. Change channels
and click **Refresh axes** to update the active plot without creating another
tab. Use `record_id` as an axis to inspect original row number against time.

The embedded editor still supports Python colouring, font-size controls and
dark/light themes. Click curves to copy original row IDs and two-point intervals.

The included raw.csv and calibration_examples are explicitly synthetic fixtures.
They are not calibration values for the apparatus. No real TDMS experiments or
measured calibration registry is included in this public repository.

## Standard experiment reduction

Use `examples/your_experiment/reduction.py` in your experiment directory. Set
RAW_FILE to the input TDMS. With contact records set to None, run to inspect the
original physical signals. Pick the contact onset for each ram and enter those
single original record IDs, then run again.

Each ram's force/displacement is zero at its contact, forced to zero beforehand,
and retains measured changes afterwards. Calibrations, contact choices, units,
script source and raw-data fingerprints are stored in the experiment manifest.
Apparatus correction remains an explicit operator choice.

## Updates and rollback

Close the app, then from this checkout:

```bash
git status
git switch main
git pull --ff-only
python -m xlookpy gui
```

Preserve any local edits before switching/updating. Reinstall with
`python -m pip install -e ".[gui]"` when dependency/package metadata changes.
See [the Git workflow guide](docs/VERSION_CONTROL.md) for testing branches and
returning to an exact release. The baseline release is tagged `v0.1.1a1`.
See the [release history](https://github.com/marcoscuderi/lookPy/releases).

## Development policy

- main contains accepted changes; future work uses a separate branch and PR.
- Automated tests and operator acceptance precede merging.
- Numerical algorithms remain separate from the GUI.
- Real calibration records and experiment directories stay outside this repo.
- Changes and releases are recorded in [CHANGELOG.md](CHANGELOG.md).

See [CONTRIBUTING.md](CONTRIBUTING.md). Branch protection is a repository-owner
setting, separate from this documented policy. The project license is not yet
selected.

## Tests

```bash
python -m pip install -e ".[gui,test]"
python -m pytest -q
```

GitHub Actions runs the test suite on Linux and macOS with Qt
offscreen. Offscreen tests do not certify native desktop behaviour or approve
scientific reference/calibration choices. The application remains an early
working foundation, not a complete Xlook port.

## Documentation

- [Historical Mac test procedure for manual plot tabs](docs/testing/MANUAL_PLOT_TABS_MAC.md)

- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Contact-zero workflow](CONTACT_ZERO_UPDATE.md)
- [Calibration definitions and history](docs/CALIBRATIONS.md)
- [Reduction API and execution rules](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Git workflow: install, update, test and roll back](docs/VERSION_CONTROL.md)
- [Baseline provenance](docs/BASELINE.md)
- [Validation and limitations](VALIDATION.md)

Rate-and-state forward/inverse modelling, advanced catalogues and additional
Xlook compatibility remain future work.

## rawPy-style mock analysis

Start with the [function reference](docs/RAWPY_FUNCTIONS.md) and
[worked reduction](examples/rawpy_mock/reduction.py). The
[historical Mac test procedure](docs/testing/RAWPY_ANALYSIS_MAC.md) records
the original branch validation.
All mock constants are synthetic; no real experiment data are included.

## Interactive cell workspace

Use your real experiment with [cell execution and IPython](docs/CELL_WORKSPACE.md).
The guide covers running cells, trying commands in the console, and publishing
a reproducible reduction with Run all.

## Highlighting and working channels

The [channel updates guide](docs/testing/CHANNEL_UPDATES_MAC.md) describes
editor colouring, in-place updates, and revision history. Reduced exports
include current working values by default.
