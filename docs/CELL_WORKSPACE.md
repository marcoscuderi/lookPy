# Cell scripts and the interactive workspace

Open the [BigBiax template](../examples/bigbiax/reduction_step_by_step.py) for a
worked sequence. The workspace accepts top-level Python split by `# %%` comments.
`load`, `calibration`, `save`, `stop` and `session` are injected by the GUI/CLI
runner; imports of those four helpers from xlookpy also work within that runner.
These scripts require the workspace or `python -m xlookpy run script.py`, not
bare `python script.py` without a managed session.

## Smaller vocabulary

- `load(path, units=..., reader=...)`: same explicit readers as Session.load.
- `load(path, profile="BRAVA")`: explicitly select the existing BRAVA acquisition
  template mapping. This applies custom ADC Slope/Intercept, force outputs in kN,
  displacement in mm, horizontal sign -1 and time relative to the first record.
  It requires the five named ADC channels and their coefficients. Review these
  conventions against the actual file. The complete revisioned profile definition
  and fingerprint enter session.config; conversions enter operation history.
  Extra ADC channels remain available. No sensor or frame calibration is inferred.
- `calibration(id)`: select a versioned central calibration, with used snapshots
  preserved exactly as in the existing workflow.
- `save(exp, channels=[...])`: select final exports, not immediate publication.
- `stop()`: intentionally end inspection before later cells, replacing an early
  return previously used within reduce(session).
- `session.config`: optional explicit geometry, bench measurements and notes.

All numerical `exp` operations retain their current syntax and unit checks.
Old def reduce(session) scripts remain compatible. Convert to cell script creates
a new working copy; it never edits the source script in place.

## Execution state

New cells run in sequence. Run to here always rebuilds a prefix from raw input.
Rerunning an executed/edited cell also rebuilds a prefix, preventing duplicate
output names and accumulated corrections. Later results cease to be current.
Cells show pending, executed, outdated or failed. Input files changed outside the
script require Run to here / Run all to reload; this release does not watch raw
files for acquisition updates.

A QtConsole frontend and a separate IPython kernel share the same live namespace
for cells and trials. GUI plot widgets consume read-only experiment snapshots,
not kernel Python objects. Snapshot files are temporary; only successful fresh
Run all publishes the official versioned output files. The kernel is launched
with the application's sys.executable and is shut down when switching projects
or closing the GUI. Kernel failure requires Restart workspace.

Scripts and console commands may update derived working channels in place and
invalidate downstream derived channels. Original/raw inputs remain protected.
Every overwrite appends a numbered revision; old operation history is retained. The saved recipe is never automatically edited from console history.
All console commands mark the workspace exploratory, since arbitrary Python
mutations cannot be reliably classified. Insert accepted commands into the
script and validate with Run all. Rebuilding a prefix discards console-only state.

Failed cells may have made partial changes; the UI reports this rather than
claiming to roll back arbitrary Python objects. The previous published manifest
is retained. Prefix replay and a fresh kernel are the recovery mechanisms.
Arbitrary Python side effects (custom file writes, module globals, random state,
external processes) are outside transactional managed exports. For deterministic
random computations set the seed in the script. GUI Run all starts a new kernel
process as well as new script variables, excluding console-modified imports and
module globals. Prefix replay within a kernel still uses normal Python import
caching; use Restart workspace if exploratory module edits need clearing sooner.

## Scope

This is a `.py` cell editor plus IPython console, not a native `.ipynb` editor.
Cell source is ordinary Python; IPython magics belong in the exploratory console.
The accepted numerical functions and manual plot lifecycle are unchanged.
The replay implementation prioritizes transparent scientific state over fast
arbitrary-object checkpoints; rerunning a prefix can reload a large experiment.

See [compact channels and highlighting fixes](testing/CHANNEL_UPDATES_MAC.md) for 0.3.1a1.
