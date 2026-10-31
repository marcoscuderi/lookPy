# Editor update — 29 October 2026

## What changed

- Monokai-inspired dark Python syntax colours, plus a Light option.
- Keywords, function names/calls, built-ins, strings, docstrings, comments,
  numbers and operators are differentiated.
- Line numbers and a subtle current-line highlight.
- A visible Font selector above the editor, defaulting to 14 pt.
- Standard zoom shortcuts while editing (Cmd +/− on Mac; Ctrl +/− elsewhere),
  and Cmd/Ctrl 0 to restore 14 pt.
- Font size and theme are remembered between sessions.
- Conda installation steps in README.

## Update your working editable installation

1. Close Xlook Python. Download and unzip this package into a temporary folder.
2. From its `xlook_python/src/xlookpy` folder, copy **both** files below into
   `src/xlookpy` inside your existing installed `xlook_python` folder:
   - `gui.py` — replaces the existing file.
   - `editor.py` — a new file.
3. Launch from your original installed folder:

```bash
conda activate xlook
cd "/path/to/your/installed/xlook_python"
python -m xlookpy gui examples/demo/reduction.py
```

No reinstall or additional dependency is needed. Do not replace your experiment
reduction scripts, raw data, calibration registry, or experiment manifests.
The earlier manual font change in gui.py is superseded by the visible Font
selector; choose your preferred size there once.

Alternatively, install this extracted source folder with
`python -m pip install -e ".[gui]"` from inside it. That moves the editable
installation to this folder, which you must then retain in a permanent location.

## Validation and scope

The original 13 engine/desktop tests and 4 new editor tests pass (17 total).
The editor preview was visually inspected with Qt offscreen on Linux. Native
Mac shortcuts and rendering still need the operator's test. Numerical functions
and the public reduction API are unchanged; the engine version remains
0.1.0a1 so the editor-only update does not invalidate existing replay manifests.

Syntax colouring is not autocompletion, linting or a full Sublime Text editor.
The rest of the desktop remains its existing style; the theme applies to the
source editor. Incomplete Python can have partial highlighting until completed.
