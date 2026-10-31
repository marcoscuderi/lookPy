"""Pick each ram's sample-contact onset, then run a standard reduction.

1. Put the TDMS alongside this script, or edit RAW_FILE to its full path.
2. Run with both contact records None: original physical signals are plotted.
3. Click the vertical and horizontal contact onsets. Paste their original
   RECORD IDs below (one integer each, not seconds).
4. Run all again. Each ram's force AND displacement are zero at its contact;
   earlier values are forced to zero and later changes are retained.

No apparatus correction is applied unless you explicitly select a calibration.
"""
RAW_FILE = "eq_phys_demo.tdms"
VERTICAL_CONTACT_RECORD = None    # Pick vertical ram contact: e.g. 1200.
HORIZONTAL_CONTACT_RECORD = None  # Pick horizontal ram contact: e.g. 850.
ANALYSIS_RECORDS = None           # None -> whole record for friction; or (start, end).
AREA_MM2 = 2500.0                 # 5 x 5 cm, ONE interface.
SHEAR_SURFACES = 2                # Double direct shear. Normal force uses ONE area.
MIN_NORMAL_MPA = 0.1
VELOCITY_WINDOW_S = 0.5           # Full regression-window width in seconds.
FRAME_CALIBRATION_ID = None       # Approved CENTRAL apparatus calibration ID, or None.
CORRECTION_RECORDS = None         # Or (start, end) for ONE mechanical stage.
CORRECTION_REFERENCE_RECORD = None  # None -> vertical contact; stage reference can override.
CORRECTION_SIGN = -1              # Subtract elastic deformation for positive vertical coordinate.
OUTSIDE_CALIBRATION = "error"     # Alternatives mask / clip / extrapolate require operator choice.


def reduce(session):
    # %% 1. Read stored signals and inspect custom acquisition coefficients.
    exp = session.load(RAW_FILE)
    session.config = {"area_mm2": AREA_MM2, "shear_surfaces": SHEAR_SURFACES,
                      "vertical_contact_record": VERTICAL_CONTACT_RECORD,
                      "horizontal_contact_record": HORIZONTAL_CONTACT_RECORD,
                      "contact_zero_rule": "subtract exact contact sample; force earlier values to zero",
                      "apparatus_correction": FRAME_CALIBRATION_ID,
                      "spring": "operator must specify configuration/stages",
                      "layer_thickness_mm": None}

    # %% 2. Apply custom TDMS Slope/Intercept once. Units below are your apparatus
    # conventions; this TDMS does not itself declare physical output units.
    for source, unit, output in [
        ("ADC/Time", "s", "absolute_time"),
        ("ADC/Vertical Load", "kN", "vertical_load"),
        ("ADC/Horizontal Load", "kN", "horizontal_load"),
        ("ADC/Vertical Displacement", "um", "vertical_displacement_um"),
        ("ADC/Horizontal Displacement", "um", "horizontal_displacement_um"),
    ]:
        exp.convert_acquisition(source, unit=unit, output=output)
    first_record = int(exp.record_ids[0])
    last_record = int(exp.record_ids[-1])
    exp.zero("absolute_time", reference=exp.records(first_record, first_record), output="time")
    exp.convert("vertical_displacement_um", unit="mm", output="vertical_displacement_mm")
    exp.convert("horizontal_displacement_um", unit="mm", scale=-1, output="horizontal_displacement_mm")

    # Always retain original physical load plots for choosing/reviewing contact.
    exp.plot(x="time", left="vertical_load", right="horizontal_load", title="Pick ram contacts — original loads")
    if VERTICAL_CONTACT_RECORD is None or HORIZONTAL_CONTACT_RECORD is None:
        session.config["mode"] = "contact_inspection_only"
        exp.plot(x="time", left="vertical_displacement_mm", right="horizontal_displacement_mm",
                 title="Pick ram contacts — original displacements")
        print("INSPECTION ONLY: pick each contact onset on the plots, then set VERTICAL_CONTACT_RECORD and HORIZONTAL_CONTACT_RECORD to those integer record IDs. Stress/friction reduction has not run.")
        session.export(exp, channels=["time", "vertical_load", "horizontal_load",
                                     "vertical_displacement_mm", "horizontal_displacement_mm"])
        return

    # %% 3. Contact zeroing. No averaging. Each chosen point is EXACTLY zero.
    # Earlier values are zero; later unloading/negative changes are retained.
    exp.zero_at("vertical_load", record=VERTICAL_CONTACT_RECORD, output="shear_force")
    exp.zero_at("horizontal_load", record=HORIZONTAL_CONTACT_RECORD, output="normal_force")
    exp.zero_at("vertical_displacement_mm", record=VERTICAL_CONTACT_RECORD, output="measured_relative")
    exp.zero_at("horizontal_displacement_mm", record=HORIZONTAL_CONTACT_RECORD, output="normal_displacement_mm")
    session.config["mode"] = "contact_zero_reduction"

    # %% 4. Optional apparatus correction. The default reference is vertical
    # contact. For a later mechanical stage, explicitly choose a reference in it.
    if FRAME_CALIBRATION_ID is None:
        slip_channel = "measured_relative"
    else:
        frame = session.calibration(FRAME_CALIBRATION_ID)
        interval = exp.records(*CORRECTION_RECORDS) if CORRECTION_RECORDS else None
        ref = VERTICAL_CONTACT_RECORD if CORRECTION_REFERENCE_RECORD is None else CORRECTION_REFERENCE_RECORD
        exp.correct_displacement("measured_relative", force="shear_force", using=frame,
                                 reference_record=ref, records=interval, sign=CORRECTION_SIGN,
                                 outside=OUTSIDE_CALIBRATION, output="elastic_relative")
        if interval is None:
            exp.zero_at("elastic_relative", record=VERTICAL_CONTACT_RECORD, output="slip")
            slip_channel = "slip"
        else:
            slip_channel = "elastic_relative"  # Outside selected mechanical stage: NaN.

    # %% 5. Stress, friction and velocity.
    analysis = exp.records(*ANALYSIS_RECORDS) if ANALYSIS_RECORDS else None
    exp.stress("shear_force", area_mm2=AREA_MM2, surfaces=SHEAR_SURFACES, output="shear_stress")
    exp.stress("normal_force", area_mm2=AREA_MM2, output="normal_stress")
    exp.friction("shear_stress", "normal_stress", records=analysis, min_normal_MPa=MIN_NORMAL_MPA)
    # Do not fit velocity windows across the imposed pre-contact zero segment.
    start = max(VERTICAL_CONTACT_RECORD, analysis.start if analysis else first_record)
    end = analysis.end if analysis else last_record
    if start > end:
        raise ValueError("The velocity analysis interval ends before vertical contact. Select a post-contact interval.")
    exp.derivative(slip_channel, time="time", window_s=VELOCITY_WINDOW_S,
                   records=exp.records(start, end), min_points=5, max_gap_s=2.0, output="slip_velocity")
    session.config["warning"] = "Uncorrected velocity includes machine deformation when apparatus correction is disabled. Friction without normal load and velocity without a complete post-contact window are NaN."
    exp.plot(x="time", left="shear_stress", right="normal_stress", title="Contact-zero stresses")
    exp.plot(x="time", left="friction", right=slip_channel, title="Friction and displacement")
    exp.plot(x="time", left=slip_channel, right="slip_velocity", title="Velocity diagnostics")
    session.export(exp, channels=["time", "shear_force", "normal_force", "shear_stress",
                                 "normal_stress", "friction", "measured_relative", "normal_displacement_mm",
                                 *([slip_channel] if slip_channel != "measured_relative" else []), "slip_velocity"])
