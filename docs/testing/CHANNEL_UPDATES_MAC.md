# Test highlighting and compact working channels (0.3.1a1)

These fixes update `feature/cell-console-workspace` (PR #5). Main remains the
accepted numerical baseline until you validate the workspace changes.

## Update on Mac

Close pyXlook and run from your application checkout:

```bash
conda activate xlook
cd "$HOME/Code/lookPy"
git status
git fetch origin
git switch feature/cell-console-workspace
git pull --ff-only
python -m pip install -e ".[gui,test]"
python -c "import xlookpy; print(xlookpy.__version__); print(xlookpy.__file__)"
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m xlookpy gui "/full/path/to/your/experiment/reduction_cells.py"
```

Use your actual paths. If git status shows modified tracked files, preserve them
before switching. Expected version is `0.3.1a1`. Re-run the experiment: an old
cached manifest still displays the channels it previously saved until rerun.

## 1. Highlighting

Run cells and Run to here several times. Insert/delete lines above comments,
edit a multiline string, undo edits, insert a console command, and run again.
Code should retain its current token colours: comments italic/muted, numbers
purple, keywords pink, ordinary variables regular light text in Monokai.
Changing source or execution focus must not move comment formatting onto code.
No highlighting action should modify source, cursor selections or undo history.

## 2. Compact BRAVA load

With `exp = load(RAW_FILE, profile="BRAVA")`, selectors should show:

- All original `ADC/...` channels, including recorded AUX channels, plus record_id.
- `time`, `vertical_load`, `horizontal_load`, `vertical_displacement_mm`,
  `horizontal_displacement_mm`.
- Additional final quantities only as your script calculates them.

No `absolute_time`, `vertical_displacement_um` or `horizontal_displacement_um`
intermediate is created by profile revision 2. Existing final profile names,
units, signs and numerical values are retained. Revision 1 intermediate names
are no longer part of the profile interface.

## 3. Update the script to work on the same channel

Previously, separate output names deliberately created separate channels:

```python
exp.zero_at("vertical_displacement_mm", record=VERTICAL_CONTACT,
            output="loadpoint_displacement")
```

For a single evolving working channel, use:

```python
exp.convert("vertical_displacement_mm", unit="mm", scale=SHEAR_DISPLACEMENT_SIGN)
exp.zero_at("vertical_displacement_mm", record=VERTICAL_CONTACT)

for interval in SHEAR_OFFSET_INTERVALS:
    exp.offset("vertical_displacement_mm", records=exp.records(*interval))
```

Point your later source variables at that same working name:

```python
loadpoint_channel = "vertical_displacement_mm"
slip_channel = "vertical_displacement_mm"
thickness_displacement = "horizontal_displacement_mm"
```

Apply horizontal sign/zero/offset operations in the same way. For constant-k
vertical correction, using YOUR confirmed stiffness:

```python
exp.elastic_correct("vertical_displacement_mm", load="shear_stress",
                    stiffness=K_VERTICAL_MPA_PER_MM, stiffness_unit="MPa/mm",
                    reference_record=VERTICAL_CONTACT)
```

For a registry apparatus calibration instead:

```python
exp.correct_displacement("vertical_displacement_mm", force="shear_force",
                         using=calibration(VERTICAL_FRAME_ID),
                         reference_record=VERTICAL_CONTACT, sign=-1)
exp.zero_at("vertical_displacement_mm", record=VERTICAL_CONTACT)
```

Choose one correction method, matching your existing geometry and coordinate
convention. If your force channel is named vertical_load, use that actual name
instead of shear_force. Apply load zeroing/gravity correction before stress and
frame correction, as in your current scientific workflow.

Omitting output updates the working input for convert, zero, zero_at, shift,
offset, mask, elastic_correct, correct_displacement and low_pass. Explicit
`output="same_name"` does the same. Supplying a DIFFERENT output intentionally
retains a comparison branch. Old scripts that explicitly name many intermediates
still request those branches: update their sequential calls as above to remove
that clutter. There is no automatic renaming/reinterpretation of your script.

Raw input channels, including all original ADC channels, cannot be overwritten.
New physical quantities such as stress, friction, strain and velocity still have
their own names. Do not replace displacement with its derivative if you still
need displacement later; both are distinct final quantities.

An in-place change invalidates downstream derived channels calculated from its
old revision. Recalculate them or use Run to here. If you need an uncorrected
comparison after updating displacement, its source is the original ADC channel;
create an explicitly named comparison before processing if required.

## 4. Export and inspect history

Use `save(exp)` to export current working channels automatically. The text file
has one record_id column and one column per current working channel. Original
ADC inputs stay visible in the GUI/state cache but are omitted from this default
reduced text export. An explicit channel list can select quantities or include
original ADC data if you ask for them.

Run all and inspect the latest reduced.dat and experiment.json. Successive
operations on the same output name must all remain in `operations`, each with a
revision, input_revisions and (when replacing) replaces_revision. Invalidated
channels and their old operations remain in the audit log; obsolete value arrays
do not remain as duplicate channel columns. The current channel metadata identifies
its latest revision. The raw source fingerprint, exact script and calibration
snapshots still allow reconstruction of earlier processing steps.

Console commands also update the current working values. Repeating a correction
there acts on the already modified data; use Run to here to rebuild the script
prefix when comparing choices, and Run all for a fresh published result.

## Return to the previous workspace implementation

Close the application:

```bash
git switch --detach 8bc72e9934ce55dd121dbf852a9a92a4803fad5c
python -m pip install -e ".[gui,test]"
```

Use your previous script with explicit output names on that version. Return to
this test branch with `git switch feature/cell-console-workspace` and reinstall.
