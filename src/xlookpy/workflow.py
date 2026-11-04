"""Small top-level script vocabulary, bound to the active reduction session."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
from .util import digest

_ACTIVE = ContextVar("xlook_active_session", default=None)


class StopReduction(Exception):
    """Intentional end of a reduction, e.g. after loading contact-inspection data."""


@contextmanager
def using_session(session):
    token = _ACTIVE.set(session)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def _session():
    session = _ACTIVE.get()
    if session is None:
        raise RuntimeError("Use these helpers in a pyXlook cell workspace or python -m xlookpy run script.py.")
    return session


def load(path, *, profile=None, units=None, reader=None, dataendianness="little"):
    """Load one experiment; an explicit apparatus profile maps ADC channels.

    BRAVA is the existing template's acquisition convention, not a sensor or
    apparatus calibration. Review signs, units and Slope/Intercept applicability.
    """
    if profile not in (None, "BRAVA", "BigBiax"):
        raise ValueError("Available profiles: BigBiax, BRAVA; omit profile for unmapped stored channels.")
    if profile == "BigBiax":
        units = dict(units or {})
        for name in ("Vertical Load", "Horizontal Load", "Vertical Displacement", "Horizontal Displacement"):
            source = "ADC/" + name
            if source in units and units[source] != "V":
                raise ValueError(f"BigBiax expects {source} in V; use explicit mapping for other stored units.")
            units[source] = "V"
    session = _session()
    exp = session.load(path, units=units, reader=reader, dataendianness=dataendianness)
    if profile is None:
        return exp
    if exp.metadata.get("reader") != "nptdms":
        raise ValueError(f"The {profile} profile requires TDMS with the ADC group.")
    suffix = "um" if profile == "BigBiax" else "mm"
    mapping = [
        ("ADC/Time", "s", "time"),
        ("ADC/Vertical Load", "kN", "vertical_load"),
        ("ADC/Horizontal Load", "kN", "horizontal_load"),
        ("ADC/Vertical Displacement", "um", f"vertical_displacement_{suffix}"),
        ("ADC/Horizontal Displacement", "um", f"horizontal_displacement_{suffix}"),
    ]
    # Check the complete mapping before starting conversions.
    for source, _, _ in mapping:
        props = exp[source].metadata.get("properties", {})
        if "Slope" not in props or "Intercept" not in props:
            raise ValueError(f"{profile} profile needs Slope/Intercept on {source}. Use load without profile and map explicitly.")
        if not all(math.isfinite(float(props[k])) for k in ("Slope", "Intercept")):
            raise ValueError(f"Nonfinite acquisition coefficients on {source}.")
    definition = {"name": profile, "revision": 1 if profile == "BigBiax" else 2, "mapping": mapping,
                  "time_origin": "first original record", "horizontal_displacement_scale": 1 if profile == "BigBiax" else -1,
                  "displacement_output_unit": suffix,
                  "note": "Operator-selected acquisition convention; no sensor recalibration or frame correction."}
    session.config["acquisition_profile"] = {"definition": definition, "sha256": digest(definition)}
    if profile == "BigBiax":
        session.config["tdms_acquisition_calibrations"] = {
            source: {"slope": float(exp[source].metadata["properties"]["Slope"]),
                     "intercept": float(exp[source].metadata["properties"]["Intercept"]),
                     "output_unit": unit, "output": output}
            for source, unit, output in mapping}
    for source, unit, output in mapping:
        exp.convert_acquisition(source, unit=unit, output=output)
    first = int(exp.record_ids[0])
    exp.zero("time", reference=exp.records(first, first))
    if profile == "BRAVA":
        exp.convert("vertical_displacement_mm", unit="mm")
        exp.convert("horizontal_displacement_mm", unit="mm", scale=-1)
    orientation = "acquisition signs retained" if profile == "BigBiax" else "horizontal displacement sign -1"
    print(f"{profile} profile: custom TDMS Slope/Intercept applied once; forces kN; displacement {suffix}; {orientation}; time starts at first record. Verify coordinate orientation in the reduction script.")
    return exp


def calibration(identifier):
    return _session().calibration(identifier)


def save(exp, *, channels=None):
    """Choose final exports; default to current working channels, excluding raw inputs.

    Only a successful fresh Run all publishes. Explicit channel lists can include
    originals when requested; prior working revisions live in operation history.
    """
    return _session().export(exp, channels=channels)


def stop():
    """End execution intentionally after inspection; Run all can save that state."""
    raise StopReduction()


def vocabulary(session):
    return {"session": session, "load": load, "calibration": calibration, "save": save, "stop": stop}
