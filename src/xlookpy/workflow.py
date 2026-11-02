"""Small top-level script vocabulary, bound to the active reduction session."""
from contextlib import contextmanager
from contextvars import ContextVar
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
    """Load one experiment; an explicitly chosen BRAVA profile maps ADC channels.

    BRAVA is the existing template's acquisition convention, not a sensor or
    apparatus calibration. Review signs, units and Slope/Intercept applicability.
    """
    if profile not in (None, "BRAVA"):
        raise ValueError("Available profile: BRAVA; omit profile for unmapped stored channels.")
    session = _session()
    exp = session.load(path, units=units, reader=reader, dataendianness=dataendianness)
    if profile is None:
        return exp
    if exp.metadata.get("reader") != "nptdms":
        raise ValueError("The BRAVA profile requires TDMS with the ADC group.")
    mapping = [
        ("ADC/Time", "s", "absolute_time"),
        ("ADC/Vertical Load", "kN", "vertical_load"),
        ("ADC/Horizontal Load", "kN", "horizontal_load"),
        ("ADC/Vertical Displacement", "um", "vertical_displacement_um"),
        ("ADC/Horizontal Displacement", "um", "horizontal_displacement_um"),
    ]
    # Check the complete mapping before starting conversions.
    for source, _, _ in mapping:
        props = exp[source].metadata.get("properties", {})
        if "Slope" not in props or "Intercept" not in props:
            raise ValueError(f"BRAVA profile needs Slope/Intercept on {source}. Use load without profile and map explicitly.")
    definition = {"name": "BRAVA", "revision": 1, "mapping": mapping,
                  "time_origin": "first original record", "horizontal_displacement_scale": -1,
                  "displacement_output_unit": "mm",
                  "note": "Operator-selected acquisition convention; no sensor recalibration or frame correction."}
    session.config["acquisition_profile"] = {"definition": definition, "sha256": digest(definition)}
    for source, unit, output in mapping:
        exp.convert_acquisition(source, unit=unit, output=output)
    first = int(exp.record_ids[0])
    exp.zero("absolute_time", reference=exp.records(first, first), output="time")
    exp.convert("vertical_displacement_um", unit="mm", output="vertical_displacement_mm")
    exp.convert("horizontal_displacement_um", unit="mm", scale=-1, output="horizontal_displacement_mm")
    print("BRAVA profile: custom ADC Slope/Intercept applied; forces kN; displacement mm; horizontal sign -1; time starts at first record. Verify these apparatus conventions.")
    return exp


def calibration(identifier):
    return _session().calibration(identifier)


def save(exp, *, channels=None):
    """Choose final export channels. Only a successful fresh Run all publishes."""
    return _session().export(exp, channels=channels)


def stop():
    """End execution intentionally after inspection; Run all can save that state."""
    raise StopReduction()


def vocabulary(session):
    return {"session": session, "load": load, "calibration": calibration, "save": save, "stop": stop}
