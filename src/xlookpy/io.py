"""Readers never apply custom acquisition coefficients implicitly."""
import csv
from pathlib import Path
import numpy as np
from .model import Channel, Experiment
from .util import json_value


def load_file(path, *, units=None, session=None, reader=None, dataendianness="little"):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Raw experiment not found: {path}")
    units = units or {}
    if reader not in (None, "csv", "tdms", "text", "xlook_binary"):
        raise ValueError("reader must be csv, tdms, text or xlook_binary.")
    selected_reader = reader or ({".tdms": "tdms", ".csv": "csv", ".txt": "text", ".dat": "text", ".bin": "xlook_binary"}.get(path.suffix.lower(), "text"))
    if selected_reader == "text":
        return load_text(path, units=units, session=session)
    if selected_reader == "xlook_binary":
        return read_binary(path, units=units, session=session, dataendianness=dataendianness)
    if selected_reader == "tdms":
        return load_tdms(path, units=units, session=session)
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


def _header_channels(names, unit_names, overrides):
    if not names or len(names) != len(set(names)) or any(not n for n in names):
        raise ValueError("Input needs unique, nonempty channel names.")
    if len(names) != len(unit_names):
        raise ValueError("Channel names and unit header have different lengths.")
    aliases = {"na": "dimensionless", "n/a": "dimensionless", "-": "dimensionless", "": "unassigned"}
    result = {n: overrides.get(n, aliases.get(u.strip().lower(), u.strip())) for n, u in zip(names, unit_names)}
    from .util import factor
    for unit in result.values():
        factor(unit, unit)
    return result


def load_text(path, *, units=None, session=None):
    """rawPy/BRAVA two-header tab-separated format, including reduced.dat.

    A reserved record_id column restores original IDs. Other record columns
    (Record, Rec_n, etc.) are preserved as ordinary input channels.
    """
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream, delimiter="\t")
        try:
            names = [n.strip() for n in next(rows)]
            labels = next(rows)
        except StopIteration:
            raise ValueError("Text reader requires names and units as two tab-separated header rows.") from None
    declared = _header_channels(names, labels, units or {})
    data = np.loadtxt(path, delimiter="\t", skiprows=2, ndmin=2)
    if data.shape[1] != len(names):
        raise ValueError("Text data column count differs from header.")
    record_ids = None
    if "record_id" in names:
        values = data[:, names.index("record_id")]
        if not np.isfinite(values).all() or np.any(values < 0) or np.any(values != np.floor(values)) or np.any(values > 2**53):
            raise ValueError("record_id column must contain exactly representable nonnegative integer IDs.")
        record_ids = values.astype(np.int64)
    channels = {n: Channel(data[:, j], declared[n], {"role": "input_text"})
                for j, n in enumerate(names) if n != "record_id"}
    return Experiment(channels, record_ids=record_ids,
                      metadata={"reader": "rawpy_text", "source": str(path.resolve())}, session=session)


def read_binary(path, *, units=None, session=None, dataendianness="little"):
    """Legacy Xlook: big-endian fixed headers, column-major float64 payload.

    Short declared channels are explicitly padded with NaN, never invented zeros.
    No writer is provided, matching rawPy's read-only legacy binary support.
    """
    import struct
    if dataendianness not in ("little", "big"):
        raise ValueError("dataendianness must be little or big.")
    path = Path(path)
    def text(raw):
        return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
    with path.open("rb") as stream:
        def take(n):
            data = stream.read(n)
            if len(data) != n:
                raise ValueError("Truncated Xlook binary header or payload.")
            return data
        name = text(take(20))
        nrows, ncols, sweep, date = struct.unpack(">4i", take(16))
        if nrows < 1 or not 1 <= ncols <= 32:
            raise ValueError("Invalid Xlook record/column counts.")
        headers = []
        for _ in range(32):
            raw_name, raw_unit, gain, comment, count = struct.unpack(">13s13si50si", take(84))
            column = text(raw_name)
            if not column or column.startswith("no_val"):
                continue
            if not 0 <= count <= nrows:
                raise ValueError("Xlook channel record count is outside declared experiment length.")
            headers.append((column, text(raw_unit), count, text(comment)))
        if len(headers) != ncols:
            raise ValueError("Xlook column count differs from active header entries.")
        declared = _header_channels([h[0] for h in headers], [h[1] for h in headers], units or {})
        if "record_id" in declared:
            raise ValueError("Legacy binary channel record_id conflicts with reserved original IDs.")
        expected = sum(h[2] for h in headers)*8
        if path.stat().st_size-stream.tell() != expected:
            raise ValueError("Xlook payload length differs from channel header counts (truncated or trailing data).")
        channels = {}
        dtype = "<f8" if dataendianness == "little" else ">f8"
        for column, unit, count, comment in headers:
            values = np.full(nrows, np.nan)
            values[:count] = np.frombuffer(take(count*8), dtype=dtype)
            channels[column] = Channel(values, declared[column], {"role": "input_xlook_binary",
                                       "declared_records": count, "comment": comment,
                                       "missing_tail": "NaN"})
    return Experiment(channels, metadata={"reader": "xlook_binary", "source": str(path.resolve()),
                      "name": name, "sweep": sweep, "date": date, "dataendianness": dataendianness}, session=session)
