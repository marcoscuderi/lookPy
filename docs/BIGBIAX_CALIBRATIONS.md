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
contains nine operator-supplied records: two load-cell calibrations, two main
displacement calibrations, one AUX LVDT calibration, and separate loading/unloading
deformation models for both rams. It is not installed or selected automatically.
Keep experiment-specific additions outside the checkout so Git updates cannot
replace them. To use the reviewed repository catalog explicitly, pass
`--registry calibrations/BigBiax.json` when launching from the repository root.

For a different location, add `--file "/path/to/BigBiax.json"` to catalog commands.
Launch the reduction with `--registry "/path/to/BigBiax.json"` (both GUI and CLI).
`XLOOKPY_CALIBRATIONS` may also name that file or a registry directory. Existing
individual-record registries remain supported.

The JSON structure is shown below with an empty records list for illustration:

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
| `acquisition` | `sensor` | V → kN or µm | Archive TDMS conversions or explicitly select a stable sensor calibration; the profile itself uses TDMS properties |
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
consistent physical zero. A constant additive term in the deformation model
e(F) cancels in e(F)-e(F_reference). An offset in the input force generally does
not cancel for nonlinear e(F). Use `sign=1` only if your displacement coordinate
requires adding apparatus deformation instead of subtracting it.

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
in the catalog activates a correction automatically.

## 7. Reviewed BigBiax catalog: load slopes and experiment baselines

The two published load-cell entries use these stable coefficients:

| Record ID | Slope (kN/V) | Catalog intercept (kN) |
|---|---:|---:|
| `BigBiax/frame/vertical/load/62_mm_LC` | 23.203 | 0 |
| `BigBiax/frame/horizontal/load/62_mm_LC` | 25.708 | 0 |

Electrical offsets are experiment-specific. Measure an actually unloaded
reference interval for each axis and compute `F = slope * (V - V0)`. Do not
remove a real contact preload from the force supplied to the apparatus model.
One reference corrects a constant baseline, not drift throughout a run.
The original imported load coefficients are retained as historical evidence in
`provenance.source_tdms_parameters`; they are not active intercepts.

The BigBiax profile still applies each TDMS header's coefficients by default.
To explicitly replace its working load channels using the catalog, insert
these operations immediately after loading, before contact zeroing or frame
correction. Set the four baseline record IDs to real unloaded intervals:

```python
# exp = load(RAW_FILE, profile="BigBiax") has already run.
exp.calibrate(
    "ADC/Vertical Load",
    using=calibration("BigBiax/frame/vertical/load/62_mm_LC"),
    output="vertical_load",
)
exp.zero("vertical_load", reference=exp.records(V_BASE_START, V_BASE_END))

exp.calibrate(
    "ADC/Horizontal Load",
    using=calibration("BigBiax/frame/horizontal/load/62_mm_LC"),
    output="horizontal_load",
)
exp.zero("horizontal_load", reference=exp.records(H_BASE_START, H_BASE_END))
```

`zero` subtracts the mean of the selected unloaded interval from the whole
working force channel; it does not flatten any segment. With zero catalog
intercept this is algebraically `slope * (V - mean(V_unloaded))`. Raw ADC
channels remain intact, and both calibration selection and baseline operation
are recorded in history. Calibration always starts from ADC voltages, so the
profile's earlier force conversion is replaced rather than calibrated twice.
If you need a separately contact-zeroed force for display, retain the physical
force for apparatus correction and give the display channel another name.
Saving the experiment retains the selected calibration snapshot and baseline
interval/offset in the reduction history. Changing this JSON alone does not
change an existing reduction script's execution.

The catalog sets the input range to `[-150, 200]` **V** for both 62 mm load
cells and `[0, 200]` **V** for the displacement and AUX sensors. The bounds
apply to the input voltage before conversion to force or displacement.

| Axis | Published branch models | Valid physical force | Displacement origin |
|---|---|---|---|
| Horizontal | `BigBiax/frame/horizontal/2026-07-16/loading/r1` and `unloading/r1` | 10–150 kN | e(10 kN) = 0 |
| Vertical | `BigBiax/frame/vertical/2026-07-16/loading/r1` and `unloading/r1` | 20–150 kN | e(20 kN) = 0 |

For unloading replace the final `loading/r1` path segments with `unloading/r1`.
Use an in-range frame reference and correction interval; an unloaded contact
record is outside these particular models. Branch origins are independent;
these polynomials are not an automatic hysteresis-switching model. Their
historical TDMS force intercepts remain in provenance to reproduce the fits.
Matching the physical unloaded force reference matters; matching historical
electrical intercept numbers between experiments is not required. Fixture
configuration and sensor/gain suitability still need to match the reduction.

## 8. Practical guide: enter and use linear and polynomial calibrations

This walkthrough combines complete JSON examples with the terminal answers that
create them. **All numerical values below are illustrative, not measured BigBiax
calibrations.** Use your actual coefficients, sensor identities, configurations,
calibration dates and independently established validity ranges for experiments.
The examples are documentation only; they are not installed automatically.

### A. Start the guided entry tool

With the calibration test branch installed, run:

```bash
conda activate xlook
python -m xlookpy catalog init
python -m xlookpy catalog add
```

`init` creates the catalog if necessary and preserves an existing one. By default,
entries are saved in `~/.xlookpy/calibrations/BigBiax.json`. You answer prompts in
the terminal; **you do not need to write JSON manually**. The manager supplies
`schema_version`, `apparatus` and `category` automatically.

### B. Linear example: voltage to force

For an illustrative low-gain vertical load cell:

`F [kN] = 20.0 * voltage [V] + 0.5`

At 2 V the converted force is 40.5 kN. The validity range below is in **volts**.
To enter this example, answer `catalog add` as follows, in prompt order:

| Prompt | Example answer |
|---|---|
| Purpose (acquisition / auxiliary / elastic) | `acquisition` |
| Permanent ID | `BigBiax/load/vertical/low/example-r1` |
| Sensor identity or frame axis | `Vertical load cell` |
| Apparatus / electronics configuration | `Example electronics configuration` |
| Calibration date YYYY-MM-DD | `2026-11-04` |
| Source measurement file / calibration report | `Illustrative calibration report` |
| Input unit | `V` |
| Output unit | `kN` |
| Model (linear / polynomial) | `linear` |
| Gain (low / high / explicit description) | `low` |
| Slope | `20.0` |
| Intercept | `0.5` |
| Minimum calibrated input | `0.0` |
| Maximum calibrated input | `10.0` |
| Notes (orientation, fit, limitations) | `EXAMPLE ONLY. Replace with measured coefficients and calibrated voltage range.` |

The resulting entry is:

```json
{
  "schema_version": 1,
  "id": "BigBiax/load/vertical/low/example-r1",
  "apparatus": "BigBiax",
  "purpose": "acquisition",
  "category": "sensor",
  "sensor": "Vertical load cell",
  "gain": "low",
  "configuration": "Example electronics configuration",
  "date": "2026-11-04",
  "source": "Illustrative calibration report",
  "input_unit": "V",
  "output_unit": "kN",
  "model": "linear",
  "parameters": {
    "slope": 20.0,
    "intercept": 0.5
  },
  "valid_range": [0.0, 10.0],
  "notes": "EXAMPLE ONLY. Replace with measured coefficients and calibrated voltage range."
}
```

For a main channel this entry archives the acquisition calibration. It does not
override the coefficients used by `load(RAW_FILE, profile="BigBiax")`, which reads
that experiment's TDMS properties. For an additional sensor calibrated during
reduction, select purpose `auxiliary`, give it its actual sensor ID, gain, units
and coefficients, and apply it through `exp.calibrate()` as shown in section 4.

### C. Polynomial example: force to apparatus deformation

For illustrative vertical apparatus deformation:

`e(F) [um] = 0.02 * F**2 + 1.5 * F`, with F in kN.

At 50 kN the apparatus deformation is 125 µm. This model describes **elastic
deformation e(F), not stiffness k(F)**. Its validity range is in **kN**.

Run `python -m xlookpy catalog add` again and enter:

| Prompt | Example answer |
|---|---|
| Purpose (acquisition / auxiliary / elastic) | `elastic` |
| Permanent ID | `BigBiax/frame/vertical/config_A/example-r1` |
| Sensor identity or frame axis | `Vertical apparatus deformation` |
| Apparatus / electronics configuration | `Example frame configuration A` |
| Calibration date YYYY-MM-DD | `2026-11-04` |
| Source measurement file / calibration report | `Illustrative apparatus calibration` |
| Input unit | `kN` |
| Output unit | `um` |
| Model (linear / polynomial) | `polynomial` |
| Coefficients, highest power FIRST, separated by spaces | `0.02 1.5 0.0` |
| Minimum calibrated input | `0.0` |
| Maximum calibrated input | `100.0` |
| Notes (orientation, fit, limitations) | `EXAMPLE ONLY. Polynomial describes elastic deformation e(F), not stiffness.` |

Enter coefficients **separated by spaces, without commas or brackets**, starting
with the highest power. `[a2, a1, a0]` in the generated JSON means
`a2*F**2 + a1*F + a0`. Elastic records have no sensor-gain prompt.

The resulting entry is:

```json
{
  "schema_version": 1,
  "id": "BigBiax/frame/vertical/config_A/example-r1",
  "apparatus": "BigBiax",
  "purpose": "elastic",
  "category": "apparatus",
  "sensor": "Vertical apparatus deformation",
  "configuration": "Example frame configuration A",
  "date": "2026-11-04",
  "source": "Illustrative apparatus calibration",
  "input_unit": "kN",
  "output_unit": "um",
  "model": "polynomial",
  "parameters": {
    "coefficients": [0.02, 1.5, 0.0]
  },
  "valid_range": [0.0, 100.0],
  "notes": "EXAMPLE ONLY. Polynomial describes elastic deformation e(F), not stiffness."
}
```

### D. Review, save and inspect

For either example, the manager validates the entry, prints its JSON and asks:

```text
Save this new revision? [y/N]:
```

Type `y` to append it to the catalog. Any other answer cancels. Invalid input also
leaves the catalog unchanged. These objects belong in the catalog's **`records`
list**; do not replace the whole catalog with a single entry. Alternatively, save
one object to its own JSON file and use `catalog import` to append it safely.

After entering the examples, inspect them with:

```bash
python -m xlookpy catalog list
python -m xlookpy catalog show BigBiax/load/vertical/low/example-r1
python -m xlookpy catalog curve BigBiax/load/vertical/low/example-r1 --points 6
python -m xlookpy catalog show BigBiax/frame/vertical/config_A/example-r1
python -m xlookpy catalog curve BigBiax/frame/vertical/config_A/example-r1 --points 5
```

`show` displays the definition and fingerprint. `curve` prints an input/output
table, not a plot. All validity limits are expressed in the record's input unit.

### E. Read acquisition coefficients from TDMS instead of typing them

For a real main-channel acquisition calibration:

```bash
python -m xlookpy catalog add \
  --tdms "/path/to/experiment.tdms" \
  --channel "Vertical Load"
```

The manager sets purpose `acquisition` and model `linear`, reads `Slope` and
`Intercept`, and records the source file path, SHA256 and ADC channel. You still
enter the permanent ID, sensor identity, configuration, calibration date, units,
gain, calibrated input range and notes. The source/model/coefficient prompts
are therefore omitted. The final review and `y` confirmation are unchanged.

### F. Use the selected apparatus revision in reduction.py

In your existing cell-based reduction script, after setting `RAW_FILE` and
picking `VERTICAL_CONTACT` as an original record ID:

```python
# %% Acquisition conversion: TDMS coefficients, kN and um
exp = load(RAW_FILE, profile="BigBiax")

# %% Apparatus correction: replace the example ID with your measured revision
frame = calibration("BigBiax/frame/vertical/config_A/example-r1")
exp.correct_displacement(
    "vertical_displacement_um",
    force="vertical_load",
    using=frame,
    reference_record=VERTICAL_CONTACT,
)

# %% Save current working channels and calibration history
save(exp)
```

This snippet shows the integration points, not a replacement for the complete
experiment reduction. Use your measured frame calibration for real analysis.
The default correction subtracts the **change in apparatus deformation since
contact**, retains displacement in µm and overwrites the working channel. Raw
ADC values remain available. Force values, including the reference, must lie
inside the calibrated range unless you deliberately select an explicit outside
policy. See section 4 for interval selection, both axes and sign conventions.

When a calibration changes, run `catalog add` with a **new revision ID**, such as
`r2`, and select that ID explicitly in new reductions. Retain the previous entry
for earlier experiments. The saved experiment manifest snapshots the definitions
actually used, allowing replay independently of later catalog additions.
