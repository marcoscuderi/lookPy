"""Command line entry points also used by the desktop execution worker."""
import argparse
import sys
from .calibration import Registry
from .session import run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="xlookpy")
    sub = parser.add_subparsers(dest="command", required=True)
    reduce = sub.add_parser("run", help="Execute a trusted reduction.py from fresh state")
    reduce.add_argument("script")
    reduce.add_argument("--registry")
    reduce.add_argument("--replay-manifest")
    gui = sub.add_parser("gui", help="Open the experimental desktop workspace")
    gui.add_argument("script", nargs="?")
    gui.add_argument("--registry")
    calibration = sub.add_parser("calibration", help="Manage central calibration revisions")
    calibration.add_argument("action", choices=["import", "list", "show"])
    calibration.add_argument("value", nargs="?")
    calibration.add_argument("--registry")
    from . import catalog_cli
    catalog_cli.configure(sub.add_parser("catalog", help="Manage a BigBiax JSON catalog"))
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            run(args.script, registry=args.registry, replay_manifest=args.replay_manifest)
        elif args.command == "gui":
            from .gui import launch
            return launch(args.script, args.registry)
        elif args.command == "catalog":
            catalog_cli.execute(args)
        else:
            registry = Registry(args.registry)
            if args.action == "import":
                if not args.value:
                    parser.error("calibration import needs a JSON file")
                cal = registry.import_file(args.value)
                print(f"Imported {cal.id}\nSHA256 {cal.fingerprint}\nRegistry {registry.root}")
            elif args.action == "list":
                print(f"Registry: {registry.root}")
                for c in registry.list():
                    r = c.record
                    print(f"{c.id}\t{r['category']}\t{r['date']}\t{r['input_unit']} -> {r['output_unit']}")
            else:
                import json
                if not args.value:
                    parser.error("calibration show needs an ID")
                print(json.dumps(registry.get(args.value).record, indent=2))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"REDUCTION NOT PUBLISHED: {exc}", file=sys.stderr)
        return 1
    return 0
