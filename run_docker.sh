#!/usr/bin/env bash
# Build (cached, so quick after the first time) and start the dev container,
# with git, gh and a ready-to-use virtualenv set up. Usage:
#   ./run_docker.sh            # shell in the container
#   ./run_docker.sh claude     # straight into Claude
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$HOME/.config/claude-docker/env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE (should contain GH_TOKEN=...)" >&2
  exit 1
fi

docker build -q \
  --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" \
  -t ysesiwn-claude -f "$REPO/.devcontainer/Dockerfile" "$REPO/.devcontainer" \
  >/dev/null

SETUP='
set -e
gh auth setup-git
git config --global url."https://github.com/".insteadOf git@github.com:
git config --global --add safe.directory /work
uv venv -q /tmp/venv
. /tmp/venv/bin/activate
uv pip install -q -r requirements-dev.txt
exec "${@:-bash}"
'

docker run -it --rm \
  --env-file "$ENV_FILE" \
  -v "$REPO:/work" \
  -v claude-home:/home/pwuser/.claude \
  -v uv-cache:/home/pwuser/.cache/uv \
  ysesiwn-claude bash -c "$SETUP" setup "$@"
