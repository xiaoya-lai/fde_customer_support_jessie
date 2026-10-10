#!/usr/bin/env bash
# run.sh — orchestration. Stage 1 implements: setup, reset, status.
# Later stages add: toolbox, judge, masker, phoenix, cli, web, stop.
set -euo pipefail

DB_NAME="${DB_NAME:-support}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
# Least-privilege role the MCP Toolbox will connect as (used from Stage 2).
TOOLBOX_USER="${TOOLBOX_USER:-toolbox}"
TOOLBOX_PASS="${TOOLBOX_PASS:-toolbox}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PGHOST="$DB_HOST" PGPORT="$DB_PORT"

cmd="${1:-help}"
case "$cmd" in
  setup)
    # Create the database and a least-privilege Toolbox role (M-6 defense-in-depth:
    # the role has no UPDATE/DELETE on customer_orders).
    createdb "$DB_NAME" 2>/dev/null && echo "created db $DB_NAME" || echo "db $DB_NAME already exists"
    psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${TOOLBOX_USER}') THEN
    CREATE ROLE ${TOOLBOX_USER} LOGIN PASSWORD '${TOOLBOX_PASS}';
  END IF;
END \$\$;
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${TOOLBOX_USER};
SQL
    echo "setup done. now run: ./run.sh reset"
    ;;

  reset)
    # Option A: drop + recreate + seed. SERIAL ids restart at 1 (EVALS §2).
    psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$ROOT/db/seed.sql"
    # Re-grant least-privilege reads to the Toolbox role on the fresh tables.
    psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT SELECT ON users, customer_orders TO ${TOOLBOX_USER};
GRANT SELECT, INSERT ON actions_log TO ${TOOLBOX_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${TOOLBOX_USER};
SQL
    echo "reset done: tables dropped, recreated, seeded (EVALS §2)."
    ;;

  toolbox)
    # Start the MCP Toolbox server (Stage 2). Loads tools.yaml with env-substituted
    # credentials. Override the launcher with TOOLBOX_CMD if npx can't find it.
    set -a; . "$ROOT/.env"; set +a
    TOOLBOX_CMD="${TOOLBOX_CMD:-npx -y @toolbox-sdk/server}"
    TOOLBOX_PORT="${TOOLBOX_PORT:-5050}"   # 5000 is taken by macOS AirPlay Receiver
    exec $TOOLBOX_CMD --config "$ROOT/mcp_toolbox/tools.yaml" --enable-api \
      --address 127.0.0.1 --port "$TOOLBOX_PORT"
    ;;

  status)
    echo "db $DB_NAME @ $DB_HOST:$DB_PORT"
    pg_isready -d "$DB_NAME" || true
    psql -d "$DB_NAME" -tAc "select 'users='||count(*) from users" 2>/dev/null || echo "no tables yet — run ./run.sh reset"
    ;;

  help|*)
    echo "usage: ./run.sh {setup|reset|toolbox|status}"
    ;;
esac
