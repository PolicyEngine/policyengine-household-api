#! /usr/bin/env bash

version=$(python -c 'import tomllib; from pathlib import Path; print(tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"])')
git tag "$version"
git push --tags || true  # update the repository version
