# Xlook Python — first test implementation

Version **0.1.1a1**, with contact-onset zeroing and the Monokai editor. A script-driven desktop workspace for experimental reduction.
The numerical package also runs without the desktop. This is an early working
foundation, not a complete translation of Xlook and not a validated final
reduction of your laboratory experiment.

Start with the synthetic example, then use the TDMS template with your own
operator choices. All example calibration values are labelled **synthetic**.

## Start on your Mac

Using Anaconda, unzip this package, open Terminal, and change into the
`xlook_python` folder. For a first installation run:

```bash
conda create -n xlook python=3.12 pip
conda activate xlook
python -m pip install -e ".[gui]"
python tools/setup_demo.py
python -m xlookpy gui examples/demo/reduction.py
```

The first installation needs internet access. If the xlook environment already
exists, skip its creation. On subsequent occasions run `conda activate xlook`,
change to the installed source folder, and run the final command. Closing a plot
tab does not change the reduction script. For an existing editable installation,
see `EDITOR_UPDATE.md` for updating only the two editor-related files.

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

## Try your actual experiment

Copy `examples/your_experiment/reduction.py` into a **new directory** containing
`eq_phys_demo.tdms`, or set its `RAW_FILE` to the full file path. Keep your
existing reduction project intact.

```bash
python -m xlookpy gui /full/path/to/your/new_project/reduction.py
```

The template starts in inspection mode while either contact setting is `None`.
Run it to see original physical forces and displacements, click each ram's
sample-contact onset, and paste the copied original record ID into:

```python
VERTICAL_CONTACT_RECORD = 1200    # Example only: replace with your picked ID.
HORIZONTAL_CONTACT_RECORD = 850  # Example only: replace with your picked ID.
```

Run all again to reduce. Each selected contact sample is exactly zero, earlier
force/displacement samples are forced to zero, and later samples retain their
changes relative to contact. Each ram's displacement shares that ram's contact.
These are single record IDs, not times, values or averaging intervals.

The reduction uses the acquisition coefficients stored in the TDMS, 2500 mm²
area, and two shear surfaces. **Apparatus correction is disabled** until selected.
Contact choices and subtracted values are retained in the experiment manifest.
Friction without sufficient normal load is NaN; velocity is estimated only from
complete windows after vertical contact, so it cannot leak across the imposed
pre-contact zero segment.

The file's custom Slope/Intercept properties do not declare physical output
units. The template explicitly supplies the kN/µm/s conventions used in your
previous workflow. The interface retains those properties in the original
channel metadata. Original TDMS channel units are labelled `unassigned` until
declared; they are not assumed to be physical dimensionless measurements.
Do not apply demo calibrations to this file.

The original standard-reduction template was exercised on your full
728,939-record file. The contact-zero revision was tested with generated TDMS
signals of known contact and deformation, including an elastic correction.
The raw laboratory file is not duplicated in this download. Selecting the actual
physical contact records remains the operator's decision. See CONTACT_ZERO_UPDATE.md.

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

## Documentation and limitations

- [Calibration guide](CALIBRATIONS.md): models, coefficient units, revisions,
  range policies, snapshots and replay.
- [API and execution rules](API.md): all supported reduction operations,
  numerical definitions and record selection conventions.
- [Architecture and development scope](ARCHITECTURE.md): module boundaries
  and the next implementation steps.
- [Validation](../VALIDATION.md): checks performed and remaining limitations.

The accepted numerical workflow supports Run all, original-record selections,
CSV/BRAVA text/legacy binary and the apparatus ADC-group TDMS reader. See the
[function reference](RAWPY_FUNCTIONS.md) for current operations. The workspace
trial adds [top-level cells and IPython](CELL_WORKSPACE.md); use the
[real-experiment Mac procedure](testing/CELL_WORKSPACE_MAC.md). Existing
`def reduce(session)` files continue to run in batch mode; convert a new working
copy to use cells and the console. Rate-and-state modelling, inversion,
stick-slip catalogues, automatic calibration fitting and publication figure
export remain deferred. There is no full Xlook command-recipe compatibility claim.

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
