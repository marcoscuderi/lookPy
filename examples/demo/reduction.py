"""Synthetic teaching experiment. All calibrations here are demonstration values.

Run using: python -m xlookpy run examples/demo/reduction.py
or open this file in the desktop workspace. Paths resolve beside this script.
"""


def reduce(session):
    # %% 1. Load signals. Units describe the values actually stored in the CSV.
    exp = session.load("raw.csv", units={
        "time": "s", "shear_voltage": "V", "normal_voltage": "V",
        "displacement_voltage": "V",
    })

    # %% 2. Operator choices: inclusive ORIGINAL zero-based record IDs.
    reference = exp.records(0, 0)
    analysis = exp.records(0, len(exp)-1)
    area_mm2 = 2500.0              # One 5 x 5 cm interface.
    shear_surfaces = 2            # Double direct shear; normal force uses ONE area.
    velocity_window_s = 0.20      # Full width, in seconds. Try 0.05, 0.2 and 1.0.

    # Exact revisions from the CENTRAL registry. These are SYNTHETIC calibrations.
    shear = session.calibration("demo/shear/2026-10-r1")
    normal = session.calibration("demo/normal/2026-10-r1")
    displacement = session.calibration("demo/displacement/2026-10-r1")
    frame = session.calibration("demo/frame/2026-10-r1")

    # Experiment-specific decisions, copied into experiment.json.
    session.config = {"geometry": "double direct shear", "area_mm2": area_mm2,
                      "shear_surfaces": shear_surfaces, "spring": "absent in synthetic example",
                      "layer_thickness_mm": None, "purpose": "synthetic teaching/test data"}

    # %% 3. Convert signals into force/displacement, with explicit calibration IDs.
    exp.calibrate("shear_voltage", using=shear, output="shear_force")
    exp.calibrate("normal_voltage", using=normal, output="normal_force")
    exp.calibrate("displacement_voltage", using=displacement, output="measured_displacement")

    # %% 4. Apply apparatus correction independently of sensor calibration.
    # Model e(F) is elastic deformation in mm, as a function of force in kN.
    # u_corrected = (u-u_ref) - (e(F)-e(F_ref)), with sign=-1.
    # sign=+1 is available for an opposite displacement convention.
    exp.correct_displacement("measured_displacement", force="shear_force", using=frame,
                             reference_record=reference.start, sign=-1, output="slip")
    exp.zero("measured_displacement", reference=reference, output="measured_relative")

    # %% 5. Stress, friction and velocity.
    exp.stress("shear_force", area_mm2=area_mm2, surfaces=shear_surfaces, output="shear_stress")
    exp.stress("normal_force", area_mm2=area_mm2, output="normal_stress")
    exp.friction("shear_stress", "normal_stress", records=analysis, min_normal_MPa=0.1)
    exp.derivative("slip", time="time", window_s=velocity_window_s,
                   min_points=5, max_gap_s=0.05, output="slip_velocity")

    # %% 6. Optional plot specifications saved in the manifest.
    # Open GUI tabs explicitly with New plot tab; use Refresh axes to update.
    exp.plot(x="time", left="shear_stress", right="normal_stress", title="Stresses")
    exp.plot(x="time", left="measured_relative", right="slip", title="Displacement correction")
    exp.plot(x="time", left="friction", right="slip_velocity", title="Friction and velocity")

    # Publication happens only after the WHOLE script succeeds.
    session.export(exp, channels=["time", "shear_force", "normal_force", "shear_stress",
                                 "normal_stress", "friction", "measured_relative", "slip", "slip_velocity"])
