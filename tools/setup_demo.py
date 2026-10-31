"""Install clearly labelled demonstration calibrations in your central registry."""
from pathlib import Path
from xlookpy import Registry

registry = Registry()
for path in sorted((Path(__file__).resolve().parents[1]/"calibration_examples").glob("*.json")):
    cal = registry.import_file(path)
    print("Imported SYNTHETIC calibration:", cal.id)
print("Central registry:", registry.root)
print("Next: python -m xlookpy gui examples/demo/reduction.py")
