# Codex Database Access on Windows

This repo includes a local database gate so Codex can query PostgreSQL from the Windows machine without defaulting to raw `psql`.

This is a **soft guard**, not a hard sandbox. The normal path is read-only and uses a dedicated `codex_ro` database role, but the write-capable app credential still exists in `.env` inside the Codex-visible workspace.

## How it works

- Default reads go through `ops/codex-db/run-query.ps1` without `-Write`.
- Read mode loads `.env.codex-db`, connects as `codex_ro`, sets `default_transaction_read_only=on`, and rejects psql meta-commands.
- Rare writes use the same wrapper with `-Write`, but only while a local unlock file exists under `%LOCALAPPDATA%\PolyEdge\codex-db\`.
- Every wrapper run appends a JSON audit entry with mode, SQL hash, preview, success/failure, and result summary.

Codex should use the wrapper only. For writes, Codex should show you the exact SQL first, then wait for you to run `unlock-write.ps1`.

## Files

- `ops/codex-db/bootstrap-readonly-role.ps1`: one-time script that creates or rotates the `codex_ro` role and writes `.env.codex-db`.
- `ops/codex-db/run-query.ps1`: main wrapper for read and write queries.
- `ops/codex-db/unlock-write.ps1`: opens a short local write window.
- `ops/codex-db/lock-write.ps1`: closes the write window immediately.
- `ops/codex-db/lib.ps1`: shared helper functions.
- `.env.codex-db`: local ignored read-only credential file used by the wrapper.

## One-time bootstrap

Use a real PostgreSQL admin login once to create the read-only role:

```powershell
cd C:\Users\igol\Documents\GitHub\polyedge-v2
powershell -ExecutionPolicy Bypass -File .\ops\codex-db\bootstrap-readonly-role.ps1 -AdminUser postgres
```

The script prompts for the admin password through `psql`, then:

- creates or rotates the `codex_ro` password
- grants `CONNECT` on the app database
- grants `USAGE` on schema `public`
- grants `SELECT` on current `public` tables and sequences
- sets default privileges for future `public` tables and sequences created by `polymarket`
- writes the local ignored credential file `.env.codex-db`

If your admin login is not `postgres`, pass `-AdminUser youradminrole`.

Do not use the normal app role from `.env` unless it truly has PostgreSQL `CREATEROLE` or `SUPERUSER`. In this setup, `polymarket` is the app role and is not sufficient for the bootstrap.

## Read queries

Default query mode is read-only:

```powershell
powershell -File .\ops\codex-db\run-query.ps1 -Sql "select current_database(), current_user;"
powershell -File .\ops\codex-db\run-query.ps1 -Sql "select * from public.bot_config limit 5;"
powershell -File .\ops\codex-db\run-query.ps1 -File .\tmp\query.sql
```

Read mode:

- uses `.env.codex-db`
- sets `application_name = codex_db_ro`
- sets `statement_timeout = 15s`
- sets `lock_timeout = 5s`
- sets `default_transaction_read_only = on`
- rejects psql meta-commands such as `\!`, `\copy`, and `\i`

## Rare writes

Write mode is locked by default.

Open a temporary write window:

```powershell
powershell -File .\ops\codex-db\unlock-write.ps1 -Minutes 5
```

Run a write query:

```powershell
powershell -File .\ops\codex-db\run-query.ps1 -Write -Sql "update public.bot_config set value = '300' where key = 'daily_loss_limit';"
```

Close the window early:

```powershell
powershell -File .\ops\codex-db\lock-write.ps1
```

Write mode:

- uses `.env`
- sets `application_name = codex_db_rw`
- is allowed only while `%LOCALAPPDATA%\PolyEdge\codex-db\write-unlock.json` is still valid
- allows any SQL during that short window because this workflow is intentionally a soft guard

## Audit log

Each wrapper execution appends a JSON line to:

```text
%LOCALAPPDATA%\PolyEdge\codex-db\query-audit.jsonl
```

Each entry includes:

- UTC timestamp
- mode (`read` or `write`)
- SQL SHA-256 hash
- first non-empty SQL line as preview
- success/failure
- result summary such as `(1 row)` or `UPDATE 1`

## Security note

This workflow reduces accidental writes. It does not fully prevent them, because the write-capable app credential remains in the same local workspace that Codex can read.
