# Changelog

## Unreleased

Future changes will be developed on branches, reviewed in pull requests, and
accepted after operator testing. Numerical and GUI baseline remains 0.1.1a1.

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
