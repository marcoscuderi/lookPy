# rawPy workflow: function reference (0.2.0a1)

The scientific record is `reduction.py`, which defines `reduce(session)`.
Run all starts from the raw file. Operations create named channels without
replacing inputs; all derived channels appear in the GUI selectors. Parameters,
selections, fit diagnostics and models are saved in the manifest. The embedded
editor, manual tabs, axis refresh and original-record picking remain unchanged.

The complete executable example is `examples/rawpy_mock/reduction.py`.
Create its data and working copy with `tools/setup_rawpy_mock.py`; do not edit
tracked example scripts for your own experiments.

## Conventions

* Channel names, not arbitrary arrays, identify inputs.
* Transformations default to updating the working input when `output=` is omitted.
  A different output name keeps an intentional comparison. Original inputs are protected.
* `exp.records(a, b)` means inclusive ORIGINAL zero-based record IDs. Slicing
  preserves IDs; an ID is not elapsed time or the current array position.
* Operations return `exp` for chaining, except `fit` (diagnostic dictionary),
  `plot` (specification), `slice` (new experiment) and inspection methods.
* Units come from channel metadata; functions check dimensional compatibility.
  `unassigned` channels need an explicit acquisition conversion or declared units.
* NaN means undefined or unavailable. Friction is NaN outside valid loading;
  this avoids inventing zero friction or adding an arbitrary denominator epsilon.
* Computation never automatically opens plot windows. Use **New plot tab** and
  **Refresh axes**. `exp.plot` records an optional specification only.

## All public reduction operations

| Function | Purpose | Example inside `reduce(session)` |
|---|---|---|
| `session.load` | Load one source and fingerprint it | `exp = session.load("raw.csv", units={"time":"s", "force":"kN", "disp":"mm"})` |
| `session.calibration` | Select a central calibration revision or replay snapshot | `cal = session.calibration("biax/frame/r1")` |
| `session.export` | Select final experiment and export channels; publish only after success | `session.export(exp, channels=["time", "slip", "friction"])` |
| `exp.records` | Validate an inclusive original-record interval | `stage = exp.records(100, 500)` |
| `exp.slice` | Make an interval experiment retaining original IDs | `stage_exp = exp.slice(stage)` |
| `exp.convert_acquisition` | Apply custom TDMS Slope/Intercept once | `exp.convert_acquisition("ADC/Aux 6", unit="V", output="aux6_V")` |
| `exp.calibrate` | Apply a sensor calibration | `exp.calibrate("voltage", using=cal, output="force")` |
| `exp.convert` | Convert compatible units; optional sign/scale | `exp.convert("disp", unit="mm", scale=-1, output="disp_positive")` |
| `exp.zero` | Subtract finite interval mean without clipping | `exp.zero("force", reference=exp.records(100,100), output="force_relative")` |
| `exp.zero_at` | Set contact to zero; force earlier records to zero | `exp.zero_at("force", record=100, output="contact_force")` |
| `exp.shift` | Add a constant in specified units, optionally in an interval | `exp.shift("contact_force", value=.044, unit="kN", records=stage, output="gravity_force")` |
| `exp.offset` | Flatten selected interval at its first value; shift later samples | `exp.offset("disp", records=exp.records(200,205), output="repaired")` |
| `exp.mask` | Replace selected data with NaN, with a reason | `exp.mask("disp", records=stage, reason="Sensor dropout", output="disp_valid")` |
| `exp.stress` | Force divided by area and surface count, in MPa | `exp.stress("force", area_mm2=2500, surfaces=2, output="shear_stress")` |
| `exp.friction` | Shear/normal stress in valid loading | `exp.friction("shear_stress", "normal_stress", min_normal_MPa=.1, records=stage)` |
| `exp.correct_displacement` | Reference-relative elastic correction using a central apparatus record | `exp.correct_displacement("disp", force="force", using=cal, reference_record=100, output="slip")` |
| `exp.elastic_correct` | Explicit constant-stiffness correction | `exp.elastic_correct("disp", load="shear_stress", stiffness=100, stiffness_unit="MPa/mm", reference_record=100, output="slip")` |
| `exp.layer_thickness` | Reference thickness plus per-layer displacement change | `exp.layer_thickness("horizontal_corrected", reference_record=200, thickness=.8, layers=2, closure_sign=-1, output="thickness")` |
| `exp.geometrical_thinning` | Named rawPy triangular legacy recurrence | `exp.geometrical_thinning("disp", thickness="thickness", block_length=50, reference_record=200, output="rgt_thickness")` |
| `exp.shear_strain` | Accumulated slip increment / adjacent mean thickness | `exp.shear_strain("slip", thickness="thickness", reference_record=200)` |
| `exp.derivative` | Centred time-width local regression, actual timestamps | `exp.derivative("slip", time="time", window_s=.5, max_gap_s=.2, output="velocity")` |
| `exp.running_slope` | rawPy-style local slope: N samples each side | `exp.running_slope("slip", x="time", window=20, output="velocity_samples")` |
| `exp.low_pass` | Zero-phase Butterworth low-pass in one uniform-rate stage | `exp.low_pass("friction", cutoff_Hz=2, order=2, records=stage, output="mu_filtered")` |
| `exp.fit` | Interval polynomial fit and diagnostics | `fit = exp.fit("slip", "friction", records=stage, degree=1, output="fit_mu")` |
| `exp.plot` | Save plot specification, no automatic tabs | `exp.plot(x="time", left="friction", right="velocity")` |
| `exp.summary` | Channel units, validity counts and metadata | `print(exp.summary())` |

Examples in this table illustrate signatures; use channel names and intervals
that exist in your experiment. The complete mock script runs all these numerical
operations except central calibration, demonstrated in `examples/demo/reduction.py`.

`exp["slip"].values` gives a read-only NumPy vector; `.unit` and `.metadata` expose
its units and provenance. `exp.channels`, `exp.plot_columns`, `exp.record_ids`,
`exp.history`, `exp.metadata`, and `len(exp)` provide inspection. `session.config`
records experiment geometry, operator choices and bench measurements.

## rawPy mapping and intentional differences

| rawPy | pyXlook equivalent |
|---|---|
| `load_tdms` | `session.load("experiment.tdms")`, then explicit conversions |
| `load_data` | `session.load("data.txt", reader="text")` |
| `read_binary` | `session.load("legacy", reader="xlook_binary", dataendianness="little")` |
| `save_data` | `session.export(exp, channels=[...])` |
| `zero` | `exp.zero(... reference=exp.records(r,r))`; notebook pre-contact clipping uses `zero_at` |
| `offset` | `exp.offset(... records=exp.records(a,b))` |
| `ElasticCorrection` | `elastic_correct` for constant k; `correct_displacement` for registry models |
| `shear_strain` | `exp.shear_strain` |
| `filter_low_pass` | `exp.low_pass` |
| `slope` | `exp.fit` |
| `rslope` | `exp.running_slope`; time-width alternative: `exp.derivative` |
| `rgt` | `exp.geometrical_thinning(model="rawpy_triangular")` |
| `plot`, `Cursor` | Existing manual GUI tabs, zoom, dual axes, exact point/interval picking |
| `_binary_tuple_to_string` | Internal binary-header decoding; no public helper required |

Functionality is ported into the channel API; this is not a drop-in `import rawPy`
compatibility layer and existing rawPy notebooks require adapting calls.

### Loading, comments and export

* CSV: one comma-separated names header; declare all input units explicitly.
* BRAVA/rawPy text: tab-separated names, then tab-separated units, then numbers.
  The `.txt`, `.dat` and extensionless defaults select this reader. Unit overrides
  are allowed. `na`, `n/a` and `-` mean dimensionless; blank means unassigned.
* TDMS: loads every numeric ADC channel, retains custom acquisition coefficients,
  experiment properties and other groups (including comments) in metadata.
  No implicit Slope/Intercept conversion or unequal-length alignment is applied.
  Inspect stored values and metadata before assigning physical units.
* Binary: fixed big-endian header, little-endian float64 data by default; specify
  big-endian payload explicitly for old files. Short declared channels have NaN
  tails, not zeros. Truncated/inconsistent files raise errors. Synthetic fixtures
  test both payload endiannesses; validation on your archived files is still needed.
* `reduced.dat` always starts with original `record_id`, followed by selected
  channels, with separate names/units headers. Reloading it restores original IDs.
  Legacy text columns named `Record`/`Rec_n` remain ordinary channels: IDs denote
  their source rows rather than assuming a one-based instrument counter is zero-based.
* TDMS comments stay in their recorded time coordinate; if you zero acquisition
  time, apply that same reference explicitly when interpreting comment times.
* Calibration management remains `Registry.import_file`, `.get`, `.list`, and
  `Calibration.evaluate(values, outside="error"|"mask"|"clip")`. Normal reductions
  use `session.calibration` so used definitions enter the manifest. Prefer new
  revision IDs instead of changing an existing central record.

### Zeroing, offset repair and gravity

`zero` subtracts a mean and retains the full signal; `zero_at` sets earlier data
and the contact point to zero. `offset` uses two endpoints: it removes **all**
measured change between them, including real motion. Choose the shortest defensible
reset interval and inspect original versus repaired signals.

For gravity correction, use `shift` on `[contact,last_record]` after contact
zeroing. That deliberately adds a nonzero force at contact while leaving earlier
records zero. If your load-cell sign or geometry differs, choose the appropriate
signed value; `.044 kN` in the example is synthetic, not a laboratory default.

### Elastic correction, thickness and strain

Constant correction is `(u-u_ref) - (load-load_ref)/k`. A stress-based stiffness
is geometry-dependent; a force-based one uses force/length. Neither becomes a
sensor calibration. For nonlinear central models use `correct_displacement`,
which evaluates reference-relative e(F); it does not integrate a varying tangent
stiffness and does not model hysteresis.

Layer thickness is `h_ref + closure_sign*(u-u_ref)/layers`. Choose sign from the
actual coordinate; `-1` means positive displacement closes the assembly. Supply
**per-layer** reference thickness, e.g. `(bench_total-blocks-spacers)/2` for DDS.
Validate the bench values and original reference ID in your script.

Strain integrates `delta_slip / mean(h_previous,h_current)` and starts at zero at
its reference; earlier samples are NaN. A missing increment propagates NaN rather
than integrating across unknown data. Thickness must be positive. Explicitly
choose measured versus geometrically corrected thickness as input.

The only geometrical model is **rawpy_triangular**, the exact supplied recurrence:

```
corrected[0] = h[0]
D[i] = D[i-1] + h[i-1]*(d[i]-d[i-1])/(2*L)
corrected[i] = h[i-1] + D[i]
```

Its lagged `h[i-1]` is deliberately retained. Displacement increments are signed;
reversals are not converted to absolute slip. This is a legacy comparison model,
not a newly validated physical correction. Inputs from the chosen reference must
be finite and contiguous. No coefficients from the old notebook are promoted to
default laboratory calibrations.

### Slopes, fits and filtering

`running_slope(window=20)` fits up to 41 samples, with shorter edge windows.
It uses the actual X coordinates, so output units are Y/X; finite segments are
split at NaNs or missing records. A sample window has changing duration where the
sample rate changes. `derivative(window_s=.5)` instead keeps a physical time scale,
requires full-width edge support and can reject temporal gaps with `max_gap_s`.

`fit` uses stable centred/scaled polynomial regression, returns ascending original-X
coefficients `[intercept, slope, ...]`, RMSE, R², sample count and coefficient units.
The manifest also saves normalized coefficients/domain/window for stable evaluation.
R² is null for constant Y. Only selected finite X/Y pairs enter the fit; the fitted
channel is evaluated at finite X within the interval and is NaN outside it.

`low_pass` uses SOS forward/backward filtering, checks the actual sample intervals,
and rejects mixed rates, missing records, NaNs, non-increasing time or short data.
Select one acquisition-rate stage. It derives fs from time, or verifies supplied
`fs_Hz`. Default relative spacing tolerance is 0.001. `order` is the single-pass
Butterworth order; the forward/backward magnitude response is squared. There can
be transients at selected boundaries: compare input and output near both ends.
Values outside selection stay unchanged; a whole-signal filter includes the last
sample, correcting rawPy's default `[:-1]` omission.

Working-channel revisions and default compact export: [Mac update guide](testing/CHANNEL_UPDATES_MAC.md).
