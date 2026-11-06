#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
set -eu
project_directory=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$project_directory/scripts/sign-repository.py"
