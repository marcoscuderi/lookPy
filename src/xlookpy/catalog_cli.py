"""Terminal calibration manager; numerical values are always supplied by the operator."""
from datetime import date
import json
from pathlib import Path
import numpy as np
from .catalog import Catalog
from .calibration import Registry
from .util import file_digest


def configure(parser):
    parser.add_argument("action", choices=["init", "add", "import", "list", "show", "curve", "suggest"])
    parser.add_argument("value", nargs="?", help="Record JSON path, exact ID, or suggestion name")
    parser.add_argument("identifier", nargs="?", help="Exact ID for suggest")
    root = Registry().root
    parser.add_argument("--file", default=str(root if root.suffix.lower() == ".json" else root / "BigBiax.json"))
    parser.add_argument("--points", type=int, default=11, help="Samples for curve table")
    parser.add_argument("--tdms", help="Prefill add from TDMS custom Slope/Intercept metadata")
    parser.add_argument("--channel", help="Original TDMS channel name, e.g. Vertical Load")


def _ask(label, default=None):
    answer = input(label + (f" [{default}]" if default is not None else "") + ": ").strip()
    answer = answer or default
    if answer is None or answer == "":
        raise ValueError(f"{label} is required; nothing was saved.")
    return answer


def new_record(acquisition=None):
    purpose = "acquisition" if acquisition else _ask("Purpose (acquisition / auxiliary / elastic)")
    elastic = purpose == "elastic"
    print("Elastic models describe deformation e(F), NOT stiffness k(F)." if elastic else
          "Sensor models convert the declared input values to engineering units.")
    record = {"schema_version": 1, "apparatus": "BigBiax", "purpose": purpose,
              "id": _ask("Permanent ID, e.g. BigBiax/frame/vertical/config_A/r1"),
              "category": "apparatus" if elastic else "sensor",
              "sensor": _ask("Sensor identity or frame axis"),
              "configuration": _ask("Apparatus / electronics configuration"),
              "date": _ask("Calibration date YYYY-MM-DD", date.today().isoformat()),
              "source": acquisition["source"] if acquisition else _ask("Source measurement file / calibration report"),
              "input_unit": _ask("Input unit", "kN" if elastic else "V"),
              "output_unit": _ask("Output unit", "um" if elastic else None),
              "model": "linear" if acquisition else _ask("Model (linear / polynomial)", "polynomial" if elastic else "linear")}
    if not elastic:
        record["gain"] = _ask("Gain (low / high / explicit description)")
    if acquisition:
        record["parameters"] = acquisition["parameters"]
        record["provenance"] = acquisition["provenance"]
        print("TDMS coefficients:", record["parameters"])
    elif record["model"] == "linear":
        record["parameters"] = {"slope": float(_ask("Slope")), "intercept": float(_ask("Intercept"))}
    else:
        record["parameters"] = {"coefficients": [float(x) for x in _ask("Coefficients, highest power FIRST, separated by spaces").split()]}
    record["valid_range"] = [float(_ask("Minimum calibrated input")), float(_ask("Maximum calibrated input"))]
    record["notes"] = _ask("Notes (orientation, fit, limitations)")
    Catalog.validate_record(record)
    return record


def execute(args):
    catalog = Catalog(args.file)
    if (args.tdms or args.channel) and (args.action != "add" or not (args.tdms and args.channel)):
        raise ValueError("Use --tdms and --channel together with catalog add.")
    if args.action == "init":
        print(catalog.initialize())
    elif args.action == "add":
        acquisition = None
        if args.tdms:
            from nptdms import TdmsFile
            props = TdmsFile.read_metadata(args.tdms)["ADC"][args.channel].properties
            acquisition = {"source": str(Path(args.tdms).expanduser().resolve()),
                           "parameters": {"slope": float(props["Slope"]), "intercept": float(props["Intercept"])},
                           "provenance": {"tdms_sha256": file_digest(args.tdms), "channel": "ADC/"+args.channel}}
        record = new_record(acquisition)
        print(json.dumps(record, indent=2))
        if input("Save this new revision? [y/N]: ").strip().lower() != "y":
            print("Cancelled; nothing saved.")
            return
        print(f"Saved {catalog.add(record).id}")
    elif args.action == "import":
        if not args.value:
            raise ValueError("import needs a single-record JSON path.")
        print(f"Saved {catalog.add(json.loads(Path(args.value).read_text(encoding='utf-8'))).id}")
    elif args.action == "list":
        data = catalog.read()
        for cal in catalog.list():
            r = cal.record
            print(f"{cal.id}\t{r['purpose']}\t{r['sensor']}\t{r.get('gain', '—')}\t{r['configuration']}\t{r['date']}\t{r['input_unit']} -> {r['output_unit']}")
        print("Suggested defaults (not applied automatically):", json.dumps(data["suggested_defaults"]))
    elif args.action == "suggest":
        catalog.suggest(args.value, args.identifier)
        print(f"Suggestion {args.value}: {args.identifier}. Reduction scripts still require the exact ID.")
    else:
        if not args.value:
            raise ValueError(f"{args.action} needs an exact calibration ID.")
        cal = catalog.get(args.value)
        if args.action == "show":
            print(json.dumps(cal.record, indent=2))
            print("SHA256", cal.fingerprint)
        else:
            if not 2 <= args.points <= 10000:
                raise ValueError("points must be between 2 and 10000.")
            x = np.linspace(*cal.record["valid_range"], args.points)
            y, _ = cal.evaluate(x)
            print(f"input [{cal.record['input_unit']}]\toutput [{cal.record['output_unit']}]")
            for xx, yy in zip(x, y):
                print(f"{xx:.12g}\t{yy:.12g}")
