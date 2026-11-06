"""Reusable operations for cell-based BigBiax reductions."""

import numpy as np

from .model import Experiment
from .workflow import _session, calibration, save


def calculation_view(current, inputs):
    """Use read-only historical inputs without adding intermediate GUI channels."""
    view = Experiment(inputs, record_ids=current.record_ids, session=_session())
    view.history = list(current.history)
    return view


def keep_results(current, calculation, names):
    """Bring calculated results and their revision history into the live experiment."""
    channels = {name: current[name] for name in current.channels}
    channels.update({name: calculation[name] for name in names})
    updated = Experiment(channels, metadata=current.metadata,
                         record_ids=current.record_ids, session=_session())
    updated.history = list(calculation.history)
    save(updated)  # Select live state only; publication still requires Run all.
    return updated


def bigbiax_frame(identifier):
    """Select an exact, snapshotted apparatus revision; never a changing default."""
    selected = calibration(identifier)
    r = selected.record
    if r["apparatus"] != "BigBiax" or r["category"] != "apparatus":
        raise ValueError(f"{identifier}: choose a BigBiax apparatus deformation calibration.")
    if r.get("purpose") != "elastic":
        raise ValueError(f"{identifier}: the catalog purpose must be elastic.")
    return selected


def sensor_calibration(identifier, source, purpose):
    selected = calibration(identifier)
    r = selected.record
    if r["apparatus"] != "BigBiax" or r["category"] != "sensor" or r.get("purpose") != purpose:
        raise ValueError(f"{identifier}: choose a BigBiax {purpose} sensor calibration.")
    channel = r.get("provenance", {}).get("channel")
    if channel is not None and channel != source:
        raise ValueError(f"{identifier}: catalog source {channel} does not match {source}.")
    return selected


def unloaded_interval(exp, pair, label):
    if pair is None or len(pair) != 2:
        raise ValueError(f"Set {label}=(start_record, end_record) using actual unloaded data.")
    selection = exp.records(*pair)
    if not np.isin([selection.start, selection.end], exp.record_ids).all():
        raise ValueError(f"{label}: endpoints must be original records present in this file.")
    return selection


def frame_stage(exp, pair, reference, start, end, label):
    interval = (start, end) if pair is None else pair
    selection = exp.records(*interval)
    if not np.isin([selection.start, selection.end], exp.record_ids).all():
        raise ValueError(f"{label}: interval endpoints are not present in this file.")
    reference = selection.start if reference is None else reference
    if not selection.start <= reference <= selection.end:
        raise ValueError(f"{label}: reference must lie inside the correction interval.")
    if reference not in exp.record_ids:
        raise ValueError(f"{label}: reference is not an original record in this file.")
    return selection, int(reference)


def finite_reference(exp, source, record, label):
    positions = np.flatnonzero(exp.record_ids == record)
    if len(positions) != 1 or not np.isfinite(exp[source].values[positions[0]]):
        raise ValueError(f"{label}: choose a finite reference within the corrected interval.")


def constant_frame(exp, source, stress, stiffness, contact, sign):
    # elastic_correct subtracts stress/k. Reverse coordinates around that operation
    # when the signed frame correction requires addition. No extra channels.
    if sign not in (-1, 1):
        raise ValueError("Frame sign must be -1 or +1.")
    if sign == 1:
        exp.convert(source, unit="um", scale=-1)
    exp.elastic_correct(source, load=stress, stiffness=stiffness,
                        stiffness_unit="MPa/mm", reference_record=contact)
    if sign == 1:
        exp.convert(source, unit="um", scale=-1)
    exp.zero_at(source, record=contact)
