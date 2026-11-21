"""Publish one dashboard.json as the only file on a data branch (force-pushed, no history).

Uses git plumbing, so it never touches the working tree or the checked-out branch,
and works the same on Windows, macOS and Linux self-hosted runners.

  python scripts/publish_data_branch.py <json file> <branch> [remote]
"""
import json
import os
import subprocess
import sys


def git(*args, stdin=None):
    return subprocess.run(["git", *args], input=stdin, capture_output=True, text=True, check=True).stdout.strip()


def main():
    path, branch = sys.argv[1], sys.argv[2]
    remote = sys.argv[3] if len(sys.argv) > 3 else "origin"
    data = json.loads(open(path, encoding="utf-8").read())
    assert len(data.get("top", [])) >= 5, "refusing to publish a ranking with fewer than 5 stocks"

    env = {"GIT_AUTHOR_NAME": "moomoo-refresh", "GIT_AUTHOR_EMAIL": "actions@users.noreply.github.com",
           "GIT_COMMITTER_NAME": "moomoo-refresh", "GIT_COMMITTER_EMAIL": "actions@users.noreply.github.com"}
    os.environ.update(env)

    blob = git("hash-object", "-w", path)
    tree = git("mktree", stdin=f"100644 blob {blob}\tdashboard.json\n")
    commit = git("commit-tree", tree, "-m", f"moomoo data {data['generated_at']}")
    git("push", "--force", remote, f"{commit}:refs/heads/{branch}")
    print(f"published {data['generated_at']} -> {remote}/{branch} ({commit[:8]})")


if __name__ == "__main__":
    main()
