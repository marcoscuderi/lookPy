# Test the cell editor and IPython workspace on your real experiment

Branch: `feature/cell-console-workspace`. Version: **0.3.0a1**.
The accepted rawPy analysis functions are now on main (PR #4). This workspace
branch is deliberately unmerged until you validate it. No new demonstration
experiment is required: use your current real-experiment reduction script.

## 1. Select and install this test branch

Close pyXlook. In Terminal, using your actual checkout location:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git status
```

If tracked files have edits, preserve them before switching. Then:

```bash
git fetch origin
git switch feature/cell-console-workspace
git pull --ff-only
python -m pip install -e ".[gui,test]"
python -c "import xlookpy; print(xlookpy.__version__); print(xlookpy.__file__)"
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Expect `0.3.0a1` and a module path within this checkout. Reinstallation adds
QtConsole/IPykernel; it uses Python from your active Conda environment. You do
not need a browser notebook server or a separate Jupyter environment.

## 2. Open and convert your working script

Keep your experiment folder outside the application repository:

```bash
python -m xlookpy gui "/full/path/to/your/experiment/reduction.py"
```

For a script containing `def reduce(session)`, click **Convert to cell script**.
The application opens a NEW file alongside it, usually `reduction_cells.py`.
If that name exists, a numbered name is chosen. The original file is not
modified. RAW_FILE, contact IDs, geometry, corrections, comments and relative
paths are retained. The function wrapper is removed; `session.load/export/
calibration` calls become `load/save/calibration`. Early inspection returns
become `stop()`.

The converter accepts the existing straightforward templates, not every
possible Python program. It refuses unfamiliar constructs instead of silently
rewriting them. A conversion refusal does not change your original file.
Legacy scripts remain runnable using the original Run all batch workflow.

Review the converted script before execution. Every **top-level** `# %%` or
`#%%` comment is a cell boundary. A preamble containing imports/constants is
shown as **Setup**. Markers inside strings or indented blocks are not boundaries.

## 3. Execute your experiment in cells

1. Click the Setup cell in the cell list. Click **Run cell**, or press
   **Shift+Enter** while the editor has focus. The cursor advances after success.
2. Run the loading/conversion cell. The first operation starts a separate
   IPython kernel; your stored/physical channels appear in the selectors.
3. Make a plot with **New plot tab**. Picking and **Refresh axes** work as before.
4. Continue through contact zeroing, corrections, stress/friction and analysis.
5. At any later cell, **Run to here** rebuilds from raw data through that cell.
6. Change a contact or earlier parameter. Later cell labels become outdated.
   Run to here at the analysis cell to rebuild with the revised choice.

New cells run sequentially in the live namespace. Skipping unexecuted earlier
cells is refused with a suggestion to use Run to here. Rerunning an earlier cell
rebuilds the prefix and invalidates later results rather than accumulating
corrections. This may reload a large TDMS; it favors predictable state in this
first implementation over arbitrary Python-object checkpoints.

If the existing script stops for contact inspection, later cells are not run.
Pick contacts, edit their constants, then use Run to here. Save is the ordinary
editor save; it does not validate or publish numerical results.

## 4. Explore in IPython

The **IPython workspace** dock shares `exp`, variables and helpers with cells.
Use its Start IPython button if it has not started yet. Completion, history and
help come from IPython, e.g. type `exp.` and press Tab, or enter `exp.running_slope?`.
The Execution log dock also receives output and tracebacks.

Use your real slip channel name and try a new velocity window:

```python
exp.running_slope("slip", x="time", window=40, output="velocity_trial")
```

The trial becomes a selectable plotting channel. If your script calls the slip
channel `measured_relative` or `elastic_relative`, use that name instead.
Repeat the command with another window and the same trial output: derived
outputs may be replaced in the console. Raw channels cannot be overwritten.
Derived channels that depend on a replaced channel are removed, so they cannot
silently remain current. Arbitrary Python variables holding old arrays are not
automatically rewritten: use the current `exp` channels after an edit.

Every console command is conservatively marked exploratory, including inspection
commands. Select an accepted submitted command in the history dropdown and click
**Insert command into script**. It is inserted at the end of the editor line
containing the cursor; it is neither saved nor executed automatically. Put it
at the correct top-level position in the desired cell. Remove a superseded old
call if both would create the same output channel during Run all.

Run cell / Run to here after console trials rebuilds the script prefix and
**discards console-only variables and changes**. Add wanted choices to the script
first. Console history is for exploration, not an implicit reduction recipe.

## 5. Validate and publish

Click **Run all**. The GUI saves the editor source, starts a fresh kernel process
and executes it from a fresh workspace. `save(exp, channels=[...])` selects exports; publication happens only
after the complete fresh execution succeeds. The displayed badge becomes
**Validated**. The exact source, parameters, calibrations and outputs are saved
using the same manifest/results workflow as before.

Cells and console trials do NOT publish `experiment.json` or reduced.dat.
If a cell/console fails, its workspace can be partially modified and the badge
says so. Previously published results remain on disk. Use Run to here or
Restart workspace to rebuild a known state. Cancel also interrupts a running
kernel calculation. Python writes you explicitly perform outside the managed
export API are ordinary Python side effects, not automatically reversible.

Restart workspace clears live variables, cell execution state and plot tabs;
it does not delete raw files or published results. Opening another experiment or
closing the application shuts down its kernel. Linux/macOS communicate through
local IPC sockets; the kernel uses the same Python executable as the application.

## 6. Real-experiment acceptance checklist

- Converted and original scripts produce the same selected reduced values
  for identical parameters (compare the versioned reduced.dat outputs).
- Run a loading cell, plot your real loads and copy the correct contact IDs.
- Change one contact and Run to here; later results update without cumulative zeroing.
- Trial a velocity window in the console and see its channel in plotting selectors.
- Insert the accepted command at the right cell, save, Run all; reproduce it
  without relying on console-only variables.
- Verify that a failed console command leaves the prior experiment.json unchanged.
- Check completion, font size, Shift+Enter, interruption and kernel shutdown on Mac.

## 7. Return to accepted main

Close the GUI:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git switch main
git pull --ff-only
python -m pip install -e ".[gui,test]"
python -m xlookpy gui "/full/path/to/your/experiment/reduction.py"
```

Use the original `def reduce(session)` script on main; cell syntax requires the
test branch. No application files need downloading or manual replacement.
