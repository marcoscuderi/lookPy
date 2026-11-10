# lookPy

Script-driven experimental reduction, inspired by Xlook's interactive workflow.

lookPy combines a Python reduction script, an interactive IPython workspace,
and dual-axis plots for laboratory data. The package and launch command are
`xlookpy`. See the [changelog](CHANGELOG.md) and [tagged releases](https://github.com/marcoscuderi/lookPy/releases).

## Install with Anaconda

Clone into a permanent local folder, preferably outside Google Drive. Keep raw
experiments and operator reduction scripts in their own experiment directories.

```bash
git clone https://github.com/marcoscuderi/lookPy.git
cd lookPy
conda env create -f environment.yml
conda activate xlook
python -m pip install -e ".[gui]"
python -m xlookpy gui
```

If the `xlook` environment already exists, skip its creation. The editable
installation uses this checkout directly.
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

Choose a **Fit degree** (1 for a slope, 2–6 for a polynomial), click **Fit
interval**, then click two points on the curve of interest. The fit uses all
finite X/Y pairs between those original records, inclusive. The plot draws the
fit on the curve's Y axis. The execution log shows the interval, sample count,
fit quality and coefficients, including the slope and its units for degree 1.
Each new fit replaces the previous overlay in that tab. **Clear fit** removes
it. Use the reduction script's `exp.fit()` for fits you want to save and replay.

To remove a trend, fit the interval and click **Copy detrend command**. Paste
the command into your reduction script after the operations that produced the
plotted channels, then run that cell. The new channel contains the measured
values minus the fitted trend, in the original Y units. Plot it against the
same X channel or `record_id`. Use a separate output name for each window.

The embedded editor still supports Python colouring, font-size controls and
dark/light themes. Click curves to copy original row IDs and two-point intervals.

The included raw.csv and calibration_examples are explicitly synthetic fixtures.
They are not calibration values for the apparatus. The operator-reviewed
`calibrations/BigBiax.json` contains the published laboratory calibration catalog;
see the [calibration guide](docs/BIGBIAX_CALIBRATIONS.md) for baseline handling,
configuration checks and explicit selection. Real TDMS experiments are not included.

## Standard experiment reduction

For BigBiax, copy the [step-by-step reduction template](examples/bigbiax/reduction_step_by_step.py)
into your experiment directory. Set `RAW_FILE` and select the reviewed
`calibrations/BigBiax.json` from your checkout in cell 3 or when launching lookPy.
Run through cell 4a to inspect the ADC signals, enter the picked record IDs in
cell 4b, and review the remaining stages one cell at a time. Use **Run all**
after review to write the final results and experiment manifest.

### Acquisition-profile example

Use `examples/your_experiment/reduction.py` in your experiment directory. Set
RAW_FILE to the input TDMS. With contact records set to None, run to inspect the
original physical signals. Pick the contact onset for each ram and enter those
single original record IDs, then run again.

Each ram's force/displacement is zero at its contact, forced to zero beforehand,
and retains measured changes afterwards. Calibrations, contact choices, units,
script source and raw-data fingerprints are stored in the experiment manifest.
Apparatus correction remains an explicit operator choice.

## Reopen reduced data

Open the same reduction script to load its last published result. The manifest
points to the exported table at `results/<run-id>/reduced.dat`. See
[reopening saved results](docs/OPERATOR_GUIDE.md#reopen-saved-results) for
loading that table from a separate analysis script.

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
returning to an exact release. The initial baseline is available as `v0.1.1a1`.

## Development policy

- main contains accepted changes; future work uses a separate branch and PR.
- Automated tests and operator acceptance precede merging.
- Numerical algorithms remain separate from the GUI.
- Experiment directories and private calibration additions stay outside this repo;
  the operator-approved BigBiax catalog is versioned explicitly.
- Changes and releases are recorded in [CHANGELOG.md](CHANGELOG.md).

See [CONTRIBUTING.md](CONTRIBUTING.md). Branch protection is a repository-owner
setting, separate from this documented policy. The project license is not yet
selected.

## Tests

```bash
python -m pip install -e ".[gui,test]"
python -m pytest -q
```

GitHub Actions runs the test suite on Linux and macOS with Qt offscreen.

## Documentation

- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Cell execution and IPython](docs/CELL_WORKSPACE.md)
- [BigBiax calibration and frame correction](docs/BIGBIAX_CALIBRATIONS.md)
- [Calibration definitions and history](docs/CALIBRATIONS.md)
- [Reduction API and execution rules](docs/API.md)
- [rawPy operations and worked example](docs/RAWPY_FUNCTIONS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Git workflow: install, update, test and roll back](docs/VERSION_CONTROL.md)
- [Validation and limitations](VALIDATION.md)
- [Historical baseline](docs/BASELINE.md) and [branch test procedures](docs/testing/)
