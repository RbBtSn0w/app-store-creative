#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <candidate-id>" >&2
  echo "Set APP_STORE_CREATIVE_CLI to the installed app_store_creative.py runtime." >&2
  exit 64
fi

: "${APP_STORE_CREATIVE_CLI:?Set APP_STORE_CREATIVE_CLI to the installed runtime}"
export PYTHONDONTWRITEBYTECODE=1
if [ -n "${APP_STORE_CREATIVE_PYTHON:-}" ]; then
  creative_python="$APP_STORE_CREATIVE_PYTHON"
elif [ -x /opt/homebrew/bin/python3 ]; then
  creative_python=/opt/homebrew/bin/python3
else
  creative_python=python3
fi
exec "$creative_python" "$APP_STORE_CREATIVE_CLI" candidate validate --repo "$PWD" --id "$1"
