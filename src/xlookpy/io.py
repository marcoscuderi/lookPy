"""Readers never apply custom acquisition coefficients implicitly."""
import csv
from pathlib import Path
import numpy as np
from .model import Channel, Experiment
from .util import json_value


def load_file(path, *, units=None, session=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Raw experiment not found: {path}")
    units = units or {}
    if path.suffix.lower() == ".tdms":
        return load_tdms(path, units=units, session=session)
    if path.suffix.lower() != ".csv":
        raise ValueError("Prototype readers support .tdms and comma-separated .csv. Specify numeric channel units explicitly.")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        header = next(csv.reader(stream))
    if len(header) != len(set(header)) or any(not n or n == "record_id" for n in header):
        raise ValueError("CSV needs unique, nonempty headers; record_id is reserved.")
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    if data.shape[1] != len(header):
        raise ValueError("CSV column count differs from header.")
    missing = set(header)-set(units)
    if missing:
        raise ValueError(f"Specify units for CSV channels: {sorted(missing)}.")
    channels = {name: Channel(data[:, i], units[name], {"role": "input_csv"}) for i, name in enumerate(header)}
    return Experiment(channels, metadata={"reader": "csv", "source": str(path)}, session=session)


def load_tdms(path, *, units, session):
    from nptdms import TdmsFile
    tdms = TdmsFile.read(path)
    status = tdms.file_status
    if status.incomplete_final_segment:
        raise ValueError("TDMS has an incomplete final segment. Recover/verify the acquisition file before reducing it.")
    channels, other = {}, {}
    groups = tdms.groups()
    if not any(g.name == "ADC" for g in groups):
        raise ValueError("This first TDMS reader requires the apparatus ADC group. Other layouts need an explicit reader mapping.")
    for group in groups:
        if group.name != "ADC":
            other[group.name] = {"properties": json_value(dict(group.properties)),
                                 "channels": {c.name: {"properties": json_value(dict(c.properties)),
                                                      "values": json_value(c[:].tolist())} for c in group.channels()}}
            continue
        for channel in group.channels():
            name = "ADC/" + channel.name
            values = np.asarray(channel[:])
            if values.dtype.kind not in "fiub":
                raise ValueError(f"ADC channel {name} is not numeric.")
            # Unit must be explicit; never infer voltage vs physical units from name.
            channels[name] = Channel(values, units.get(name, "unassigned"),
                                     {"role": "stored_tdms", "tdms_path": channel.path,
                                      "properties": json_value(dict(channel.properties)),
                                      "input_unit_declared": name in units,
                                      "note": "Values returned by npTDMS (may include NI scaling); custom Slope/Intercept properties are not applied."})
    return Experiment(channels, metadata={"reader": "nptdms", "source": str(path),
                      "properties": json_value(dict(tdms.properties)), "other_groups": other,
                      "adc_properties": json_value(dict(tdms["ADC"].properties))}, session=session)


def write_dat(exp, path, channels):
    selected = list(channels or exp.channels)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Export requires one or more unique channel names.")
    # Original row IDs are always the first column, including when explicitly selected.
    selected = [name for name in selected if name != "record_id"]
    for name in selected:
        exp[name]
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        stream.write("\t".join(["record_id", *selected])+"\n")
        stream.write("\t".join(["dimensionless", *[exp[c].unit for c in selected]])+"\n")
        # Blocks avoid making another copy of the complete experiment.
        for start in range(0, len(exp), 10000):
            block = np.column_stack([exp.record_ids[start:start+10000], *[exp[c].values[start:start+10000] for c in selected]])
            np.savetxt(stream, block, delimiter="\t", fmt=["%d"]+["%.17g"]*len(selected))
    return selected


def write_state(exp, path):
    np.savez_compressed(path, record_id=exp.record_ids,
                        **{f"c{i}": exp[name].values for i, name in enumerate(exp.channels)})


def read_state(path, manifest):
    with np.load(path, allow_pickle=False) as state:
        channels = {c["name"]: Channel(state[f"c{i}"], c["unit"], c["metadata"])
                    for i, c in enumerate(manifest["channels"])}
        exp = Experiment(channels, record_ids=state["record_id"], metadata=manifest["experiment"])
    exp.history = manifest["operations"]
    return exp
