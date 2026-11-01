# Reduction API and execution rules

A reduction script defines `def reduce(session):`. Put experiment processing
inside that function. The application reads and executes that exact source from
fresh state on every Run all. Standard Python variables, branches and functions
are available. Paths passed to `session.load` resolve beside the script, not
against whichever directory launched the application.

## Session methods

| Call | Meaning |
|---|---|
| `session.load(path, units={...})` | Read one aligned CSV/ADC TDMS experiment |
| `session.calibration(id)` | Get an exact central revision, or saved snapshot in replay |
| `session.config = {...}` | Record JSON-compatible experiment-specific decisions |
| `session.export(exp, channels=[...])` | Choose final experiment/channels; publish after successful execution |

The central registry can be selected through a command argument, environment
variable, or the GUI folder selector. Calibration examples never become lab
defaults. Reader support is intentionally explicit: other TDMS group layouts,
asynchronous channels and Xlook binary inputs require additional adapters.

## Channel and selection methods

`exp.channels` lists measured/derived names (unchanged by plotting);
`exp.plot_columns` additionally includes virtual `record_id`, the original
zero-based row coordinate. It is accessible as `exp["record_id"]` and retains
original IDs after slicing. DAT exports already contain this first column;
explicit selection will not duplicate it.

`exp["force"].values` is a read-only NumPy array;
`.unit`, `.valid` and `.metadata` expose the channel's unit, finite-value mask
and provenance. The first version represents invalid samples with NaN plus
operation metadata/reasons, rather than a separate general quality-flag system.

`exp.records(start, end)` creates an inclusive selection using original,
zero-based record IDs. `exp.slice(selection)` returns an independent aligned
experiment retaining original IDs. Assign the sliced experiment to a variable
and export it explicitly. Slicing does not renumber records.

Every operation below adds a named output. Existing channels are never
overwritten. Each call returns the same experiment, but separate readable lines
are recommended for teaching.

| Method | Arguments and behaviour |
|---|---|
| `convert_acquisition(source, unit=..., output=...)` | Apply custom TDMS Slope/Intercept to the original reader values; unit is an operator declaration |
| `calibrate(source, using=cal, output=..., outside="error")` | Apply a central sensor calibration with input/output unit checks |
| `convert(source, unit=..., output=..., scale=1)` | Compatible unit conversion; use scale=-1 to reverse a coordinate |
| `zero(source, reference=selection, output=...)` | Subtract finite mean over reference records; no pre-reference clipping |
| `zero_at(source, record=contact_id, output=...)` | Subtract the exact selected contact sample; force all earlier original records to zero |
| `mask(source, records=selection, reason="...", output=...)` | Set an invalid interval to NaN without removing records |
| `stress(force, area_mm2=..., surfaces=1, output=...)` | Force divided by area × surfaces; result MPa |
| `friction(shear, normal, output="friction", min_normal_MPa=0.01, records=None)` | Stress ratio only where finite, inside selection, and normal stress strictly exceeds threshold |
| `correct_displacement(source, force=..., using=cal, reference_record=..., sign=-1, outside="error", records=None, output=...)` | Reference-relative correction from e(F); see calibration guide |
| `derivative(source, time="time", window_s=..., min_points=5, max_gap_s=None, records=None, output=...)` | Local linear-regression derivative, output source-unit/s |
| `plot(x="time", left=..., right=None, title=...)` | Record a plot specification in the manifest; GUI tabs are opened explicitly |

For your geometry use **2500 mm²** and **surfaces=2 for shear stress**. Normal
stress uses **surfaces=1**. A force or displacement zero is always your decision.
After contact, negative loads are retained. The explicit `zero_at()` operation
forces the pre-contact interval to zero; it does not delete rows or change
original channels. `zero()` remains available for average-based offsets and
time-origin selection, with its original behaviour unchanged.

For the ram-contact workflow:

```python
exp.zero_at("vertical_load", record=VERTICAL_CONTACT_RECORD, output="shear_force")
exp.zero_at("horizontal_load", record=HORIZONTAL_CONTACT_RECORD, output="normal_force")
exp.zero_at("vertical_displacement_mm", record=VERTICAL_CONTACT_RECORD, output="measured_relative")
```

The ID must exist and its source value must be finite. NaNs after contact stay
NaN; even missing pre-contact values become zero under the requested forced-zero
rule. Each operation records the contact ID, exact offset and count of forced
samples in the manifest. Read-only original values remain available for review.

## What derivative() calculates

For each time t, gather finite samples between t − window_s/2 and
t + window_s/2 within the same valid contiguous acquisition segment. Fit
`displacement = a + velocity * time` by ordinary least squares. Return the fitted
slope at t. Each sampled point has equal weight; dense acquisition intervals
therefore carry more weight than sparse intervals near a rate transition.

The window is in **seconds**, unlike Xlook's odd-sample-count running slope.
Do not assume these two operations give identical numbers. No automatic
resampling, velocity clipping or smoothing across missing data is performed.
The implementation uses recentered blocks with cumulative sums for efficiency
and numerical stability on long, densely sampled experiments.

At least `min_points` are required. Both temporal half-windows must fit inside
the segment: edges and boundaries become NaN. Missing values, excluded records,
discontinuities in original record IDs, and time gaps larger than an explicit
`max_gap_s` break segments. Time must be finite and strictly increasing.

Start with a window small compared with the event duration. Plot displacement
and velocity together, then compare several window widths. For loading-rate
estimates, use a larger width on selected loading intervals. For short slip
events, a shorter width preserves amplitude but increases noise. Derivatives of
uncorrected displacement include apparatus deformation.

## Execution and saving

The GUI launches the same command-line runner in a separate Python process.
Results return as ordinary manifest and data files. No Qt object enters the
numerical engine. Editing a script marks displayed results as outdated.

On success, the runner writes data/cache/manifest into a fresh run directory,
then atomically replaces `experiment.json`. On ordinary script/validation/export
failure it removes its staging outputs and leaves the previous manifest and
result files unchanged. Arbitrary Python side effects are outside this boundary.
Cancellation or power loss may leave an unused staging/run directory; the
manifest references only a completed published run. Results are checked against
their state-cache fingerprint when opened in the desktop.

In this release `# %%` markers organize the script for readers only: **Run
section is not implemented**. A general dependency graph, checkpoint reuse,
undo, multi-experiment sessions, and automatic script insertion are deferred.

## Manual plot controls

The desktop does not open exp.plot() specifications automatically. Existing
scripts remain valid and their requests stay in the manifest. Select axes and
use New plot tab to create a panel, or Refresh axes to replace the active
panel. Dropdown changes alone do not redraw. Existing user-created tabs refresh
on a rerun; opening another project starts with no tabs. These display choices
do not alter reduced arrays or scientific parameters.
