# Changelog

## 0.2.0a1 — rawPy workflow test version

- Add offset repair, constant shifts/stiffness correction, layer thickness, strain,
  explicit legacy geometrical thinning, sample-window running slopes, interval
  polynomial fitting and SOS low-pass filtering. Preserve inputs and record parameters.
- Add BRAVA/rawPy two-header text and legacy Xlook binary readers, including
  endian selection and explicit missing tails. Round-trip exported original IDs.
- Add deterministic mock experiment, complete function reference and Mac test guide.
- Add SciPy dependency and record its version in manifests.
- Keep accepted embedded editor, contact zero and manual plotting behaviour.

## Unreleased

## 0.1.3a1 — manual plotting (under operator review)

- No automatic plot tabs on loading/reducing, including legacy script plot requests.
- Original row number `record_id` is selectable for plotting and remains stable after slicing.
- Refresh axes replaces the active plot in place; New plot tab is the explicit way to add a plot.
- Unchanged X retains zoom; changing X resets its range and updates axis links.
- Reruns update existing user tabs without opening additional plots.
- Embedded editor, contact-zero calculations and calibration workflow retained.
- Detailed Mac test procedure included; 26 automated tests.

Main and the baseline tag stay unchanged until operator acceptance.

## 0.1.1a1 — approved baseline

- Embedded Python editor with Monokai/Light themes and saved font-size controls.
- Exact picked-contact zeroing for each ram: pre-contact values forced to zero,
  selected sample zero, subsequent measured changes retained.
- Contact-inspection mode before the operator supplies contact record IDs.
- Explicit sensor calibration and independent elastic displacement correction.
- Dual-axis plotting, full-resolution point picking and interval copying.
- Configurable running-regression velocity estimate and manifest exports.
- 20 automated tests in the approved baseline.

## Repository bootstrap — 2026-10-31

- Imported the approved 0.1.1a1 source without changing application modules.
- Added Conda/Git installation and rollback instructions, contribution policy,
  issue/PR templates and Linux/macOS test automation.
- Added immutable baseline release automation after successful tests on main.
- Kept the Python package/import/command name `xlookpy`; repository name is lookPy.

The experimental external-editor 0.1.2a1 package was rejected and is not the
starting point of this repository.
