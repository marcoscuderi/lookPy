# lookPy operator guide

lookPy provides a Python script editor, a cell workspace with IPython, and
interactive dual-axis plots for laboratory experiment reduction. The same
reduction scripts can also run from the terminal.

Follow the [installation instructions](../README.md#install-with-anaconda).
Start with the [synthetic teaching example](../README.md#try-the-synthetic-teaching-example)
to learn the plot controls, then open a copy of the BigBiax template in your
experiment directory.

## Readable script editor

The script panel now uses Monokai-inspired Python colouring, line numbers and
a current-line highlight. Above the source are a **Font** selector (8–32 pt,
default 14) and a **Theme** selector (Monokai or Light). Both preferences are
remembered on this computer. With focus in the editor, use **Cmd + / Cmd -** on
Mac (**Ctrl + / Ctrl -** on other platforms) to change size, and **Cmd 0** to
reset it to 14 pt. The visible Font selector is always available.

Keywords, function calls, strings/docstrings, numbers, built-ins and comments
have distinct colours. Colouring is a visual aid, not a Python error checker.
It does not change the source, calculations or experiment manifest.

1. Click **Run all**. The script is saved and executed in a separate process.
2. The channel list and execution log populate on success; no plots open
   automatically. Select axes and use New plot tab. Use Refresh axes to update
   that same plot when you change its variables. `record_id` is the original
   row-number plotting column.
3. Zoom horizontally. Both y-axes fit the visible data independently. Uncheck
   **Fit both Y axes** to hold the current ranges. Right-click the plot for
   additional navigation controls. Matching x channels are linked between tabs;
   toggle **Link matching X axes** to unlink them.
4. Click near a curve. The exact original record ID is copied to the clipboard;
   coordinates, units and channel are printed in the bottom panel. Picking uses
   full-resolution values even when the drawing is downsampled.
5. Pick two points and press **Copy interval from last 2 picks**. Paste the
   resulting `exp.records(start, end)` into the script. Endpoints are inclusive.
6. Change `velocity_window_s` from `0.20` to `1.0`; click **Run all** again.
   Compare the shape and amplitude of the velocity peaks. A larger window reduces
   noise but broadens/attenuates short events.
7. Inspect `examples/demo/experiment.json` and the new `results/<run-id>` folder.
   Repeating Run all does not accumulate conversions or corrections.

The application is not a notebook and does not use notebook plotting widgets.
The right panel is an ordinary Python script editor; plot selections only change
the script when you paste them. Save before switching projects or closing the
application in this initial release.

## Reduce a BigBiax experiment

1. Copy the [step-by-step template](../examples/bigbiax/reduction_step_by_step.py)
   into your experiment directory. Set `RAW_FILE` and select the reviewed
   [BigBiax catalog](BIGBIAX_CALIBRATIONS.md).
2. Run through cell 4a. Plot the original ADC load channels against `record_id`,
   then enter the unloaded intervals, ram contacts and analysis end in cell 4b.
3. Run the remaining cells in order and inspect the calibrated signals, stresses,
   and load-point and corrected displacements. Review the geometry, frame model
   and its applicable interval for each experiment.
4. Use **Run all** to publish your checked reduction. See
   [cell execution and IPython](CELL_WORKSPACE.md) for exploratory work.

For the earlier acquisition-profile workflow, use the
[legacy batch example](../examples/your_experiment/reduction.py) and see the
[contact-zero notes](../CONTACT_ZERO_UPDATE.md).

## Central application and per-experiment files

Application code is installed once in your Python environment. The shared
calibration registry defaults to `~/.xlookpy/calibrations`, outside the installed
application. It is not copied into each experiment project.

To use a laboratory-wide folder instead, supply the same registry when importing
calibrations and launching/running reductions:

```bash
python -m xlookpy calibration import /path/new_calibration.json --registry /path/lab_calibrations
python -m xlookpy gui /path/experiment/reduction.py --registry /path/lab_calibrations
```

Alternatively set the environment variable `XLOOKPY_CALIBRATIONS`. The GUI also
has a **Registry folder** selector for its subsequent runs; that selection is
for the current application session. Registry paths are configuration, not
scientific calibration identity.

Each experiment directory contains:

| File | Purpose |
|---|---|
| Raw input | Original measurements; never modified by the package |
| `reduction.py` | Operator choices and readable analysis procedure |
| `experiment.json` | Manifest of the most recent successful reduction |
| `results/<run-id>/reduced.dat` | Tab-separated data, header and units rows, full double precision |
| `results/<run-id>/state.npz` | Full-resolution channel cache for the GUI |
| `results/<run-id>/manifest.json` | Manifest retained with that particular run |

No separate calibration files are required in the experiment directory. The
manifest embeds the exact calibration definitions used. Previous result folders
are retained; automatic cleanup is not implemented.

## Reopen saved results

Open the original reduction script in lookPy to load its last published result.
Use **New plot tab** to inspect the saved channels.

To start a separate analysis, place `analysis.py` beside `experiment.json`
and run this cell in lookPy:

```python
# %% Open the exported data
import json
from xlookpy import load

manifest = json.loads(
    (session.project / "experiment.json").read_text(encoding="utf-8")
)
exp = load(manifest["outputs"]["dat"], reader="text")
```

The loader restores the exported channels, units and original record IDs.
For a fixed run, pass its `results/<run-id>/reduced.dat` path directly to
`load()`. Use **Run cell** for exploration in the same directory. A successful
**Run all** from a separate analysis script publishes a new result there and
updates `experiment.json`.

## Documentation and limitations

- [Calibration guide](CALIBRATIONS.md): models, coefficient units, revisions,
  range policies, snapshots and replay.
- [API and execution rules](API.md): all supported reduction operations,
  numerical definitions and record selection conventions.
- [Architecture and development scope](ARCHITECTURE.md): module boundaries
  and the next implementation steps.
- [Validation](../VALIDATION.md): checks performed and remaining limitations.

The readers support CSV, rawPy-style text, supported legacy binary files, and
aligned ADC-group TDMS data. Existing `def reduce(session)` scripts continue
to run in batch mode. **Convert to cell script** creates a working copy for
cell execution. Rate-and-state modelling, inversion, stick-slip catalogues
and automatic calibration fitting remain outside this release.

Scripts are ordinary trusted Python with access to your computer. Transactional
publication applies to package-managed outputs, not arbitrary file writes made
by custom Python code. Background cancellation can leave a temporary staging
directory; it never exposes a half-written `experiment.json`.

## Terminal use and tests

```bash
python -m xlookpy run examples/demo/reduction.py
python -m xlookpy calibration list
python -m pip install -e ".[test]"
python -m pytest -q
```

The desktop tests run Qt offscreen and skip if optional GUI dependencies are
absent. Passing offscreen tests is not a substitute for testing the desktop on
your Mac.
