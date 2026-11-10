"""Small public API; desktop widgets do not participate in calculations."""
__version__ = "0.4.0"
from .session import Session, run
from .model import Experiment, Channel, Records
from .calibration import Calibration, Registry
from .catalog import Catalog

__all__ = ["Session", "run", "Experiment", "Channel", "Records", "Calibration", "Registry"]
__all__ += ["Catalog"]

from .workflow import load, calibration, save, stop
__all__ += ["load", "calibration", "save", "stop"]
