# Test manual plotting on your Mac

Feature branch: **feature/manual-plot-tabs**

Trial application version: **0.1.3a1**. Main remains the approved 0.1.1a1.
The rejected external-editor experiment used 0.1.2a1; that number is not reused.
The embedded Monokai editor and contact-zero workflow are retained.

## 1. Close the app and check your working copy

In Terminal:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git status
```

If you cloned elsewhere, replace the cd path. Continue when Git says
`working tree clean`. If it lists modified files, preserve them and send the
output before proceeding. Do not use reset --hard or delete local work.

## 2. Select the test branch

```bash
git fetch origin
git switch feature/manual-plot-tabs
git pull --ff-only
python -m pip install -e ".[gui,test]"
```

On the first switch, Git should create a local tracking branch from the remote
branch. On later test updates, the same commands update it. If Git reports an
ambiguity or conflicting local changes, stop and send the message.

Verify the version and installation:

```bash
python -c "import xlookpy; print(xlookpy.__version__); print(xlookpy.__file__)"
```

Expected: `0.1.3a1`, with the module path inside your Git checkout's
`src/xlookpy` folder. No new Conda environment is needed.

## 3. Run automated checks

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Expected for this branch: **26 passed**. The offscreen setting applies only to
this command, so your normal GUI launch below will still show a window.

## 4. Make a working example outside Git

```bash
python tools/setup_demo.py
mkdir -p "$HOME/lookPy-tests/manual-plot-tabs"
cp -n examples/demo/raw.csv examples/demo/reduction.py "$HOME/lookPy-tests/manual-plot-tabs/"
python -m xlookpy gui "$HOME/lookPy-tests/manual-plot-tabs/reduction.py"
```

`cp -n` preserves an existing working example if you repeat these instructions.
This example uses synthetic data/calibrations. It does not change laboratory
calibration records. A real-data test can use a copied reduction.py in a test
directory with RAW_FILE pointing at the original TDMS by its full path.

## 5. Operator acceptance checklist

1. **No automatic plots.** Click Run all. The editor and experiment information
   remain available, but no plot tab opens. This also applies when reopening
   saved results or running old scripts with exp.plot() requests.
2. **Original row column.** Find `record_id` in the channel list and all three
   axis selectors. It is the original zero-based row number, not seconds. It
   remains the original ID after slicing an experiment.
3. **Create the first plot.** Select X=`time`, LEFT=`record_id`, RIGHT=`(none)`.
   Click **New plot tab**. Exactly one tab opens. In the synthetic demo the
   slope changes around 80 and 100 s because its sampling rate changes from
   100 to 500 and back to 100 samples/s. Real experiments use their own rates.
4. **Refresh instead of adding.** Zoom into part of that time range. Select
   LEFT=`shear_stress` and RIGHT=`normal_stress`. Dropdown selection alone should
   not change the plot. Click **Refresh axes**: the active plot changes, the tab
   count stays one, and the visible time range is retained.
5. **Change the X variable.** Select X=`record_id`, LEFT=`time`, RIGHT=`(none)`
   and Refresh axes. The same tab now uses row numbers. Changing X resets the
   X range because the coordinate/units changed. The old right-hand curve is gone.
6. **Add a separate plot deliberately.** Choose X=`time`, LEFT=`friction`,
   RIGHT=`slip_velocity` and click New plot tab. There are now two tabs, and the
   first keeps its own axes. Switching tabs restores their selector choices.
7. **Picking.** Click near a curve. The exact original row is copied and its
   coordinates appear in the log. Pick two points and copy the interval. Refresh
   a plot and verify previous picked markers are cleared, avoiding stale picks.
8. **Rerun and close.** Run all again: only your two user-created tabs are
   refreshed; no additional script-generated tabs appear. Close both tabs, run
   again, and verify the area stays empty until New plot tab is clicked.

The existing dual-axis auto-scaling and linked-X controls should still work.
Only panels with the same X variable are linked. Refresh with unchanged X keeps
its zoom; switching X resets it. With automatic Y fitting disabled, manually
chosen Y limits remain under operator control.

## 6. Report the result

Open the pull request linked with this update. You can comment there or reply in
our conversation. Include:

- Mac model/macOS, installed version and test result.
- Which checklist item failed, or confirmation that all behaved as expected.
- Error text or a screenshot where helpful.
- Whether you accept this plotting workflow or want changes before merging.

Do not merge the pull request just to install/test the branch. Main is unchanged
until the change is accepted. No baseline tag is moved or replaced.

## 7. Return to the approved version

Close the app first:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git switch main
python -m pip install -e ".[gui,test]"
python -m xlookpy gui
```

Before acceptance/merge, main reports `0.1.1a1` and has the previous automatic
plot behaviour. If you need the exact historical version after main later
advances, use `git switch --detach v0.1.1a1` instead. Existing experiment files
and calibration registry do not move when switching application branches.
