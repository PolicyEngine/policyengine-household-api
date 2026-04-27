#!/bin/bash

set -euo pipefail

uv run pytest --confcutdir=tests/deployed tests/deployed -v
