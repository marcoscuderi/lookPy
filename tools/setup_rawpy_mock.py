"""Create a repeatable synthetic experiment outside the application checkout."""
import argparse
from pathlib import Path
import shutil
import numpy as np


def create(destination):
    target = Path(destination).expanduser().resolve()
    source = Path(__file__).resolve().parents[1]/"examples/rawpy_mock/reduction.py"
    if any((target/name).exists() for name in ("raw.csv", "reduction.py")):
        raise FileExistsError("raw.csv or reduction.py already exists. Choose a fresh destination to preserve your edits.")
    target.mkdir(parents=True, exist_ok=True)
    # Rate changes at 10 s and 30 s; exact contact IDs 20 and 80.
    t = np.r_[np.arange(100)*.1, 10+np.arange(2000)*.01, 30+np.arange(200)*.05]
    normal = np.minimum(np.maximum(t-2, 0)*10, 50)
    shear = np.minimum(np.maximum(t-8, 0)*5, 60)
    slip = .02*np.maximum(t-8, 0)
    vertical = 1.+slip+shear/400.+.015*(t >= 20)
    # Horizontal coordinate decreases as the sample compacts.
    horizontal = 2.-.002*np.maximum(t-2, 0)+normal/800.
    rng = np.random.default_rng(754)
    # Load noise is zero exactly at the known contact points.
    noise = .008*np.sin(2*np.pi*15*t)+rng.normal(0, .001, len(t))
    noise[80] = 0
    np.savetxt(target/"raw.csv", np.column_stack([t, shear+.12+noise, normal+.3, vertical, horizontal]),
               delimiter=",", header="time,vertical_load,horizontal_load,vertical_displacement,horizontal_displacement", comments="")
    shutil.copyfile(source, target/"reduction.py")
    print("Created SYNTHETIC experiment:", target)
    print('Launch: python -m xlookpy gui "'+str(target/"reduction.py")+'"')
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    create(parser.parse_args().destination)
