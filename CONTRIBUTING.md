# Developing lookPy

`main` is the approved working application. The initial scientific/GUI baseline
is version 0.1.1a1: embedded Monokai editor and contact-onset zeroing. Do not
replace it with the rejected external-editor experiment.

## One change at a time

1. Describe the problem or requested behaviour in a GitHub issue.
2. Branch from an up-to-date main: `git switch -c feature/short-description`.
3. Make focused commits and update relevant documentation.
4. Run `python -m pytest -q` with GUI dependencies installed and
   `QT_QPA_PLATFORM=offscreen` when no display is available.
5. Push the branch and open a pull request. Explain the resulting behaviour,
   validation, operator choices, and any scientific algorithm differences.
6. Wait for automated checks and operator testing. A passing test is not
   scientific approval of a new correction or interface.
7. Merge only after acceptance. Keep a rejected experiment on its branch or in
   the closed pull request; do not overwrite the approved baseline.

The initial repository bootstrap is the exception to the branch/PR rule. Future
application changes follow this workflow. Branch-protection rules are an owner
setting; this document establishes policy and does not itself enforce it.

## Scientific behaviour

- Preserve original record IDs, raw channels, explicit units and provenance.
- Keep numerical functions independent of Qt widgets.
- Keep calibration functions separate from versioned calibration values.
- Record operator choices in the reduction script and experiment manifest.
- Do not silently change algorithms or choose new calibration revisions.
- Add meaningful numerical/behaviour tests for fixes and calculations.
- Use synthetic fixtures. Never commit real raw data or private calibration files.
- Do not copy C Xlook code or assets without reviewing their license separately.

## Versions and releases

`src/xlookpy/__init__.py` and `pyproject.toml` must agree. Tags use `v` plus the
application version, for example `v0.1.1a1`. Released tags are never moved or
reused. The first tag/release is created only after baseline CI passes.

Record user-facing changes in CHANGELOG.md. Keep the software version in
CITATION.cff aligned with the package version. Keep release notes concise and
state scientific limitations. The software and documentation use the
[Apache License 2.0](LICENSE). Keep third-party notices with material you add.

## Development installation

```bash
conda activate xlook
python -m pip install -e ".[gui,test]"
python -m pytest -q
```

Local source changes are used immediately by the editable installation. Reinstall
after changing dependency or package metadata. Experiment scripts should stay in
their own directories so updating this repository cannot overwrite operator work.
