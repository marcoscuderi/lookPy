# %% 1. Import reduction tools
# Open this file in lookPy and run the cells in order. The GUI supplies session.
# After editing an earlier cell, select the desired cell and use Run to here.
# Once the reduction is checked, Run all rebuilds it and publishes the results.
from pathlib import Path

from xlookpy import Experiment, Registry, load, save
from xlookpy.reduction_helpers import (
    bigbiax_frame,
    calculation_view,
    constant_frame,
    finite_reference,
    frame_stage,
    keep_results,
    sensor_calibration,
    unloaded_interval,
)


# %% 2. Select the raw TDMS file
# A relative path is resolved from the folder containing this script.
RAW_FILE = None  # Set to your TDMS filename or absolute path.
if RAW_FILE is None:
    raise ValueError("Set RAW_FILE to your experiment's TDMS filename or path.")


# %% 3. Select the calibration registry
# None uses the registry selected when you opened lookPy.
# Set an explicit path to the repository's calibrations/BigBiax.json if needed.
CALIBRATION_FILE = None

if CALIBRATION_FILE is not None:
    catalog_path = Path(CALIBRATION_FILE).expanduser()
    session.registry = Registry(session.project / catalog_path)
session.config.update(apparatus="BigBiax", calibration_registry=str(session.registry.root))
print("Calibration catalog / registry:", session.registry.root)


# %% 4a. Load and inspect the original ADC channels
# Declare units of the stored signals. Add other AUX units here if you plan to
# calibrate them in cell 11. Verify what the TDMS reader returns for those inputs.
ADC_UNITS = {
    "ADC/Vertical Load": "V",
    "ADC/Horizontal Load": "V",
    "ADC/Vertical Displacement": "V",
    "ADC/Horizontal Displacement": "V",
    "ADC/AUX 6": "V",
}
exp = load(RAW_FILE, units=ADC_UNITS)
first_record, last_record = int(exp.record_ids[0]), int(exp.record_ids[-1])
print(f"Original record IDs: {first_record}–{last_record}.")
print("Plot record_id against ADC/Vertical Load and ADC/Horizontal Load.")
print("Pick both unloaded intervals, both contact points and the analysis end.")

# Pause here to plot. In Experiment and channels, choose the axes and click
# New plot tab. Click the traces to read original record IDs in the execution log.
# Copy interval from last 2 picks gives inclusive endpoints. Use the two integers
# in the tuples below. Pick each ram's unloaded interval on its own load curve.


# %% 4b. Enter and verify the picked records
# Enter the original record IDs you picked after running cell 4a.
# An unloaded baseline may come from after the chosen analysis end.
VERTICAL_UNLOADED_RECORDS = None    # (first_record, last_record)
HORIZONTAL_UNLOADED_RECORDS = None  # (first_record, last_record)
VERTICAL_CONTACT = None    # Vertical ram drives shear.
HORIZONTAL_CONTACT = None  # Horizontal ram supplies normal load.
END_RECORD = None          # None uses the last recorded sample.

v_baseline = unloaded_interval(exp, VERTICAL_UNLOADED_RECORDS, "VERTICAL_UNLOADED_RECORDS")
h_baseline = unloaded_interval(exp, HORIZONTAL_UNLOADED_RECORDS, "HORIZONTAL_UNLOADED_RECORDS")
for label, record in (("VERTICAL_CONTACT", VERTICAL_CONTACT),
                      ("HORIZONTAL_CONTACT", HORIZONTAL_CONTACT)):
    if isinstance(record, bool) or not isinstance(record, int) or record not in exp.record_ids:
        raise ValueError(f"{label}: enter one original record ID picked from the ADC plot.")
analysis_end = last_record if END_RECORD is None else END_RECORD
if analysis_end < max(VERTICAL_CONTACT, HORIZONTAL_CONTACT):
    raise ValueError("END_RECORD must be at or after both ram contacts.")
analysis = exp.records(VERTICAL_CONTACT, analysis_end)
session.config.update(
    unloaded_baseline_records={"vertical": VERTICAL_UNLOADED_RECORDS,
                               "horizontal": HORIZONTAL_UNLOADED_RECORDS},
    vertical_contact=VERTICAL_CONTACT,
    horizontal_contact=HORIZONTAL_CONTACT,
    end_record=END_RECORD,
)
print("Friction and velocity analysis interval:", analysis.json())


# %% 5. Calibrate signals, remove unloaded baselines and repair offsets
VERTICAL_LOAD_ID = "BigBiax/frame/vertical/load/62_mm_LC"
HORIZONTAL_LOAD_ID = "BigBiax/frame/horizontal/load/62_mm_LC"
VERTICAL_DISPLACEMENT_ID = "BigBiax/frame/vertical/Displacement/TK_long"
HORIZONTAL_DISPLACEMENT_ID = "BigBiax/frame/horizontal/TK_short"
SENSOR_OUTSIDE = "extrapolate"

# Each repair interval is an inclusive pair of original record IDs.
SHEAR_OFFSET_INTERVALS = []
NORMAL_OFFSET_INTERVALS = []
SHEAR_DISP_OFFSET_INTERVALS = []
NORMAL_DISP_OFFSET_INTERVALS = []
SHEAR_DISPLACEMENT_SIGN = 1   # Positive in the shearing direction.
NORMAL_DISPLACEMENT_SIGN = -1  # Positive for closure.

if any(sign not in (-1, 1) for sign in (SHEAR_DISPLACEMENT_SIGN, NORMAL_DISPLACEMENT_SIGN)):
    raise ValueError("Displacement signs must be -1 or +1.")

# Use the TDMS time coefficients and the explicitly selected sensor calibrations.
exp.convert_acquisition("ADC/Time", unit="s", output="time")
exp.zero("time", reference=exp.records(first_record, first_record))
main_sensors = (
    ("ADC/Vertical Load", VERTICAL_LOAD_ID, "vertical_load"),
    ("ADC/Horizontal Load", HORIZONTAL_LOAD_ID, "horizontal_load"),
    ("ADC/Vertical Displacement", VERTICAL_DISPLACEMENT_ID, "vertical_disp_lp"),
    ("ADC/Horizontal Displacement", HORIZONTAL_DISPLACEMENT_ID, "horizontal_disp_lp"),
)
for source, identifier, output in main_sensors:
    selected = sensor_calibration(identifier, source, "acquisition")
    record = selected.record
    if output.endswith("_load") and (
        record["model"] != "linear" or record["parameters"]["intercept"] != 0
    ):
        raise ValueError(f"{identifier}: select the reviewed slope-only, zero-intercept load record.")
    exp.calibrate(source, using=selected, output=output, outside=SENSOR_OUTSIDE)

# These physical forces feed the frame correction in cell 7. Capture them
# after baseline removal and offset repair, before contact zeroing and gravity.
exp.zero("vertical_load", reference=v_baseline)
exp.zero("horizontal_load", reference=h_baseline)
for channel, intervals in (("vertical_load", SHEAR_OFFSET_INTERVALS),
                           ("horizontal_load", NORMAL_OFFSET_INTERVALS)):
    for interval in intervals:
        exp.offset(channel, records=exp.records(*interval))
frame_forces = {name: exp[name] for name in ("vertical_load", "horizontal_load")}

# Orient and contact-zero the load-point displacement before repairing its jumps.
for channel, sign, contact, intervals in (
    ("vertical_disp_lp", SHEAR_DISPLACEMENT_SIGN, VERTICAL_CONTACT, SHEAR_DISP_OFFSET_INTERVALS),
    ("horizontal_disp_lp", NORMAL_DISPLACEMENT_SIGN, HORIZONTAL_CONTACT, NORMAL_DISP_OFFSET_INTERVALS),
):
    exp.convert(channel, unit="um", scale=sign)
    exp.zero_at(channel, record=contact)
    for interval in intervals:
        exp.offset(channel, records=exp.records(*interval))

session.config.update(
    main_sensor_ids={output: identifier for _, identifier, output in main_sensors},
    displacement_unit="um",
    shear_displacement_sign=SHEAR_DISPLACEMENT_SIGN,
    normal_displacement_sign=NORMAL_DISPLACEMENT_SIGN,
    frame_force_basis="unloaded baseline removed and load offsets repaired before contact zero and gravity",
)
print("Check vertical_load, horizontal_load, vertical_disp_lp and horizontal_disp_lp.")


# %% 6. Define geometry and calculate normal and shear stress
AREA_MM2 = 2500.0       # Area of one interface.
SHEAR_SURFACES = 2
NUMBER_OF_LAYERS = 2
GRAVITY_FORCE_KN = 0.0  # Signed force added to vertical load after contact.

exp.zero_at("horizontal_load", record=HORIZONTAL_CONTACT)
exp.stress("horizontal_load", area_mm2=AREA_MM2, output="normal_stress")
exp.zero_at("vertical_load", record=VERTICAL_CONTACT)
exp.shift("vertical_load", value=GRAVITY_FORCE_KN, unit="kN",
          records=exp.records(VERTICAL_CONTACT, last_record))
exp.stress("vertical_load", area_mm2=AREA_MM2, surfaces=SHEAR_SURFACES,
           output="shear_stress")
session.config.update(geometry="double direct shear", area_mm2=AREA_MM2,
                      shear_surfaces=SHEAR_SURFACES, number_of_layers=NUMBER_OF_LAYERS)
print("Plot normal_stress and shear_stress in MPa against time or record_id.")


# %% 7. Apply elastic frame correction and inspect displacement
# Choose the loading or unloading branch explicitly for each ram.
VERTICAL_FRAME_ID = "BigBiax/frame/vertical/2026-07-16/loading/r1"
HORIZONTAL_FRAME_ID = "BigBiax/frame/horizontal/2026-07-16/loading/r1"
VERTICAL_FRAME_SIGN = -SHEAR_DISPLACEMENT_SIGN
HORIZONTAL_FRAME_SIGN = -NORMAL_DISPLACEMENT_SIGN

# None corrects the full record. A pair restricts the correction to that stage.
VERTICAL_FRAME_RECORDS = None
HORIZONTAL_FRAME_RECORDS = None
VERTICAL_FRAME_REFERENCE_RECORD = VERTICAL_CONTACT
HORIZONTAL_FRAME_REFERENCE_RECORD = HORIZONTAL_CONTACT
VERTICAL_FRAME_OUTSIDE = "extrapolate"
HORIZONTAL_FRAME_OUTSIDE = "extrapolate"

# To use constant stiffness, set that ram's FRAME_ID to None and supply MPa/mm.
# The constant-stiffness alternative uses the full record and the contact origin.
# Leave both settings None for that ram to use load-point displacement.
K_VERTICAL_MPA_PER_MM = None
K_HORIZONTAL_MPA_PER_MM = None

vertical_slip, horizontal_closure = "vertical_disp_lp", "horizontal_disp_lp"
vertical_frame_reference = VERTICAL_CONTACT
frame_settings = (
    ("vertical", "shear_stress", VERTICAL_CONTACT, VERTICAL_FRAME_ID,
     VERTICAL_FRAME_SIGN, VERTICAL_FRAME_RECORDS, VERTICAL_FRAME_REFERENCE_RECORD,
     VERTICAL_FRAME_OUTSIDE, K_VERTICAL_MPA_PER_MM),
    ("horizontal", "normal_stress", HORIZONTAL_CONTACT, HORIZONTAL_FRAME_ID,
     HORIZONTAL_FRAME_SIGN, HORIZONTAL_FRAME_RECORDS, HORIZONTAL_FRAME_REFERENCE_RECORD,
     HORIZONTAL_FRAME_OUTSIDE, K_HORIZONTAL_MPA_PER_MM),
)
for ram, stress, contact, identifier, sign, interval, reference, outside, stiffness in frame_settings:
    load_point, corrected, force = f"{ram}_disp_lp", f"{ram}_disp_ec", f"{ram}_load"
    if identifier is not None and stiffness is not None:
        raise ValueError(f"Choose a catalog model or constant stiffness for the {ram} ram.")
    if identifier is not None:
        stage, reference = frame_stage(
            exp, interval, reference, first_record, last_record, f"{ram.upper()}_FRAME_RECORDS",
        )
        # Use the physical force revision retained in cell 5 without adding
        # a second force channel to the GUI or exports.
        view = calculation_view(exp, {load_point: exp[load_point], force: frame_forces[force]})
        view.correct_displacement(
            load_point, force=force, using=bigbiax_frame(identifier), output=corrected,
            reference_record=reference, sign=sign, outside=outside, records=stage,
        )
        exp = keep_results(exp, view, [corrected])
        del view
        session.config[f"{ram}_frame_stage"] = {"records": stage.json(), "reference_record": reference}
    elif stiffness is not None:
        exp.convert(load_point, unit="um", output=corrected)
        constant_frame(exp, corrected, stress, stiffness, contact, sign)
        reference = contact

    applied = identifier is not None or stiffness is not None
    session.config.update({
        f"{ram}_frame_id": identifier,
        f"{ram}_frame_sign": sign,
        f"{ram}_frame_correction_applied": applied,
    })
    if applied:
        print(f"Compare {load_point} and {corrected}. Correction origin: record {reference}.")
        if ram == "vertical":
            vertical_slip, vertical_frame_reference = corrected, reference
        else:
            horizontal_closure = corrected
    else:
        print(f"{ram.capitalize()} frame correction off. Using {load_point}.")
del frame_forces


# %% 8. Calculate layer thickness and accumulated shear strain
# Enter measured thickness of ONE layer in mm at a known original record.
# Leave both None to skip thickness and strain.
# When thickness is calculated, lookPy closes plots using horizontal_disp_ec.
# Open a plot of layer_thickness to continue inspecting the normal direction.
THICKNESS_RECORD = None
THICKNESS_MM = None
THICKNESS_SIGN = -1  # Positive normal displacement closes the assembly.
REMOVE_GEOMETRICAL_THINNING = False
BLOCK_LENGTH_MM = 50.0
STRAIN_REFERENCE_RECORD = None  # None uses the vertical frame origin or contact.
STRAIN_THICKNESS = "measured"   # "measured" or "geometrical".

if (THICKNESS_RECORD is None) != (THICKNESS_MM is None):
    raise ValueError("Supply both THICKNESS_RECORD and per-layer THICKNESS_MM.")
if STRAIN_THICKNESS not in ("measured", "geometrical"):
    raise ValueError("STRAIN_THICKNESS must be measured or geometrical.")
if REMOVE_GEOMETRICAL_THINNING and THICKNESS_RECORD is None:
    raise ValueError("Geometrical thinning needs a layer-thickness reference.")

session.config.update(
    strain_thickness_choice=STRAIN_THICKNESS,
    geometrical_displacement_basis="repaired vertical load-point displacement",
)
if THICKNESS_RECORD is not None:
    if STRAIN_THICKNESS == "geometrical" and not REMOVE_GEOMETRICAL_THINNING:
        raise ValueError("Enable geometrical thinning before using it for strain.")
    strain_reference = (vertical_frame_reference if STRAIN_REFERENCE_RECORD is None
                        else STRAIN_REFERENCE_RECORD)
    finite_reference(exp, horizontal_closure, THICKNESS_RECORD, "THICKNESS_RECORD")
    finite_reference(exp, vertical_slip, strain_reference, "STRAIN_REFERENCE_RECORD")
    exp.layer_thickness(
        horizontal_closure, reference_record=THICKNESS_RECORD,
        thickness=THICKNESS_MM * 1000.0, unit="um", layers=NUMBER_OF_LAYERS,
        closure_sign=THICKNESS_SIGN, output="layer_thickness",
    )
    if REMOVE_GEOMETRICAL_THINNING:
        exp.geometrical_thinning(
            "vertical_disp_lp", thickness="layer_thickness", block_length=BLOCK_LENGTH_MM * 1000.0,
            unit="um", reference_record=strain_reference, model="rawpy_triangular",
            output="geometrical_thickness",
        )
    thickness_channel = "geometrical_thickness" if STRAIN_THICKNESS == "geometrical" else "layer_thickness"
    exp.shear_strain(vertical_slip, thickness=thickness_channel,
                     reference_record=strain_reference, output="shear_strain")

    # Keep the correction in operation history after replacing its plot channel
    # with layer_thickness. The original ADC and both load points remain available.
    if "horizontal_disp_ec" in exp.channels:
        channels = {name: exp[name] for name in exp.channels if name != "horizontal_disp_ec"}
        thickness_result = Experiment(channels, record_ids=exp.record_ids,
                                      metadata=exp.metadata, session=session)
        thickness_result.history = list(exp.history)
        exp = thickness_result
        save(exp)
        del thickness_result, channels
    print("Plot layer_thickness in µm and shear_strain against time or displacement.")
else:
    print("Thickness and strain skipped. The horizontal displacement remains available.")


# %% 9. Calculate friction
MIN_NORMAL_MPA = 0.1
FRICTION_MASK_INTERVALS = []  # Optional (start_record, end_record, reason) entries.

exp.friction("shear_stress", "normal_stress", records=analysis,
             min_normal_MPa=MIN_NORMAL_MPA, output="friction")
for start, end, reason in FRICTION_MASK_INTERVALS:
    exp.mask("friction", records=exp.records(start, end), reason=reason)


# %% 10. Calculate shear velocity from the load point
# Use "vertical_disp_ec" instead if you want velocity from corrected displacement.
VELOCITY_SOURCE = "vertical_disp_lp"
VELOCITY_WINDOW_S = 0.5
MAX_TIME_GAP_S = 2.0
RUNNING_SLOPE_HALF_WINDOW = None  # Optional comparison, e.g. 20 for up to 41 points.

# The regression uses actual timestamps and a fixed time span as sampling varies.
exp.derivative(VELOCITY_SOURCE, time="time", window_s=VELOCITY_WINDOW_S,
               records=analysis, min_points=5, max_gap_s=MAX_TIME_GAP_S,
               output="shear_velocity")
if RUNNING_SLOPE_HALF_WINDOW is not None:
    exp.running_slope(VELOCITY_SOURCE, x="time", window=RUNNING_SLOPE_HALF_WINDOW,
                      records=analysis, output="shear_velocity_samples")
session.config.update(velocity_unit="um/s", velocity_source=VELOCITY_SOURCE)
print(f"shear_velocity in µm/s from {VELOCITY_SOURCE}.")


# %% 11. Calibrate auxiliary channels
# Entries: (ADC channel, stored unit declared in cell 4a, calibration ID, output).
# Confirm the AUX 6 wiring and sensor gain before enabling the example.
AUXILIARY_SENSORS = [
    # ("ADC/AUX 6", "V", "BigBiax/aux/onboard_LVDT/15V", "onboard_displacement_um"),
]
AUX_OUTSIDE = "extrapolate"
for source, stored_unit, identifier, output in AUXILIARY_SENSORS:
    if exp[source].unit != stored_unit:
        raise ValueError(f"{source}: declare its stored unit {stored_unit!r} in ADC_UNITS in cell 4a.")
    exp.calibrate(source, using=sensor_calibration(identifier, source, "auxiliary"),
                  output=output, outside=AUX_OUTSIDE)
if not AUXILIARY_SENSORS:
    print("No AUX calibrations selected. Original ADC/AUX channels remain available.")


# %% 12a. Optional low-pass filtering
# Use one uniformly sampled interval with finite friction and time values.
# Leave both None to skip. A record interval needs two IDs, e.g. (12000, 16000).
FILTER_RECORDS = None
FILTER_CUTOFF_HZ = None
FILTER_ORDER = 2

friction_before_filter = exp["friction"]
if (FILTER_RECORDS is None) != (FILTER_CUTOFF_HZ is None):
    raise ValueError("Supply both FILTER_RECORDS and FILTER_CUTOFF_HZ.")
if FILTER_RECORDS is not None:
    if not isinstance(FILTER_RECORDS, (tuple, list)) or len(FILTER_RECORDS) != 2:
        raise ValueError("FILTER_RECORDS must be (start_record, end_record).")
    exp.low_pass("friction", time="time", records=exp.records(*FILTER_RECORDS),
                 cutoff_Hz=FILTER_CUTOFF_HZ, order=FILTER_ORDER)


# %% 12b. Optional fits and other analysis
# A tuple enables scripted fits. For a one-off fit, use Fit interval in the GUI.
FIT_RECORDS = None
POLYNOMIAL_DEGREE = 4
FIT_USE_FILTERED = False
session.config["fit_friction_basis"] = "after filtering" if FIT_USE_FILTERED else "before filtering"

if FIT_RECORDS is not None:
    if not isinstance(FIT_RECORDS, (tuple, list)) or len(FIT_RECORDS) != 2:
        raise ValueError("FIT_RECORDS must be (start_record, end_record).")
    friction_for_fit = exp["friction"] if FIT_USE_FILTERED else friction_before_filter
    fitting = calculation_view(exp, {vertical_slip: exp[vertical_slip], "friction": friction_for_fit})
    fit_interval = fitting.records(*FIT_RECORDS)
    linear_fit = fitting.fit(vertical_slip, "friction", records=fit_interval,
                             degree=1, output="friction_linear_fit")
    polynomial_fit = fitting.fit(vertical_slip, "friction", records=fit_interval,
                                 degree=POLYNOMIAL_DEGREE, output="friction_polynomial_fit")
    exp = keep_results(exp, fitting, ["friction_linear_fit", "friction_polynomial_fit"])
    print("Linear [intercept, slope (1/µm)]:", linear_fit["coefficients"], "R²:", linear_fit["r_squared"])
    print("Polynomial fit coefficients in ascending powers:", polynomial_fit["coefficients"])
    del fitting, friction_for_fit
del friction_before_filter

# Add extra operations in their own cells here. Examples (replace the record IDs):
# exp.mask("friction", records=exp.records(12000, 12020), reason="signal dropout")
# exp.shift("vertical_disp_lp", value=2.0, unit="um", output="shifted_displacement")
# See docs/RAWPY_FUNCTIONS.md in lookPy for the operation reference.


# %% 12c. Optional detrending
# Paste commands from Fit interval → Copy detrend command here, or add entries
# below as (x channel, y channel, (first record, last record), degree, output).
# This cell uses the channels available at this stage, including any filtering.
# Use a distinct output name for each window.
DETREND_WINDOWS = [
    # ("time", "friction", (12000, 16000), 1, "friction_detrended_1"),
]
for x_channel, y_channel, interval, degree, output in DETREND_WINDOWS:
    exp.detrend(x_channel, y_channel, records=exp.records(*interval),
                degree=degree, output=output)


# %% 13. Select final output channels
# None selects the current working channels. To export a subset, list their names.
# Original ADC signals remain available in lookPy. Run all publishes the results
# and the experiment manifest after you finish checking the individual cells.
EXPORT_CHANNELS = None
save(exp, channels=EXPORT_CHANNELS)
print("Selected export channels:", ", ".join(exp.export_columns if EXPORT_CHANNELS is None else EXPORT_CHANNELS))
