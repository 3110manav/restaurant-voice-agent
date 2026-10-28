#!/usr/bin/env bash
# Deploy the realtime voice worker to LiveKit Cloud.
#   First time:  deploy/worker/deploy.sh      (creates the agent; needs deploy/worker/secrets.env)
#   After that:  deploy/worker/deploy.sh      (rolls out the new code to the same agent)
# LiveKit builds from one folder that must hold its own Dockerfile, and the repo root's Dockerfile is the
# API's, so this stages just what the worker needs into deploy/worker/build/ and deploys from there.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
build="$here/build"

command -v lk >/dev/null || { echo "Install the LiveKit CLI first: brew install livekit-cli  (then: lk cloud auth)"; exit 1; }

rm -rf "$build"
mkdir -p "$build"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude 'data/' "$root/app/" "$build/app/"
cp "$here/Dockerfile" "$here/requirements.txt" "$here/.dockerignore" "$build/"

if [ -f "$here/livekit.toml" ]; then
  cp "$here/livekit.toml" "$build/livekit.toml"
  echo "Deploying a new version of the existing agent..."
  lk agent deploy "$build"
else
  secrets="${SECRETS_FILE:-$here/secrets.env}"
  [ -f "$secrets" ] || { echo "Create $secrets first (copy secrets.env.example and fill it in)."; exit 1; }
  echo "Creating the agent on LiveKit Cloud (first time)..."
  lk agent create --secrets-file "$secrets" "$build"
  cp "$build/livekit.toml" "$here/livekit.toml"
  echo
  echo "Saved deploy/worker/livekit.toml. Commit it so later deploys update this same agent."
fi
