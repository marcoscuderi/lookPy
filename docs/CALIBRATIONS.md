# Calibration records and revision history

## Three different decisions

1. **Acquisition conversion:** the `Slope` and `Intercept` properties embedded in
   this apparatus's TDMS. Apply them explicitly with `convert_acquisition()`.
2. **Sensor calibration:** a central record that maps a measured signal to a
   physical quantity, e.g. volts → kN, using `calibrate()`.
3. **Apparatus correction:** a central record that predicts elastic deformation
   from force, using `correct_displacement()`.

Acquisition conversion and external sensor calibration are alternative routes
when they describe the same conversion. Do not stack them. The API refuses
calibration of channels already marked as calibrated, including their converted
descendants. Raw channels remain available if a different calibration is needed.
The file reader does not know whether your stored values are volts, counts, or
physical values: explicitly declare input units when using an external sensor
calibration.

Geometry, references, thickness, spring insertion, sign conventions, and analysis
intervals belong in the experiment reduction script, not the sensor registry.

## A sensor calibration file

Create an ordinary UTF-8 JSON file. This example is invented, not a laboratory
calibration:

```json
{
  "schema_version": 1,
  "id": "biax/shear_loadcell/2026-10-r1",
  "category": "sensor",
  "apparatus": "biax",
  "sensor": "replace_with_sensor_serial",
  "date": "2026-10-01",
  "input_unit": "V",
  "output_unit": "kN",
  "model": "linear",
  "parameters": {"slope": 10.0, "intercept": 0.0},
  "valid_range": [-10.0, 10.0],
  "notes": "INVENTED example. Replace with measured calibration and supporting reference."
}
```

The application computes `output = slope * input + intercept`. Slope has units
`output_unit/input_unit`; intercept has `output_unit`. `valid_range` is expressed
in input units. Units are checked and compatible conversions such as N → kN are
performed explicitly inside the operation.

For a polynomial use:

```json
"model": "polynomial",
"parameters": {"coefficients": [0.1, 10.0, 0.0]}
```

This means `0.1*x**2 + 10*x + 0`. Coefficients are **highest power first**. The
coefficient multiplying x^p has units `output_unit / input_unit**p`. Changing
input units requires changing the coefficients too; never just relabel units.

## A nonlinear apparatus correction

Version 0.1 uses a single explicit convention: the calibration describes
**elastic displacement e(F) as a function of force**, not stiffness.

```json
{
  "schema_version": 1,
  "id": "biax/vertical_frame/2026-10-r1",
  "category": "apparatus",
  "apparatus": "biax",
  "sensor": "vertical_load_train_no_spring",
  "date": "2026-10-01",
  "input_unit": "kN",
  "output_unit": "mm",
  "model": "polynomial",
  "parameters": {"coefficients": [0.000008, 0.003, 0.0]},
  "valid_range": [0.0, 100.0],
  "notes": "INVENTED example e(F). Replace with your measured calibration."
}
```

Here `e(F) = 0.000008 F² + 0.003 F` mm, for F in kN. A constant stiffness K
in kN/mm is represented by a linear model with `slope = 1/K` mm/kN and
`intercept = 0`. The code validates positive tangent compliance throughout the
declared force range, including internal extrema of the derivative polynomial.

For a chosen original reference record r:

**u_corrected(i) = [u(i) − u(r)] + sign × [e(F(i)) − e(F(r))]**

Use `sign=-1` when deformation must be subtracted from the measured displacement.
Use `sign=+1` for the opposite coordinate convention. This is independent of
vertical/horizontal names: the operator chooses based on the actual coordinate.
The force must have the same physical reference/convention used to obtain e(F).
An arbitrary force zero change can alter a nonlinear correction.

This assumes reversible, single-valued apparatus deformation. It does not model
hysteresis or permanent seating. It is intentionally distinct from Xlook's
incremental tangent-stiffness integration and the previous package's legacy
high-order stiffness polynomials. **Do not paste stiffness-polynomial
coefficients into an e(F) record.** A later compatibility operation can preserve
those algorithms explicitly after comparison with the C references.

If you have a different spring configuration, import a separate calibration ID
and select its applicable interval with `records=...`. In 0.1 one correction call
handles one stage and gives NaN outside it. Automatic stitching of mechanical
stages, and simultaneous-spring correction models, are not implemented. Leave
correction disabled until the selected model actually represents your setup.

## Import, inspect and select

```bash
python -m xlookpy calibration import /path/new_calibration.json
python -m xlookpy calibration list
python -m xlookpy calibration show biax/vertical_frame/2026-10-r1
```

Or use **Import calibration** in the desktop. The log prints the imported
definition. The script selects it using an exact ID:

```python
frame = session.calibration("biax/vertical_frame/2026-10-r1")
exp.correct_displacement("measured", force="force", using=frame,
                         reference_record=1200, sign=-1, output="slip")
```

For each new calibration campaign, create a **new ID** with the new date and/or
revision. Import never overwrites different coefficients under an existing ID.
Importing identical content is allowed and does not create another revision.
Do not manually edit files already inside the central registry.

The application never silently selects “latest”. A previously used ID whose
central contents were changed externally is refused when the project manifest
is available. Full access control and audit signatures for a shared laboratory
registry are outside this first release.

## Range policy

The default is `outside="error"`, which stops publication if any finite input
being processed falls outside the declared calibration range. Alternatives:

| Policy | Behaviour |
|---|---|
| `mask` | Out-of-range results become NaN |
| `clip` | Evaluate the model at the nearest range limit |
| `extrapolate` | Evaluate beyond the range; operator accepts an unvalidated model |

The chosen policy and out-of-range count are recorded in operation metadata.
An elastic correction's reference must remain finite. A masked reference stops
the operation. Clipping e(F) saturates its deformation; it does **not** hold
tangent compliance constant outside the range.

## Snapshots and replay

`experiment.json` records the complete definition and SHA256 of every applied
central calibration, operation choices and acquisition coefficients. It also
contains the executed script, raw input fingerprint, software versions, record
selections and output fingerprints. Metadata is not stored only in the GUI.

To rerun with the saved calibration snapshots even when the central folder is
unavailable:

```bash
python -m xlookpy run /path/project/reduction.py --replay-manifest /path/project/experiment.json
```

Replay requires the identical script, raw bytes and xlookpy version. It uses
embedded calibration records instead of the registry. Restore the manifest's
`script.source` if you have changed the script. Dependency versions are recorded
but not automatically recreated/enforced; retain the tested Python environment
for strict numerical reproduction. New replay results are written to a new run
folder, leaving earlier outputs intact.
