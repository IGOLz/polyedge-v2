#!/usr/bin/env bash
set -euo pipefail

deploy_user="codexdeploy"
repo_root="/opt/stacks/polyedge-v2"
public_key=""
public_key_file=""
skip_chown=0

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
gate_src="${script_dir}/polyedge-codex-gate.sh"
helper_src="${script_dir}/polyedge-codex-compose.sh"
gate_dst="/usr/local/bin/polyedge-codex-gate"
helper_dst="/usr/local/bin/polyedge-codex-compose"
sudoers_file="/etc/sudoers.d/polyedge-codex-compose"
tmp_gate=""
tmp_helper=""

usage() {
  cat <<'EOF'
Usage:
  sudo bash install-lxc-codex-access.sh --public-key-file /tmp/codex.pub [options]

Options:
  --deploy-user USER       Remote restricted user (default: codexdeploy)
  --repo-root PATH         Repo root to manage (default: /opt/stacks/polyedge-v2)
  --public-key KEY         SSH public key content to authorize
  --public-key-file PATH   File containing the SSH public key to authorize
  --skip-chown             Leave existing repo ownership unchanged
  --help                   Show this help text
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$tmp_gate" && -f "$tmp_gate" ]]; then
    rm -f "$tmp_gate"
  fi
  if [[ -n "$tmp_helper" && -f "$tmp_helper" ]]; then
    rm -f "$tmp_helper"
  fi
}

trap cleanup EXIT

while (($# > 0)); do
  case "$1" in
    --deploy-user)
      deploy_user="$2"
      shift 2
      ;;
    --repo-root)
      repo_root="$2"
      shift 2
      ;;
    --public-key)
      public_key="$2"
      shift 2
      ;;
    --public-key-file)
      public_key_file="$2"
      shift 2
      ;;
    --skip-chown)
      skip_chown=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument '$1'"
      ;;
  esac
done

((EUID == 0)) || die "run this installer as root"
[[ -f "$gate_src" ]] || die "missing gate source at $gate_src"
[[ -f "$helper_src" ]] || die "missing helper source at $helper_src"
[[ -d "$repo_root" ]] || die "repo root not found at $repo_root"
[[ -f "$repo_root/docker-compose.yml" ]] || die "docker-compose.yml not found under $repo_root"
command -v docker >/dev/null 2>&1 || die "docker is required on the LXC"
command -v sudo >/dev/null 2>&1 || die "sudo is required on the LXC"

if [[ -n "$public_key_file" ]]; then
  [[ -f "$public_key_file" ]] || die "public key file not found at $public_key_file"
  public_key="$(tr -d '\r' <"$public_key_file")"
fi

[[ -n "$public_key" ]] || die "a public key is required via --public-key or --public-key-file"
[[ "$public_key" =~ ^ssh-(ed25519|rsa|ecdsa)[[:space:]] ]] || die "public key format is not recognized"

if ! getent group "$deploy_user" >/dev/null 2>&1; then
  groupadd "$deploy_user"
fi

if id -u "$deploy_user" >/dev/null 2>&1; then
  usermod --shell /bin/bash --gid "$deploy_user" "$deploy_user"
else
  useradd --create-home --shell /bin/bash --gid "$deploy_user" "$deploy_user"
fi

install -d -m 700 -o "$deploy_user" -g "$deploy_user" "/home/${deploy_user}/.ssh"
touch "/home/${deploy_user}/.ssh/authorized_keys"
chown "$deploy_user:$deploy_user" "/home/${deploy_user}/.ssh/authorized_keys"
chmod 600 "/home/${deploy_user}/.ssh/authorized_keys"

authorized_key_line="restrict,command=\"${gate_dst}\" ${public_key}"
if ! grep -Fqx "$authorized_key_line" "/home/${deploy_user}/.ssh/authorized_keys"; then
  printf '%s\n' "$authorized_key_line" >>"/home/${deploy_user}/.ssh/authorized_keys"
fi

escaped_repo_root="${repo_root//&/\\&}"
tmp_gate="$(mktemp)"
tmp_helper="$(mktemp)"
sed "s|^readonly REPO_ROOT=.*$|readonly REPO_ROOT=\"${escaped_repo_root}\"|" "$gate_src" >"$tmp_gate"
sed "s|^readonly REPO_ROOT=.*$|readonly REPO_ROOT=\"${escaped_repo_root}\"|" "$helper_src" >"$tmp_helper"

install -o root -g root -m 0755 "$tmp_gate" "$gate_dst"
install -o root -g root -m 0755 "$tmp_helper" "$helper_dst"

cat >"$sudoers_file" <<EOF
Defaults:${deploy_user} !requiretty
${deploy_user} ALL=(root) NOPASSWD: ${helper_dst} *
EOF
chmod 440 "$sudoers_file"

if command -v visudo >/dev/null 2>&1; then
  visudo -cf "$sudoers_file" >/dev/null
fi

if ((skip_chown == 0)); then
  chown -R "${deploy_user}:${deploy_user}" "$repo_root"
fi

cat <<EOF
Installed restricted Codex SSH access.

Remote user: ${deploy_user}
Repo root:   ${repo_root}
Gate:        ${gate_dst}
Helper:      ${helper_dst}

Next checks:
  1. Verify the repo remote can git pull as ${deploy_user}.
  2. Test: ssh polyedge-lxc-codex status
  3. Test: ssh polyedge-lxc-codex restart trading
  4. Confirm: ssh polyedge-lxc-codex restart core fails
EOF
