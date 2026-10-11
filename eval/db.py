"""eval/db.py — read-only snapshots of customer_orders for the mutation check (EVALS §3.6).

Not an agent path: the eval harness reads the table directly via psql to prove the action
set leaves customer_orders byte-for-byte unchanged (T-MUTATE). The agent can only reach the
database through the MCP tools, which have no write access to this table.
"""
import os
import subprocess

DB_NAME = os.environ.get("DB_NAME", "support")
_COLS = "order_id, customer_email, delivery_address, status, items, total_amount"


def snapshot_orders() -> str:
    """The whole customer_orders table as stable-ordered text; compare before vs. after a set."""
    out = subprocess.run(
        ["psql", "-d", DB_NAME, "-tAc",
         f"SELECT {_COLS} FROM customer_orders ORDER BY order_id"],
        capture_output=True, text=True, check=True,
        env={**os.environ,
             "PGHOST": os.environ.get("PGHOST", "127.0.0.1"),
             "PGPORT": os.environ.get("PGPORT", "5432")},
    )
    return out.stdout
