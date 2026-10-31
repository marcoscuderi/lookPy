# GitHub workflow for the operator

## Install the repository once

Keep the checkout in a permanent local folder outside cloud synchronization.
Your raw experiments and reduction scripts can remain in Google Drive.

```bash
mkdir -p "$HOME/Code"
cd "$HOME/Code"
git clone https://github.com/marcoscuderi/lookPy.git
cd lookPy
conda activate xlook
python -m pip install -e ".[gui]"
python -m xlookpy gui
```

If the environment does not exist yet, run `conda env create -f environment.yml`
before activating it. In the GUI, open your existing experiment's reduction.py.
The installed package is still named xlookpy, so no script imports need changing.

## Get an approved update

Close the app first. From this checkout:

```bash
conda activate xlook
git status
git switch main
git pull --ff-only
python -m xlookpy gui
```

If `git status` shows local code changes, preserve them on a separate branch
before switching/updating. Do not delete work or use reset --hard to get past
an error. `--ff-only` stops rather than inventing a merge when histories diverge.
Reinstall with `python -m pip install -e ".[gui]"` when release notes indicate
dependency/version/package metadata changes.

## Test a proposed change

The maintainer will provide the exact branch name. Save local changes, then:

```bash
git fetch origin
git switch feature/the-provided-branch
python -m pip install -e ".[gui]"
python -m xlookpy gui
```

Git creates a tracking branch for a unique matching remote branch. If that
command reports ambiguity or an existing local branch, stop and ask rather
than forcing it. Test with a copied experiment directory if you want to retain
the current experiment.json as well as the per-run result folders.

After testing, return with `git switch main`, reinstall if needed, and restart.
Accept or reject the change in its pull request; scientific choices remain yours.

## Return to the baseline

After the baseline release is published, its tag is v0.1.1a1:

```bash
git fetch origin --tags
git switch --detach v0.1.1a1
python -m pip install -e ".[gui]"
python -m xlookpy gui
```

Detached mode runs an exact historical release. For developing from that point,
create a branch instead: `git switch -c recovery/my-change v0.1.1a1`.
Use `git switch main` to return. The tag is created only after initial tests pass;
if it is not available yet, check GitHub Actions rather than guessing a tag.

## What lives where

| Material | Location |
|---|---|
| Application, tests, synthetic examples, documentation | This repository |
| Real calibration revisions | Central registry, outside this checkout |
| Raw measurements and operator reduction scripts | Experiment directories |
| Per-run snapshots and calibration definitions actually used | Experiment manifests/results |

This public repository contains no real TDMS inputs or measured calibration
values. GitHub is not a replacement for raw-data backup. Git commit/dirty-state
recording in experiment manifests is tracked as a follow-up; the baseline
currently records application version, full script, calibrations and input hashes.
