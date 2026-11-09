# lookPy

Script-driven experimental reduction, inspired by Xlook's interactive workflow.

**Trial branch: 0.1.3a1 — manual plot tabs and original-row axes.**
The approved main/tag baseline remains 0.1.1a1 until this change is accepted.
The embedded Monokai editor and contact-onset zeroing are retained.
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

Choose a **Fit degree** (1 for a slope, 2–6 for a polynomial), click **Fit
interval**, then click two points on the curve of interest. The fit uses all
finite X/Y pairs between those original records, inclusive. The plot draws the
fit on the curve's Y axis. The execution log shows the interval, sample count,
fit quality and coefficients, including the slope and its units for degree 1.
Each new fit replaces the previous overlay in that tab. **Clear fit** removes
it. Use the reduction script's `exp.fit()` for fits you want to save and replay.

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
returning to an exact release. The baseline tag v0.1.1a1 is created after the
first successful Linux/macOS CI run; published tags are never moved.

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

GitHub Actions runs the 26-test feature suite on Linux and macOS with Qt
offscreen. Offscreen tests do not certify native desktop behaviour or approve
scientific reference/calibration choices. The application remains an early
working foundation, not a complete Xlook port.

## Documentation

- [Exact Mac branch-testing and rollback procedure](docs/testing/MANUAL_PLOT_TABS_MAC.md)

- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Contact-zero workflow](CONTACT_ZERO_UPDATE.md)
- [Calibration definitions and history](docs/CALIBRATIONS.md)
- [Reduction API and execution rules](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Git workflow: install, update, test and roll back](docs/VERSION_CONTROL.md)
- [Baseline provenance](docs/BASELINE.md)
- [Validation and limitations](VALIDATION.md)

Rate-and-state forward/inverse modelling, advanced catalogues and additional
Xlook compatibility remain future work. Cell execution and IPython are available
on the workspace test branch described below.

## rawPy-style mock analysis (0.2.0a1 test branch)

Start with the [Mac test procedure](docs/testing/RAWPY_ANALYSIS_MAC.md),
[complete function reference](docs/RAWPY_FUNCTIONS.md), and
[worked reduction](examples/rawpy_mock/reduction.py).
All mock constants are synthetic; no real experiment data are included.

## Interactive cell workspace (0.3.0a1 test branch)

Use your real experiment with [cell execution and IPython](docs/CELL_WORKSPACE.md).
The [Mac procedure](docs/testing/CELL_WORKSPACE_MAC.md) covers updating, converting
a working copy of your current script, testing and returning to main.

## Highlighting and compact channels (0.3.1a1)

The [Mac update guide](docs/testing/CHANNEL_UPDATES_MAC.md) describes stable editor
colouring, in-place working-channel updates, preserved revision history and
reduced exports containing only current working values by default.

## BigBiax calibrations

Use the [BigBiax calibration guide](docs/BIGBIAX_CALIBRATIONS.md) to create your
private JSON catalog, enter and inspect revisions, and apply nonlinear frame
corrections while keeping displacement in µm. Start with `python -m xlookpy catalog init`.
