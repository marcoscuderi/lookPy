# Test rawPy analysis on your Mac

This is feature branch `feature/rawpy-analysis`, version `0.2.0a1`.
Main retains the last accepted plotting implementation until you accept this PR.

## 1. Update and select the test branch

Close the GUI. In Terminal:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git status
```

Use your actual checkout path. Continue if working tree is clean. If modified
tracked files are listed, preserve them before switching; do not discard edits.

```bash
git fetch origin
git switch feature/rawpy-analysis
git pull --ff-only
python -m pip install -e ".[gui,test]"
python -c "import xlookpy; print(xlookpy.__version__); print(xlookpy.__file__)"
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Expected version: **0.2.0a1**, module path inside this checkout. SciPy is a new
required dependency installed by the command. Native GUI behaviour still needs
your Mac test even if automated Linux/macOS checks pass.

## 2. Create and run the mock experiment

```bash
python tools/setup_rawpy_mock.py --destination "$HOME/lookPy-tests/rawpy-mock-01"
python -m xlookpy gui "$HOME/lookPy-tests/rawpy-mock-01/reduction.py"
```

The setup refuses to overwrite raw.csv/reduction.py. Choose a new destination
if you already used this directory. The working script is outside the checkout,
so edits do not dirty Git. All data, contacts, stiffnesses and bench dimensions
in this mock are SYNTHETIC. No central registry setup is needed for this example.

Click **Run all**. Expected: **2,300 records, 27 channels**, fit results in the log,
`experiment.json` and a versioned `results/` directory beside the script.
No plots should open automatically.

## 3. Plot and inspect, using New plot tab and Refresh axes

| Check | Plot and expected result |
|---|---|
| Sampling stages | X=time, LEFT=record_id. Slope changes at 10 s and 30 s: 10, 100, then 20 samples/s. |
| Contact zero | X=record_id, LEFT=normal_force. Records 0..20 are exactly zero; load grows afterward. Contact IDs in this synthetic file are H=20, V=80. |
| Stress geometry | X=time, LEFT=normal_stress, RIGHT=shear_stress. Normal reaches 20 MPa; shear tends to about 12.0088 MPa including the synthetic gravity term. |
| Offset repair | X=time, LEFT=loadpoint_displacement, RIGHT=displacement_repaired. Near 20 s, the repaired signal has the reset removed, with a short flattened interval. |
| Frame correction | X=time, LEFT=displacement_repaired, RIGHT=slip. Slip excludes synthetic vertical frame deformation and equals zero at record 80. |
| Thickness | X=record_id, LEFT=layer_thickness, RIGHT=legacy_corrected_thickness. Measured per-layer thickness is exactly .8 mm at record 200; legacy correction begins there, earlier values are NaN. |
| Strain | X=time, LEFT=shear_strain. Zero at record 200, then increasing; earlier values undefined. |
| Friction | X=time, LEFT=friction. Undefined before valid shear loading; tends to about .60044 at late times. |
| Velocity | X=time, LEFT=velocity_time_window, RIGHT=velocity_sample_window. Approximately .02 mm/s after shear loading, away from reset repair and boundaries. Edge support differs between the two methods. |
| Filter | X=time, LEFT=friction, RIGHT=friction_filtered. High-frequency noise reduced during 12..18 s, unchanged outside. Zoom in to see this. |
| Linear fit | X=slip, LEFT=friction, RIGHT=friction_linear_fit. Fit exists only at records 300..600; coefficients and R² are printed in log. |
| Polynomial | Refresh RIGHT=friction_polynomial_fit. Fourth-degree fit on same interval; coefficients are ascending powers. |

Axes have independent scales when using LEFT and RIGHT; use readout values as well
as visual curve separation. Picking and interval copy should still use original IDs.

## 4. Practise the operator workflow

1. In embedded editor set both contact constants to `None` and click Run all.
   Only the five stored channels remain, in inspection mode.
2. Plot each raw load against record_id. Pick the onset and enter H=20 and V=80.
3. Run all; derived channels return. Repeat Run all: identical reduced data, no
   cumulative correction. Each successful run has its own result directory.
4. Try changing `window=20` to `window=40`; compare velocity smoothing.
5. Try a deliberately invalid whole-experiment filter by removing its `records=`
   argument. It should report mixed sampling rates. The previous successful
   manifest/results remain. Restore the filter interval and rerun.
6. Read the manifest: selected records, stiffness values/units, geometry, filter
   parameters, polynomial diagnostics and exact script are recorded.

## 5. Start a real experiment

Keep this mock unchanged for reference. Create a separate experiment directory,
copy `examples/your_experiment/reduction.py` there, and point RAW_FILE to your data.
Use the inspection/contact-zero workflow already established in that template.
Add operations from `docs/RAWPY_FUNCTIONS.md` one at a time, using the channel names
produced by that template. The template's inspection output lets you identify ADC
channels and choose explicit conversion units. Do not copy mock contact IDs,
stiffnesses, sign choices or layer thickness into a real reduction.

For TDMS use `session.load("experiment.tdms")` and explicit acquisition conversions;
for legacy laboratory text use `reader="text"`; for old Xlook binary use
`reader="xlook_binary"` and the known payload endianness. Units from old headers
can be overridden explicitly with `units={...}`.

The existing real-experiment template is intentionally retained: no unapproved
apparatus calibration is switched on. Prefer central calibrated e(F) records;
`elastic_correct` is available for explicit constant-k comparisons.

## 6. Return to the accepted version

Close the application:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git switch main
git pull --ff-only
python -m pip install -e ".[gui,test]"
python -m xlookpy gui
```

The old version cannot execute the newly added operations. Open an older compatible
reduction script when running main. Keep all working experiment scripts outside Git.
Report which test step failed, its error log and the relevant script choices.
After you approve, we can merge this branch and give the normal main update commands.
