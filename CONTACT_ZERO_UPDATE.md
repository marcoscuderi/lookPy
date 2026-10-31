# Contact-onset zeroing — version 0.1.1a1

## The workflow you requested

Pick where each ram touches the sample and force starts rising. Use the copied
original record ID as the contact setting. These are single integers:

```python
VERTICAL_CONTACT_RECORD = 1200
HORIZONTAL_CONTACT_RECORD = 850
```

The values above are examples, not selected records for your experiment.

At/after contact the new operation calculates `signal - signal_at_contact`.
All earlier samples become zero. The picked sample itself is exactly zero.
Later unloading, negative changes and missing values are not clipped away.
Original channels and record IDs remain available unchanged.

Both force and displacement use the corresponding ram's contact. There is no
separate displacement interval in the standard template. Optional elastic
correction has its own reference/stage choices, as before; the standard
whole-experiment correction is also reanchored to vertical contact.

## Install into your existing Conda setup

1. Close Xlook Python. Unzip this package to a temporary folder.
2. Copy the new `src/xlookpy` folder contents and `pyproject.toml` into your
   installed `xlook_python` folder, replacing application files only. This
   preserves the Monokai editor and adds the numerical operation/version.
3. In Terminal, from the installed folder:

```bash
conda activate xlook
cd "/path/to/your/installed/xlook_python"
python -m pip install -e ".[gui]"
python -m xlookpy gui
```

The existing Conda environment is reused. No calibration registry or raw input
needs replacing. Updating the application alone does not rewrite old reduction
scripts: those keep their existing `zero()` calls until you change them.

## Use the new experiment template

Use `examples/your_experiment/reduction.py` as the starting script in your
experiment folder. Keep your old script as a backup and carry over your actual
RAW_FILE, geometry, calibration choices and analysis parameters.

1. Leave both contact settings as `None` and Run all.
2. Original physical signals are available. On the manual-plotting branch, select
   X=time and the vertical/horizontal load channels, then click New plot tab. This is inspection
   only; stress, friction and velocity have not yet been computed. The log and
   manifest explicitly identify this mode. Its data export contains inspection
   signals, not reduced stresses.
3. Click the vertical contact point and paste the copied record ID into
   VERTICAL_CONTACT_RECORD. Repeat independently for HORIZONTAL_CONTACT_RECORD.
4. Run all again. Original load plots remain available, along with the reduced
   stress/friction/displacement/velocity plots.

The old VERTICAL_REFERENCE/HORIZONTAL_REFERENCE/DISPLACEMENT_REFERENCE averaging
intervals are no longer used in this template. Contact settings are neither
seconds nor two-number intervals.

## Adapting an existing custom script

Replace force/displacement mean-reference calls with explicit contact calls:

```python
exp.zero_at("vertical_load", record=VERTICAL_CONTACT_RECORD, output="shear_force")
exp.zero_at("horizontal_load", record=HORIZONTAL_CONTACT_RECORD, output="normal_force")
exp.zero_at("vertical_displacement_mm", record=VERTICAL_CONTACT_RECORD, output="measured_relative")
```

Use the new template for the complete two-ram displacement and correction
sequence. `zero()` is retained unchanged for other purposes such as setting
the time origin. One-point baseline uncertainty is the uncertainty of that
sample; no hidden averaging is performed.

## Derived quantities and reproducibility

Force/displacement zeroing does not make friction valid without a normal load:
that remains NaN below the operator's threshold. The template starts velocity
fit windows after vertical contact; unsupported edge estimates are NaN, not
artificial pre-contact velocity. Outside a selected mechanical correction stage,
corrected displacement remains NaN as documented.

The manifest stores both contact IDs, the exact offset of every zeroed channel,
the forced-zero rule, sample count, full script, calibrations and software
version. Version 0.1.1a1 adds this numerical operation. Old manifests remain
viewable; strict replay continues to require their recorded engine version.

All 20 automated tests pass, including the full generated-TDMS template with
different ram contacts and an optional nonlinear e(F) correction. No new contact
points have been inferred or scientifically approved for your actual experiment.
