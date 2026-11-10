# lookPy first working release

Draft release notes for a GitHub source release. The historical baseline
is tagged `v0.1.1a1`.

- Run a complete reduction or execute a Python script cell by cell. The
  embedded IPython console shares the workspace for exploratory commands.
- Reduce BigBiax ADC data with the step-by-step template and versioned
  calibration catalog. The workflow covers load and displacement calibration,
  contact and baseline corrections, frame compliance, stress, friction,
  thickness, strain, and velocity.
- Explore dual-axis plots, pick original record IDs, fit linear or polynomial
  trends, and copy a detrending command into the reduction script.
- Publish tab-separated data and a manifest for each run. Reopen saved data for
  plotting or continue analysis from the export without reading the raw TDMS.

## Installation and use

Install from the source checkout using the [quick start](../../README.md#install-with-anaconda).
The [operator guide](../OPERATOR_GUIDE.md) covers inspection, reduction, and
reopening saved results. The [BigBiax calibration guide](../BIGBIAX_CALIBRATIONS.md)
covers model selection and calibration provenance.

## Scope

The TDMS reader expects aligned ADC channels. BigBiax calibration IDs, geometry,
contact records and correction intervals must match the experiment. Legacy
Python batch reductions remain supported. The original Xlook command language,
rate-and-state inversion, and automatic event catalogues are outside this release.

Manifest replay requires the recorded xlookpy version and exact script. Saved
data can also be inspected directly from the exported table.
