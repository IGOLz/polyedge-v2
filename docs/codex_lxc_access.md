# Codex Restricted SSH Access for the PolyEdge LXC

This repo includes a restricted SSH workflow so Codex can operate the PolyEdge LXC without getting a normal shell.

The protected root is `/opt/stacks/polyedge-v2`. Codex connects through the local SSH alias `polyedge-lxc-codex` and can only run a short allowlist of commands. It cannot browse the filesystem, run arbitrary `docker` commands, use `sudo`, or touch `core` and `timescaledb`.

## How the logic works

- The Windows machine holds a dedicated SSH key just for Codex-to-LXC access.
- The LXC user is `codexdeploy`, not your normal admin user.
- `authorized_keys` forces every connection through `polyedge-codex-gate`.
- The gate reads the requested SSH command and only accepts approved verbs.
- Approved Docker actions are delegated to a root-owned helper that always runs inside `/opt/stacks/polyedge-v2`.
- `core` and `timescaledb` are blocked even if someone asks for them explicitly.

The effect is that Codex can do project operations such as `git pull`, `build`, `up`, `down`, `restart`, `logs`, and `safe-update`, but it does not receive a shell on the LXC.

## Files

- `ops/codex-lxc/install-local-codex-ssh.ps1`: generates the dedicated Windows SSH key and appends the `polyedge-lxc-codex` host alias.
- `ops/codex-lxc/bootstrap-remote-install.ps1`: copies the installer bundle to the LXC and runs it with an admin account.
- `ops/codex-lxc/install-lxc-codex-access.sh`: idempotent LXC installer that creates `codexdeploy`, installs the gate/helper, and wires `authorized_keys` plus `sudoers`.
- `ops/codex-lxc/polyedge-codex-gate.sh`: forced-command SSH gate.
- `ops/codex-lxc/polyedge-codex-compose.sh`: root-owned helper used via tightly scoped `sudo`.

## One-time setup from Windows

Run on the Windows PC where you use Codex:

```powershell
cd C:\Users\igol\Documents\GitHub\polyedge-v2
powershell -ExecutionPolicy Bypass -File .\ops\codex-lxc\install-local-codex-ssh.ps1
```

That creates:

- `~/.ssh/codex_polyedge_lxc_ed25519`
- `~/.ssh/codex_polyedge_lxc_ed25519.pub`
- a `Host polyedge-lxc-codex` block in `~/.ssh/config`

Then bootstrap the LXC using the admin account you already use to SSH in by IP, username, and password.

If that admin account is `root`:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\codex-lxc\bootstrap-remote-install.ps1 -AdminUser root
```

If that admin account is a normal user with `sudo`:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\codex-lxc\bootstrap-remote-install.ps1 -AdminUser youradmin -UseSudo
```

During this one-time install, you type the SSH password yourself when prompted. After the install finishes, Codex uses the dedicated key and does not need the password-based admin login anymore.

## Day-to-day commands Codex can run

All day-to-day actions go through:

```bash
ssh polyedge-lxc-codex <command>
```

### Status and update

```bash
ssh polyedge-lxc-codex status
ssh polyedge-lxc-codex git-pull
ssh polyedge-lxc-codex safe-update
```

- `status` shows the current git commit hash and running Compose containers.
- `git-pull` runs `git pull --ff-only` inside `/opt/stacks/polyedge-v2`.
- `safe-update` runs `git pull --ff-only`, rebuilds approved services, and starts them again without touching `core`.

### Build and start services

```bash
ssh polyedge-lxc-codex build trading
ssh polyedge-lxc-codex build trading-weather
ssh polyedge-lxc-codex build wallet-tracker
ssh polyedge-lxc-codex build trading trading-weather dashboard
ssh polyedge-lxc-codex up trading
ssh polyedge-lxc-codex up trading-weather
ssh polyedge-lxc-codex up wallet-tracker
ssh polyedge-lxc-codex up trading trading-weather
```

- Use `build` when you want a fresh image rebuild.
- Use `up` when a service is currently stopped or has never been created on that LXC.
- If `trading` is disabled right now, Codex can still start it with `ssh polyedge-lxc-codex up trading`.

### Stop and restart services

```bash
ssh polyedge-lxc-codex down trading
ssh polyedge-lxc-codex down trading-weather
ssh polyedge-lxc-codex down wallet-tracker
ssh polyedge-lxc-codex down trading trading-weather
ssh polyedge-lxc-codex restart trading
ssh polyedge-lxc-codex restart trading-weather
ssh polyedge-lxc-codex restart wallet-tracker
```

- `down <service>` is the restricted stop command for an individual service.
- `restart <service>` should be used only after that service already exists.
- If a service was never started before, prefer `up` instead of `restart`.

### Logs

```bash
ssh polyedge-lxc-codex logs trading 100
ssh polyedge-lxc-codex logs trading-weather 100
ssh polyedge-lxc-codex logs wallet-tracker 100
ssh polyedge-lxc-codex logs dashboard 200
```

- The number at the end is the number of lines to fetch.
- This is useful for checking whether a service started correctly after `up`, `restart`, or `safe-update`.

## Allowed services

The current allowlist is:

- `analysis`
- `trading`
- `dashboard`
- `weather`
- `trading-weather`
- `wallet-tracker`
- `core-debug`

## Updating The Remote Helper

The restricted LXC gate/helper is installed as a root-owned copy in `/usr/local/bin`, not as a live wrapper around the repo files. After changing `ops/codex-lxc/polyedge-codex-gate.sh` or `ops/codex-lxc/polyedge-codex-compose.sh`, you must rerun the admin bootstrap/install flow so the remote helper picks up the new allowlist.

## Blocked actions

The gate rejects:

- interactive shell access
- `core`
- `timescaledb`
- arbitrary `docker`, `docker exec`, `docker run`, or `sudo`
- filesystem commands such as `pwd`, `ls`, or `cat`

Examples that should fail:

```bash
ssh polyedge-lxc-codex restart core
ssh polyedge-lxc-codex docker ps
ssh polyedge-lxc-codex pwd
```

## Remaining manual checks

- Ensure the LXC repo remote can `git pull` as `codexdeploy`.
- Restrict SSH on the LXC or Proxmox firewall to this laptop's LAN IP.
- Verify `ssh polyedge-lxc-codex restart core` fails.
