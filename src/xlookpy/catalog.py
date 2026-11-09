"""One apparatus catalog with immutable calibration revisions.

Defaults are suggestions for an operator, never automatic reduction selections.
Updates use a lock and atomic replacement; errors leave the previous file intact.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from .calibration import Calibration


class Catalog:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    @staticmethod
    def empty():
        return {"schema_version": 1, "apparatus": "BigBiax",
                "description": "Private calibration history; no numerical defaults supplied.",
                "records": [], "suggested_defaults": {}}

    def read(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or data.get("apparatus") != "BigBiax":
            raise ValueError("Expected a schema_version=1 BigBiax catalog.")
        if not isinstance(data.get("records"), list) or not isinstance(data.get("suggested_defaults"), dict):
            raise ValueError("Catalog needs records and suggested_defaults.")
        seen = set()
        for record in data["records"]:
            cal = self.validate_record(record)
            if cal.id in seen:
                raise ValueError(f"Duplicate calibration ID: {cal.id}")
            seen.add(cal.id)
        for name, identifier in data["suggested_defaults"].items():
            if not isinstance(name, str) or identifier not in seen:
                raise ValueError("Suggested defaults must reference existing exact IDs.")
        return data

    @staticmethod
    def validate_record(record):
        cal = Calibration(record)
        if record["apparatus"] != "BigBiax" or not cal.id.startswith("BigBiax/"):
            raise ValueError("Catalog records require apparatus BigBiax and ID BigBiax/…")
        purpose = record.get("purpose")
        if purpose not in ("acquisition", "auxiliary", "elastic"):
            raise ValueError("purpose must be acquisition, auxiliary or elastic.")
        if (purpose == "elastic") != (record["category"] == "apparatus"):
            raise ValueError("Elastic records use category apparatus; acquisition/auxiliary use sensor.")
        for key in ("configuration", "source"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"Catalog records need a nonempty {key}.")
        if purpose in ("acquisition", "auxiliary"):
            if not isinstance(record.get("gain"), str) or not record["gain"].strip():
                raise ValueError("Sensor records need gain (low, high, or an explicit description).")
        return cal

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError(f"Catalog is locked: {lock}. Retry after the other writer finishes; inspect stale locks after a crash.") from None
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def _write(self, data):
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def initialize(self):
        with self._locked():
            if self.path.exists():
                self.read()
            else:
                self._write(self.empty())
        return self.path

    def list(self):
        return [Calibration(r) for r in self.read()["records"]]

    def get(self, identifier):
        for cal in self.list():
            if cal.id == identifier:
                return cal
        raise FileNotFoundError(f"Calibration {identifier!r} is not in {self.path}.")

    def add(self, record):
        cal = self.validate_record(record)
        with self._locked():
            data = self.read()
            existing = {r["id"]: Calibration(r) for r in data["records"]}
            if cal.id in existing:
                if existing[cal.id].fingerprint != cal.fingerprint:
                    raise ValueError(f"{cal.id} already exists. Use a new revision ID; old records are immutable.")
                return cal
            data["records"].append(deepcopy(record))
            self._write(data)
        return cal

    def suggest(self, slot, identifier):
        if not isinstance(slot, str) or not slot.strip():
            raise ValueError("A nonempty suggestion name is required.")
        with self._locked():
            data = self.read()
            if identifier not in {r["id"] for r in data["records"]}:
                raise ValueError("Select an existing exact calibration ID.")
            data["suggested_defaults"][slot] = identifier
            self._write(data)
