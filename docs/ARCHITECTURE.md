# First implementation boundaries

The public objects are `Session`, `Experiment`, `Channel`, `Records`,
`Calibration`, `Registry`, and `run()`. Top-level cell scripts use the
`load`, `calibration`, `save`, `stop` vocabulary and experiment methods; legacy
scripts retain their supplied Session.

| Module | Responsibility |
|---|---|
| `model.py` | Aligned channels, immutable record IDs, numerical reduction operations |
| `calibration.py` | Definition validation, numerical model evaluation, central revision registry |
| `io.py` | Explicit format readers, text exports, desktop state cache |
| `session.py` | Fresh execution, source fingerprints, provenance, successful-result publication |
| `gui.py` | Docked workspace, worker process, plotting and full-resolution picking |
| `workspace.py` | Cell parser, legacy conversion, sequential execution and prefix replay |
| `workflow.py` | Top-level helpers and explicit BRAVA acquisition profile |
| `kernel_runtime.py` | Kernel namespace hooks and read-only experiment snapshots |
| `console.py` | QtConsole frontend and lifecycle of the separate IPython process |
| `cli.py` | Terminal execution, desktop launch and calibration management |
| `util.py` | Units, canonical serialization and fingerprints |

The numerical layer depends on NumPy/Pint/SciPy, with npTDMS for input. Qt/PyQtGraph
are optional and loaded only for the desktop. The worker executes the same
`run()` function exercised by tests and the terminal. No GUI callback contains
stress, correction or velocity formulas.

## First user review

Review the demo script's readability, selecting/copying original record IDs,
changing calibration revisions, seeing coefficient metadata, modifying velocity
windows, and opening the generated manifest. Then replace placeholder references
in the real TDMS template and compare with your standard reduction.

## Next stages

1. Refine names/defaults and calibration fields after the first operator test.
2. Validate additional Xlook numerical operations against the compiled C
   reference datasets. Mark exact-compatibility algorithms explicitly.
3. Add calibration response/diagnostic plots and calibration measurement fitting,
   without conflating fitted measurements, model definitions and use in a run.
4. Add mechanical-stage composition and operator-controlled spring models.
5. Evaluate the cell/console trial and prefix-replay performance on real records;
   optimize checkpoints only after execution-state semantics are accepted.
6. Add catalogue analysis and publication plotting as consumers of the shared
   experiment model. Rate-and-state remains deferred.

This release has no compatibility claim for the complete Xlook command set.
Its independently tested reference-relative e(F) correction and seconds-based
derivative deliberately have explicit definitions, rather than silently
reproducing the previous package's legacy stiffness and smoothing choices.

Cell execution details and limits: [Cell workspace](CELL_WORKSPACE.md).
