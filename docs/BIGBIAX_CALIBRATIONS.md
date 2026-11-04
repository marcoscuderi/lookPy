# BigBiax calibration workflow

Main load and displacement channels contain voltages. Their custom TDMS
`Slope` and `Intercept` properties convert these values to kN and µm:

`engineering_value = Slope * recorded_value + Intercept`

The explicit `BigBiax` profile applies this conversion once, retains acquisition
signs, keeps displacement in µm, and zeroes time at the first original record.
Time also needs its TDMS Slope/Intercept. Original `ADC/…` arrays remain unchanged.
This assumes the values delivered by npTDMS are voltages: NI native scaling and
custom Slope/Intercept are distinct mechanisms. Check one known measurement when
first using a new acquisition configuration; do not apply the profile to data
already converted to force/displacement.

## 1. Create your private catalog

```bash
conda activate xlook
python -m xlookpy catalog init
python -m xlookpy catalog list
```

Default location: `~/.xlookpy/calibrations/BigBiax.json`.
`init` preserves an existing catalog. The repository's `calibrations/BigBiax.json`
is an **empty structure**, with no laboratory values. Populate the private catalog
outside the application checkout, so updating Git cannot replace it.

For a different location, add `--file "/path/to/BigBiax.json"` to catalog commands.
Launch the reduction with `--registry "/path/to/BigBiax.json"` (both GUI and CLI).
`XLOOKPY_CALIBRATIONS` may also name that file or a registry directory. Existing
individual-record registries remain supported.

The JSON has four principal fields:

```json
{
  "schema_version": 1,
  "apparatus": "BigBiax",
  "description": "Private calibration history; no numerical defaults supplied.",
  "records": [],
  "suggested_defaults": {}
}
```

Each entry in `records` has a permanent `id`, `purpose`, `category`, `apparatus`,
`sensor`, `configuration`, `date`, `source`, `input_unit`, `output_unit`, `model`,
`parameters`, `valid_range`, and `notes`. Acquisition and auxiliary records also
require `gain`. The manager prompts for these fields and validates them before
saving. Each record retains its own coefficients, units and validity range.

| Purpose | Category | Typical input → output | How used |
|---|---|---|---|
| `acquisition` | `sensor` | V → kN or µm | Archive the conversion recorded in TDMS; the profile uses the TDMS itself |
| `auxiliary` | `sensor` | V → sensor engineering units | Explicit `exp.calibrate()` |
| `elastic` | `apparatus` | kN → µm | Explicit `exp.correct_displacement()` |

## 2. Enter or import a revision

```bash
python -m xlookpy catalog add
```

Choose `elastic` for apparatus deformation, or `auxiliary` for an additional
sensor. The guided prompts accept linear or polynomial models. Review the
printed definition and type `y` to save. Invalid input or cancelling leaves the
catalog unchanged. Use descriptive, permanent IDs such as:

- `BigBiax/frame/vertical/config_A/r1`
- `BigBiax/frame/horizontal/config_A/r1`
- `BigBiax/aux/P01/low/r1`

These are naming examples, not installed records. Gain is explicit; it is never
inferred from amplitude or calibration date. Change the ID for every new revision.
The manager refuses replacement of an existing ID with different values.

To archive a main-channel calibration directly from the TDMS header:

```bash
python -m xlookpy catalog add \
  --tdms "/path/to/experiment.tdms" --channel "Vertical Load"
```

This reads the custom coefficients without retyping them and records the source
TDMS SHA256 and channel. You supply sensor identity, gain, configuration, units,
calibration date, **the independently established calibrated voltage range**,
and notes. The experiment date and measured data extrema do not establish
calibration validity. This archive does not override a different experiment's
TDMS coefficients. Repeat for other main load/displacement channels if desired.

To import an existing single-record JSON with the fields above:

```bash
python -m xlookpy catalog import "/path/to/calibration_record.json"
```

Records are appended to the one central file. Its manager uses an exclusive
writer lock and atomic file replacement. Keep backups of this file; do not edit
old records by hand. After a crash, inspect any remaining `.lock` file before
removing it, and confirm no manager process is still writing.

## 3. Inspect and select

After replacing these illustrative IDs with actual installed IDs:

```bash
python -m xlookpy catalog list
python -m xlookpy catalog show BigBiax/frame/vertical/config_A/r1
python -m xlookpy catalog curve BigBiax/frame/vertical/config_A/r1 --points 21
python -m xlookpy catalog suggest vertical_frame BigBiax/frame/vertical/config_A/r1
```

`curve` prints an input/output table across the calibrated range. `show` prints
the complete definition and fingerprint. `list` includes all historic revisions,
gain and configuration. Suggestions are conveniences for choosing an ID; the
reduction requires an **exact revision ID**, never a changing `latest` alias.
There is no GUI calibration editor in this first implementation.

## 4. Connect your real reduction script

Keep your existing cell structure and scientific parameters. Change the load
cell to:

```python
# %% Load and acquisition conversion
exp = load(RAW_FILE, profile="BigBiax", units={"ADC/AUX 6": "V"})
# Main working names:
# vertical_load / horizontal_load                 [kN]
# vertical_displacement_um / horizontal_displacement_um [um]
# time                                            [s]
```

Omit the `units` argument if not calibrating an auxiliary sensor. Set actual
sensor units for any AUX channel you use; the profile does not assume all AUX
channels are voltages. Sensors other than the four mapped main channels remain
unassigned unless explicitly declared. To reverse a displacement coordinate,
use an explicit in-place operation before its contact zeroing:

```python
exp.convert("horizontal_displacement_um", unit="um", scale=-1)
```

BigBiax does not automatically reverse this coordinate. When migrating from
BRAVA, restore that explicit `-1` if you need the old sign convention.

After contact picking and any required displacement repair, apply the chosen
apparatus corrections **before** calculating thickness, strain or velocity:

```python
# %% Nonlinear apparatus correction
# Set these IDs to records you have entered, and the contacts to picked record IDs.
vertical_frame = calibration(VERTICAL_FRAME_ID)
horizontal_frame = calibration(HORIZONTAL_FRAME_ID)

exp.correct_displacement(
    "vertical_displacement_um",
    force="vertical_load",
    using=vertical_frame,
    reference_record=VERTICAL_CONTACT,
)
exp.correct_displacement(
    "horizontal_displacement_um",
    force="horizontal_load",
    using=horizontal_frame,
    reference_record=HORIZONTAL_CONTACT,
)
```

With the default `sign=-1`, each call computes:

`corrected[i] = (u[i] - u[reference]) - (e(F[i]) - e(F[reference]))`

`e(F)` is the **measured elastic deformation of the apparatus**, not stiffness.
For a polynomial, coefficients are in descending powers, e.g. `[a2, a1, a0]`
means `e(F) = a2*F**2 + a1*F + a0`. For a linear model use `slope` and `intercept`.
Units and positive tangent compliance are validated throughout the declared
force range. The local stiffness is `1 / (de/dF)`.

If your existing calibration describes **tangent stiffness** `k(F)`, it must first
be converted to deformation by integrating `1/k(F)`. Do not enter its polynomial
coefficients as deformation coefficients. This implementation accepts linear or
polynomial **deformation** models; it does not accept arbitrary stiffness curves.

The force input must represent the force used in the calibration, with a
consistent physical zero. Correction is relative to contact, so a constant
intercept cancels. Use `sign=1` only if your displacement coordinate requires
adding apparatus deformation instead of subtracting it.

By default out-of-range force raises an error; there is no silent 2–162 kN
clipping. If the initial unloaded records fall outside the calibration, select
a valid interval explicitly:

```python
exp.correct_displacement(
    "vertical_displacement_um", force="vertical_load",
    using=vertical_frame, reference_record=VERTICAL_CONTACT,
    records=exp.records(VERTICAL_CONTACT, END_RECORD),
)
```

The reference must lie inside that interval and within the calibration range.
Values outside the selected interval become NaN, rather than being presented as
corrected measurements. Explicit `outside="mask"`, `"clip"` or `"extrapolate"`
policies are available and recorded; choose them only deliberately.
`correct_displacement` subtracts a reference but does not flatten earlier data;
if you want the pre-contact segment displayed as zero, apply `zero_at` afterward,
as in your existing reduction script.

For an AUX sensor, calibrate from its original declared voltage channel:

```python
exp.calibrate(
    "ADC/AUX 6", using=calibration(AUX6_CALIBRATION_ID), output="pore_pressure",
)
```

Select calibration by sensor identity, electronics gain and configuration. The
original voltages stay visible; corrections overwrite working displacement
channels. Calling `save(exp)` exports current working channels, with revision
history and exact selected calibration snapshots in `experiment.json`.

## 5. Migrate units consistently

Replace both displacement names ending in `_mm` with `_um` throughout your script.
Replace explicit displacement `unit="mm"` conversions with `unit="um"`. Keep the
sample geometry's declared units accurate: `thickness=… , unit="mm"` is still
valid when your measured sample thickness is in mm. The API converts compatible
units internally; strain stays dimensionless. Velocity from the new displacement
channels is µm/s. Any constant stiffness supplied manually must retain its real
unit (`MPa/mm`, `kN/mm`, etc.); changing the displacement unit is not a reason to
relabel the same numerical coefficient.

A polynomial fit against displacement will now have µm-based coefficients, not
the previous mm-based coefficients. Review fit axes/labels and any literal
thresholds, plotting limits or manual calculations outside the API.

## 6. Test and replay

```bash
python -m xlookpy gui "/path/to/experiment/reduction.py"
# Or execute from fresh data:
python -m xlookpy run "/path/to/experiment/reduction.py"
# Reproduce using calibration snapshots, independent of later catalog additions:
python -m xlookpy run "/path/to/experiment/reduction.py" \
  --replay-manifest "/path/to/experiment/experiment.json"
```

Start with contact inspection, confirm a known force/displacement conversion,
then add the actual frame revisions and check corrected displacement. Nothing
in the empty catalog activates a correction automatically.
