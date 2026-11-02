"""Complete rawPy-style MOCK reduction: all constants are SYNTHETIC.

Create working files outside the checkout with tools/setup_rawpy_mock.py.
Set a contact to None to inspect stored signals before choosing contact IDs.
Do not transfer these stiffnesses, geometry or record IDs to a real experiment.
"""
VERTICAL_CONTACT_RECORD = 80      # Synthetic t=8 s; set None to practise picking.
HORIZONTAL_CONTACT_RECORD = 20    # Synthetic t=2 s.
THICKNESS_REFERENCE_RECORD = 200  # Synthetic t=11 s.


def reduce(session):
    # %% 1. Load. Engineering units are ALREADY stored in this synthetic CSV.
    exp = session.load("raw.csv", units={
        "time": "s", "vertical_load": "kN", "horizontal_load": "kN",
        "vertical_displacement": "mm", "horizontal_displacement": "mm"})
    session.config = {"purpose": "SYNTHETIC rawPy workflow validation",
                      "area_mm2": 2500., "shear_surfaces": 2,
                      "vertical_contact": VERTICAL_CONTACT_RECORD,
                      "horizontal_contact": HORIZONTAL_CONTACT_RECORD,
                      "thickness_reference": THICKNESS_REFERENCE_RECORD,
                      "thickness_basis": "0.8 mm per layer at reference; synthetic bench measurement"}
    if VERTICAL_CONTACT_RECORD is None or HORIZONTAL_CONTACT_RECORD is None:
        print("Inspection mode: plot loads against record_id, pick both contact records, then edit constants.")
        session.export(exp)
        return

    # %% 2. Contact zero. Original input channels remain available.
    exp.zero_at("vertical_load", record=VERTICAL_CONTACT_RECORD, output="vertical_force_zero")
    exp.zero_at("horizontal_load", record=HORIZONTAL_CONTACT_RECORD, output="normal_force")
    exp.zero_at("vertical_displacement", record=VERTICAL_CONTACT_RECORD, output="loadpoint_displacement")
    exp.zero_at("horizontal_displacement", record=HORIZONTAL_CONTACT_RECORD, output="horizontal_relative")

    # Ordinary reference zeroing (NO pre-reference clipping), for comparison.
    exp.zero("vertical_displacement", reference=exp.records(VERTICAL_CONTACT_RECORD, VERTICAL_CONTACT_RECORD),
             output="displacement_reference_only")
    # Optional sign/unit conversion, shown without altering the analysis coordinate.
    exp.convert("loadpoint_displacement", unit="micrometer", output="loadpoint_um")

    # %% 3. Gravity correction, in force units, only from shear contact onward.
    exp.shift("vertical_force_zero", value=0.044, unit="kN",
              records=exp.records(VERTICAL_CONTACT_RECORD, int(exp.record_ids[-1])), output="shear_force")
    exp.stress("normal_force", area_mm2=2500., output="normal_stress")
    exp.stress("shear_force", area_mm2=2500., surfaces=2, output="shear_stress")

    # %% 4. Repair a deliberate synthetic displacement reset near t=20 s.
    # BOTH endpoints are inclusive; the interval is flattened and later data shifted.
    exp.offset("loadpoint_displacement", records=exp.records(1099, 1101), output="displacement_repaired")

    # %% 5. Constant apparatus stiffnesses: SYNTHETIC, NOT lab calibrations.
    # A load can be force with kN/mm or stress with MPa/mm.
    # For real centrally managed models use session.calibration and
    # exp.correct_displacement(... using=frame_cal, ...), as in examples/demo.
    exp.elastic_correct("displacement_repaired", load="shear_force", stiffness=400.,
                        stiffness_unit="kN/mm", reference_record=VERTICAL_CONTACT_RECORD, output="slip")
    exp.elastic_correct("horizontal_relative", load="normal_force", stiffness=800.,
                        stiffness_unit="kN/mm", reference_record=HORIZONTAL_CONTACT_RECORD,
                        output="horizontal_corrected")

    # %% 6. Two layers; this horizontal coordinate decreases during closure.
    exp.layer_thickness("horizontal_corrected", reference_record=THICKNESS_REFERENCE_RECORD,
                        thickness=0.8, unit="mm", layers=2, closure_sign=1, output="layer_thickness")
    exp.geometrical_thinning("displacement_repaired", thickness="layer_thickness", block_length=50.,
                            reference_record=THICKNESS_REFERENCE_RECORD, output="legacy_corrected_thickness")
    # Explicit choice: strain uses measured, NOT geometrically corrected thickness.
    exp.shear_strain("slip", thickness="layer_thickness", reference_record=THICKNESS_REFERENCE_RECORD)

    # %% 7. Friction: undefined outside a physically valid loaded interval is NaN.
    exp.friction("shear_stress", "normal_stress", min_normal_MPa=0.1,
                 records=exp.records(VERTICAL_CONTACT_RECORD, int(exp.record_ids[-1])))
    exp.derivative("slip", time="time", window_s=0.5, min_points=5, max_gap_s=0.2, output="velocity_time_window")
    exp.running_slope("slip", x="time", window=20, output="velocity_sample_window")

    # %% 8. Filtering: choose ONLY a uniformly sampled stage (here t=12..18 s).
    exp.low_pass("friction", time="time", cutoff_Hz=2., order=2,
                 records=exp.records(300, 900), output="friction_filtered")
    # Fits: fitted values become channels; coefficients/diagnostics also print.
    linear = exp.fit("slip", "friction", records=exp.records(300, 600), degree=1, output="friction_linear_fit")
    polynomial = exp.fit("slip", "friction", records=exp.records(300, 600), degree=4, output="friction_polynomial_fit")
    print("Linear coefficients [intercept, slope]:", linear["coefficients"], "R²:", linear["r_squared"])
    print("Polynomial coefficients, ascending:", polynomial["coefficients"])
    exp.mask("friction", records=exp.records(1099, 1101), reason="Synthetic reset interval", output="friction_masked")

    # %% 9. Optional plot specifications do NOT open automatic GUI plots.
    exp.plot(x="time", left="friction", right="velocity_time_window")
    # In GUI use New plot tab / Refresh axes. Plot record_id vs time for rate changes.
    session.export(exp, channels=["time", "normal_stress", "shear_stress", "loadpoint_displacement",
        "displacement_repaired", "slip", "layer_thickness", "legacy_corrected_thickness",
        "shear_strain", "friction", "friction_filtered", "velocity_time_window",
        "velocity_sample_window", "friction_linear_fit", "friction_polynomial_fit"])
