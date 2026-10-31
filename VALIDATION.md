# Validation of version 0.1.3a1 (trial branch)

Validation performed in Linux with Python 3.12. Automated desktop checks use
Qt's offscreen platform. A native macOS window has not been exercised here.

## Automated checks

**26 tests passed locally** after the manual-plotting update, including:

- Recovering prescribed slip from a nonlinear elastic displacement model on
  loading and unloading, including an opposite coordinate and N/kN conversion.
- Refusing invalid units, nonpositive compliance, repeated calibration and
  output-channel overwrites.
- Range error, masking and clipping policies.
- Double-direct-shear stress/friction and invalid-interval behaviour.
- Keeping original record IDs after slicing.
- Running-regression derivatives on irregular sample times, missing intervals,
  long dense records and explicit acquisition gaps.
- Central calibration revision protection and detection of external edits.
- Identical exported data on repeated fresh runs and replay without the registry.
- Retaining the previous manifest when a subsequent script fails.
- Full-resolution picking on either y-axis, independent visible-range scaling,
  and copying an inclusive interval expression.
- A real desktop worker process running the complete demo without opening
  automatic tabs; explicit New plot tab creates the requested plot.
- Python token colouring, comments/strings, complete and unfinished multiline
  strings, and non-BMP Unicode positioning.
- Display-only formatting that preserves source text and modified state.
- Font/theme controls and saved preferences, including font-action updates.
- Exact contact zeroing, forced pre-contact zeros, retained later negatives and
  missing samples, immutable source arrays and original IDs after slicing.
- Independent contacts for the two rams and refusal of invalid contact values.
- A generated TDMS through the revised template: initial contact-inspection
  mode, selected contact reduction, force/displacement zeros and optional
  elastic correction with saved calibration provenance.

The test suite is included in `tests/`. It tests scientific invariants and
execution behaviour, rather than treating GUI appearance as numerical proof.

Additional plotting checks cover in-place refresh, retained X zoom, original
row/time plotting after slicing, linked axes after X changes, reruns that update
only user tabs, disabled controls before reduction, and record_id export without
duplicate columns. Native Mac interaction still needs the operator test.

## Actual laboratory input

In the original numerical validation, the template was executed on
`eq_phys_demo.tdms`, all **728,939 records**. The editor update changes no
numerical modules; this full-file check was not repeated for the visual change.
Acquisition conversion and stress calculations were compared independently with
the raw TDMS arrays and their coefficients. Velocity at representative records
was compared with direct local least-squares fits. See
`validation/real_data_check.json` for counts, raw fingerprint and numerical
comparison results.

The desktop successfully loaded the complete experiment, its metadata and
three dual-axis plots. Synthetic and actual-data windows were rendered and
visually inspected offscreen. Source data and raw input bytes were unchanged.

Placeholder zero references were used for this test. Apparatus correction was
disabled. These checks establish software behaviour, not the scientific
appropriateness of those choices for the experiment.

## Packaging and dependency choices

A Python wheel was built successfully from `pyproject.toml`. The desktop
dependencies are pinned to the tested PySide6 6.8.3 / PyQtGraph 0.14.0
combination. Core dependency versions used in validation are listed in
`requirements-tested.txt`; each execution manifest records its numerical
dependency versions. Native desktop behaviour and installation still need the
first operator test on your Mac.

## Not yet validated or implemented

This is not a command-for-command Xlook port. Its e(F) apparatus correction
and seconds-based running-regression derivative have their own documented
definitions. Exact numerical compatibility with historical Xlook reduction
recipes is a subsequent validation stage against the compiled C outputs.

Mechanical-stage stitching, hysteresis, layer-thickness/strain reduction,
automatic calibration fitting, publication figure export, section execution,
the command console and stick-slip catalogues are deferred. Rate-and-state
forward and inverse modelling are outside the current scope.
