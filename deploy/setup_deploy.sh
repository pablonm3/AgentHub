#!/usr/bin/env bash
# One-time setup of the GitHub Actions deploy (.github/workflows/deploy.yml). Run it
# yourself in a terminal on your own computer; it asks for the server password once and
# never stores it. Needs ssh, the GitHub CLI (`gh`, logged in) and the server's host key
# in your known_hosts (log in to the server once before). The app must already be
# installed on the server: a clone in ~/AgentHub on the branch main, run by pm2 from
# ~/agenthub-deploy/ecosystem.config.js.
#
#   usage: deploy/setup_deploy.sh <user@host> [<owner/repo>]
#
#   1. creates a deploy key on this computer (~/.ssh/agenthub_deploy);
#   2. copies deploy_app.sh to ~/agenthub-deploy/ on the server and lets that key run
#      only that script;
#   3. checks that the key works, without deploying anything;
#   4. stores the key, the server's host key and the login as secrets of the GitHub repo.
#
# Safe to run again (do, after changing deploy_app.sh): it reuses the key and replaces
# its line on the server. SETUP_CONTROL_PATH reuses an SSH connection you already opened
# with -o ControlMaster=yes -o ControlPath=<that path>, instead of asking for the password.
set -euo pipefail

TARGET="${1:?usage: deploy/setup_deploy.sh <user@host> [<owner/repo>]}"
HOST="${TARGET#*@}"
REPO="${2:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
KEY="$HOME/.ssh/agenthub_deploy"
KEY_COMMENT="github-actions-deploy AgentHub"
HERE="$(cd "$(dirname "$0")" && pwd)"
CTL="${SETUP_CONTROL_PATH:-$HOME/.ssh/cm-ah-setup-%C}"

echo "1/4 deploy key"
if [ ! -f "$KEY" ]; then
  # no passphrase: GitHub Actions uses the key unattended
  ssh-keygen -q -t ed25519 -N "" -C "$KEY_COMMENT" -f "$KEY"
  echo "    created $KEY"
else
  echo "    reusing $KEY"
fi
PUB="$(cat "$KEY.pub")"

echo "2/4 server"
if ssh -O check -o ControlPath="$CTL" "$TARGET" 2>/dev/null; then
  echo "    reusing the open connection"
else
  echo "    your password is asked once (not at all when one of your own keys logs in)"
  # IdentitiesOnly: deploy keys held by your ssh-agent would log in to their deploy
  # script instead of a shell
  ssh -o IdentitiesOnly=yes -o ControlMaster=yes -o ControlPath="$CTL" -o ControlPersist=120 -fN "$TARGET"
  trap 'ssh -O exit -o ControlPath="$CTL" "$TARGET" 2>/dev/null || true' EXIT
fi
ssh -o ControlPath="$CTL" "$TARGET" 'mkdir -p ~/agenthub-deploy'
scp -q -o ControlPath="$CTL" "$HERE/deploy_app.sh" "$TARGET:agenthub-deploy/deploy_app.sh"
ssh -o ControlPath="$CTL" "$TARGET" bash -s <<EOF
set -e
chmod 700 ~/agenthub-deploy/deploy_app.sh
install -d -m 700 ~/.ssh
touch ~/.ssh/authorized_keys
grep -v "$KEY_COMMENT" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.new || true
echo "restrict,command=\"\$HOME/agenthub-deploy/deploy_app.sh\" $PUB" >> ~/.ssh/authorized_keys.new
chmod 600 ~/.ssh/authorized_keys.new
mv ~/.ssh/authorized_keys.new ~/.ssh/authorized_keys
echo "    script installed; the deploy key may run only that script"
EOF

echo "3/4 check: log in with the deploy key (the script answers \`check\` without deploying)"
# IdentityAgent=none: a key of your own held by your ssh-agent would be tried first and
# log in to a shell. AddKeysToAgent=no keeps the deploy key out of the agent, where it
# would take over your own logins to the server
ssh -i "$KEY" -o IdentitiesOnly=yes -o IdentityAgent=none -o AddKeysToAgent=no -o BatchMode=yes "$TARGET" check | sed 's/^/    /'

echo "4/4 GitHub secrets of $REPO"
gh secret set DEPLOY_KEY --repo "$REPO" < "$KEY"
ssh-keygen -F "$HOST" | grep -v '^#' | gh secret set DEPLOY_KNOWN_HOSTS --repo "$REPO"
printf '%s' "$TARGET" | gh secret set DEPLOY_TARGET --repo "$REPO"

echo "done: the next push to main of $REPO deploys by itself"
