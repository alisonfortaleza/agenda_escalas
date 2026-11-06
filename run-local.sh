#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
export APP_ENV=local
export SEED_DEMO=1
export BOOTSTRAP_LOCAL=1
exec python3 -m app.server
