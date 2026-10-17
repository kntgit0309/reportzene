#!/bin/bash
# Auto deploy on the server (macminiwork): launchd runs this every minute; when GitHub `main` has a new commit it
# tests it, builds the web app, publishes it to ~/reportzene and restarts the app. Collaborators only push (or merge
# a PR) to main: nobody needs SSH. A commit whose tests or build fail is never deployed (and not retried).
#
#   clone (read-only deploy key, host alias github-reportzene):  ~/reportzene-autodeploy/repo
#   state / log:     ~/reportzene-autodeploy/{deployed_sha,failed_sha,autodeploy.log,last_tests.log,last_build.log}
#   installed copy:  ~/reportzene-autodeploy/autodeploy.sh  (refreshed after every successful deploy)
#   launchd:         com.isuccess.reportzene-autodeploy (StartInterval 60)
#
# The app's own launchd plist (secrets: SSO key/secret, allow-list) is never touched here: change it with
# deploy/deploy.sh from a machine that has SSH access.
set -uo pipefail
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin

HOME_DIR=~/reportzene-autodeploy
SRC=$HOME_DIR/repo
APP=~/reportzene
LABEL=online.kntmcptools.reportzene
HEALTH=http://100.96.215.29:8870/api/health
LOCK=$HOME_DIR/lock
STALE_LOCK_MINUTES=30   # a run killed mid-way (reboot, crash) must not block auto deploy forever
OLD_ASSET_DAYS=7        # chunks of older builds kept so tabs opened before a deploy still load their pages
HEALTH_TRIES=15

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$HOME_DIR/autodeploy.log"; }

[ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +$STALE_LOCK_MINUTES)" ] && rmdir "$LOCK"
mkdir "$LOCK" 2>/dev/null || exit 0   # another run is still in progress
trap 'rmdir "$LOCK"' EXIT

cd "$SRC" || { log "missing clone $SRC"; exit 1; }
git fetch -q origin main || { log "git fetch failed"; exit 1; }
NEW=$(git rev-parse origin/main)
[ "$NEW" = "$(cat "$HOME_DIR/deployed_sha" 2>/dev/null)" ] && exit 0
[ "$NEW" = "$(cat "$HOME_DIR/failed_sha" 2>/dev/null)" ] && exit 0   # already tried and failed: wait for a fix

log "new main ${NEW:0:7}: $(git log -1 --format='%s (%an)' "$NEW")"
git reset -q --hard "$NEW"
git clean -qfdx -e .venv -e node_modules

if ! (cd backend && uv sync -q && uv run pytest -q -p no:cacheprovider >"$HOME_DIR/last_tests.log" 2>&1); then
  echo "$NEW" >"$HOME_DIR/failed_sha"
  log "tests FAILED for ${NEW:0:7}, not deployed: $(tail -1 "$HOME_DIR/last_tests.log")"
  exit 1
fi
log "tests passed: $(tail -1 "$HOME_DIR/last_tests.log")"

if ! (cd web && npm ci --no-audit --no-fund --silent && npm run build --silent) >"$HOME_DIR/last_build.log" 2>&1; then
  echo "$NEW" >"$HOME_DIR/failed_sha"
  log "web build FAILED for ${NEW:0:7}, not deployed (see last_build.log)"
  exit 1
fi

rsync -a --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.coverage' --exclude '.ruff_cache' \
  --exclude 'data/' --exclude '.env' \
  backend/ "$APP/backend/"
mkdir -p "$APP/web/dist/assets"
rsync -a --delete --exclude 'assets/' web/dist/ "$APP/web/dist/"
rsync -a web/dist/assets/ "$APP/web/dist/assets/"
find "$APP/web/dist/assets" -type f -mtime +$OLD_ASSET_DAYS -delete
(cd "$APP/backend" && { uv sync --frozen --no-dev -q 2>/dev/null || uv sync --no-dev -q; }) || { log "uv sync on the app failed"; exit 1; }
launchctl kickstart -k "gui/$(id -u)/$LABEL"

for _ in $(seq 1 $HEALTH_TRIES); do
  if curl -fsS "$HEALTH" >/dev/null 2>&1; then
    echo "$NEW" >"$HOME_DIR/deployed_sha"
    cp deploy/autodeploy.sh "$HOME_DIR/autodeploy.sh"   # pick up changes to this script itself
    log "deployed ${NEW:0:7} OK"
    exit 0
  fi
  sleep 2
done
log "app did not come back after deploying ${NEW:0:7}: check $APP/logs/server.log"
exit 1
