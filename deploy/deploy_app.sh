#!/usr/bin/env bash
# Deploy of an installed copy of AgentHub. Installed on the server as the only command the
# GitHub Actions deploy key may run (~/.ssh/authorized_keys), so the workflow can do
# nothing else: it reads a gzipped tar of the built web/dist on stdin, moves the checkout
# to origin/main, installs the built UI, restarts the pm2 app when the push changed more
# than the UI, checks that the app answers, and goes back to the commit and the UI that
# were running when it does not.
#
# The SSH command the client asks for (SSH_ORIGINAL_COMMAND) is not run: it is the commit
# the UI was built from, or `check`, which tests the key and changes nothing. Only the
# commit origin/main points at is deployed; an upload for any other commit changes nothing.
# Every line it prints about a deploy is also appended to ~/agenthub-deploy/deploy.log
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/AgentHub}"                      # the checkout the pm2 app runs from
DEPLOY_DIR="${DEPLOY_DIR:-$HOME/agenthub-deploy}"
ECOSYSTEM="${ECOSYSTEM:-$DEPLOY_DIR/ecosystem.config.js}"   # the pm2 definition of the app
APP_URL="${APP_URL:-http://127.0.0.1:8787}"
BRANCH="main"
PRIVATE_BRANCH="main"                                     # the branch the app pushes the private folder to
MAX_BYTES=$((50 * 1024 * 1024))                           # largest upload accepted
HEALTH_TRIES="${HEALTH_TRIES:-40}"                        # seconds a restarted app gets to answer
LOCK_WAIT="${LOCK_WAIT:-300}"                             # seconds to wait for a deploy that is still running
# A push that changes only these paths needs no restart: the server reads the UI from
# web/dist at every request, and never reads the other three. A restart interrupts the
# tasks that are running, so it is made only when something else changed.
NO_RESTART=(web .github deploy README.md)
LOG="$DEPLOY_DIR/deploy.log"
UPLOAD="$DEPLOY_DIR/dist.upload"
PREVIOUS="$DEPLOY_DIR/dist.previous"                      # the UI that ran before the last deploy

# a non-interactive SSH session starts with a short PATH; uv is in ~/.local/bin, pm2 in /usr/local/bin
export PATH="$HOME/.local/bin:$PATH:/usr/local/bin:/usr/bin:/bin"
mkdir -p "$DEPLOY_DIR"

request="${SSH_ORIGINAL_COMMAND:-}"
if [ "$request" = "check" ]; then
  echo "deploy key works; the app is on $(git -C "$APP_DIR" rev-parse --short HEAD)"
  exit 0
fi
if [[ ! "$request" =~ ^[0-9a-f]{40}$ ]]; then
  echo "expected the commit the UI was built from (40 hex characters) or \`check\`; nothing changed"
  exit 1
fi
sha="$request"

# One deploy at a time. flock keeps the lock itself (-o) and runs this script again under
# it, so nothing a deploy starts can keep the lock after the deploy has ended.
if [ "${AGENTHUB_DEPLOY_LOCKED:-}" != 1 ]; then
  export AGENTHUB_DEPLOY_LOCKED=1
  rc=0
  flock -w "$LOCK_WAIT" -o -E 75 "$DEPLOY_DIR/deploy.lock" bash "$0" || rc=$?
  if [ "$rc" -eq 75 ]; then echo "another deploy is still running; nothing changed"; rc=1; fi
  exit "$rc"
fi

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"; }

answers() {   # the API answers and the page served is the one in web/dist
  curl -fsS -o /dev/null --max-time 5 "$APP_URL/api/tasks" 2>/dev/null &&
    curl -fsS --max-time 5 "$APP_URL/" 2>/dev/null | cmp -s - "$APP_DIR/web/dist/index.html"
}

healthy() {
  local i
  for i in $(seq 1 "$HEALTH_TRIES"); do
    if answers; then return 0; fi
    sleep 1
  done
  return 1
}

restart_app() {
  uv sync --locked --quiet 2> >(tee -a "$LOG" >&2) || return 1
  # pm2 gets nothing of the SSH session: when it has to start its own daemon, the daemon
  # would keep the session, and with it the workflow run, open for as long as it lives
  pm2 startOrReload "$ECOSYSTEM" --update-env </dev/null >/dev/null 2>>"$LOG"
}

# 1. the upload: unpacked beside the app, checked, and installed only further down
rm -rf "$UPLOAD"
mkdir -p "$UPLOAD"
if ! head -c "$MAX_BYTES" | tar -xzf - -C "$UPLOAD" --no-same-owner 2> >(tee -a "$LOG" >&2); then
  rm -rf "$UPLOAD"
  log "the upload for ${sha:0:7} could not be unpacked; nothing changed"
  exit 1
fi
# only plain files and folders: the app serves what is in web/dist, so an uploaded symlink
# could publish any file this account can read
if [ -n "$(find "$UPLOAD" ! -type f ! -type d -print -quit)" ]; then
  rm -rf "$UPLOAD"
  log "the upload for ${sha:0:7} contains a symlink or a special file; nothing changed"
  exit 1
fi
if [ ! -f "$UPLOAD/index.html" ]; then
  rm -rf "$UPLOAD"
  log "the upload for ${sha:0:7} has no index.html; nothing changed"
  exit 1
fi

cd "$APP_DIR"

# 2. which commit: only the one origin/main points at
if ! git fetch --quiet origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"; then
  rm -rf "$UPLOAD"
  log "fetch of origin/$BRANCH failed; nothing changed"
  exit 1
fi
target=$(git rev-parse "origin/$BRANCH")
current=$(git rev-parse HEAD)

if [ "$sha" != "$target" ]; then
  rm -rf "$UPLOAD"
  if git merge-base --is-ancestor "$sha" "$target" 2>/dev/null; then
    echo "origin/$BRANCH is already at ${target:0:7}; the upload for ${sha:0:7} is left to the run of that commit"
    exit 0
  fi
  log "the upload is for ${sha:0:7}, which is not on origin/$BRANCH (${target:0:7}); nothing changed"
  exit 1
fi
if [ "$(git symbolic-ref -q --short HEAD || true)" != "$BRANCH" ]; then
  rm -rf "$UPLOAD"
  log "the checkout is not on the branch $BRANCH (HEAD is ${current:0:7}); nothing changed. \`git checkout $BRANCH\` on the server, then run the workflow again"
  exit 1
fi
if [ "$target" = "$current" ] && diff -rq "$UPLOAD" web/dist >/dev/null 2>&1 && answers; then
  rm -rf "$UPLOAD"
  echo "already on ${target:0:7} with this UI; nothing to deploy"
  exit 0
fi

restart=false
if [ "$target" != "$current" ]; then
  excluded=()
  for path in "${NO_RESTART[@]}"; do excluded+=(":(exclude)$path"); done
  if ! git diff --quiet "$current" "$target" -- . "${excluded[@]}"; then restart=true; fi
fi
# an app that does not answer before the deploy is started by it
if ! answers; then restart=true; fi

log "deploying origin/$BRANCH: ${current:0:7} -> ${target:0:7} ($([ "$restart" = true ] && echo "with a restart" || echo "UI only, no restart"))"

swapped=false
go_back() {   # to the commit and the UI that were running; always ends the script with 1
  log "$1; going back to ${current:0:7}"
  if [ "$swapped" = true ]; then
    rm -rf "$DEPLOY_DIR/dist.failed"
    mv web/dist "$DEPLOY_DIR/dist.failed"
    if [ -d "$PREVIOUS" ]; then mv "$PREVIOUS" web/dist; fi
  else
    rm -rf "$UPLOAD"
  fi
  # --keep moves the branch back and refuses, instead of overwriting, a file edited on the server
  git reset --quiet --keep "$current" 2> >(tee -a "$LOG" >&2) || log "the checkout could not be moved back to ${current:0:7}"
  # a UI-only deploy never restarted the app, so going back needs no restart either
  if [ "$restart" = true ] || ! answers; then
    restart_app || true
  fi
  if healthy; then
    log "back on ${current:0:7}"
  else
    log "ROLLBACK FAILED: ${current:0:7} does not answer either"
  fi
  exit 1
}

# 3. the code: fast-forward only, so commits or edits made on the server stop the deploy
if ! git merge --quiet --ff-only "$target" 2> >(tee -a "$LOG" >&2) || [ "$(git rev-parse HEAD)" != "$target" ]; then
  rm -rf "$UPLOAD"
  git reset --quiet --keep "$current" 2>/dev/null || true
  log "the checkout cannot be fast-forwarded to ${target:0:7} (commits or edits on the server?); still on ${current:0:7}"
  exit 1
fi

# 4. the private folder (a submodule the app itself commits to and pushes): it only has to
#    contain the commit this version records, so a copy that is ahead is left alone
recorded=$(git rev-parse "$target:private" 2>/dev/null || true)
if [ -n "$recorded" ]; then
  if [ ! -e private/.git ]; then
    git submodule update --quiet --init private 2> >(tee -a "$LOG" >&2) || go_back "the private folder could not be fetched"
  elif ! git -C private merge-base --is-ancestor "$recorded" HEAD 2>/dev/null; then
    git -C private pull --quiet --ff-only origin "$PRIVATE_BRANCH" 2> >(tee -a "$LOG" >&2) || true
    git -C private merge-base --is-ancestor "$recorded" HEAD 2>/dev/null ||
      go_back "the private folder does not contain ${recorded:0:7}, the commit ${target:0:7} records, and could not be fast-forwarded to it"
  fi
fi

# 5. the UI, then the app
rm -rf "$PREVIOUS"
if [ -d web/dist ]; then mv web/dist "$PREVIOUS"; fi
mv "$UPLOAD" web/dist
swapped=true

if [ "$restart" = true ]; then
  restart_app || go_back "${target:0:7} could not be installed or started"
fi
if healthy; then
  log "deployed ${target:0:7}"
  exit 0
fi
go_back "${target:0:7} does not answer at $APP_URL"
