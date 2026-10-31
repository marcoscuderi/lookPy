"""Create the initial approved checkpoint after CI, without moving existing tags."""
import json
import os
from pathlib import Path
import tomllib
from urllib.error import HTTPError
from urllib.request import Request, urlopen

repository = os.environ["GITHUB_REPOSITORY"]
sha = os.environ["GITHUB_SHA"]
version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
tag = "v0.1.1a1"


def api(path, data=None):
    request = Request(
        f"https://api.github.com/repos/{repository}/{path}",
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer "+os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404 and data is None:
            return None
        raise


if version != "0.1.1a1":
    print("Application has moved beyond the baseline; no baseline tag created.")
else:
    ref = api(f"git/ref/tags/{tag}")
    if ref is None:
        api("git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
        ref = api(f"git/ref/tags/{tag}")
    # Tag remains immutable; never re-point it at a later main commit.
    if api(f"releases/tags/{tag}") is None:
        api("releases", {"tag_name": tag, "name": "lookPy approved baseline 0.1.1a1",
                         "body": Path("docs/releases/v0.1.1a1.md").read_text(),
                         "draft": False, "prerelease": True})
    print(f"Approved baseline checkpoint available: {tag}")
