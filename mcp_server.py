import json
import os
import re
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from psycopg2 import sql

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://mcp:mcptest@localhost:5432/ecommerce"
)

MAX_ROWS = 100
STATEMENT_TIMEOUT_MS = 30000

ALLOWED_START_KEYWORDS = ("select", "with", "explain")
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|call|copy|do)\b",
    re.IGNORECASE,
)
LIMIT_PATTERN = re.compile(r"\blimit\s+(\d+)\s*$", re.IGNORECASE | re.DOTALL)
COMMENT_PATTERN = re.compile(r"--.*?(?=\n|$)|/\*.*?\*/", re.DOTALL)

mcp = FastMCP("postgres-qa")


@contextmanager
def db_connection():
    conn = psycopg2.connect(DB_URL)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cursor:
            cursor.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        yield conn
    finally:
        conn.close()


def sanitize_query(query: str) -> str:
    cleaned = COMMENT_PATTERN.sub(" ", query).strip().rstrip(";").strip()

    if ";" in cleaned:
        raise ValueError("Only a single SQL statement is allowed.")

    first_word = cleaned.split(None, 1)[0].lower()
    if first_word not in ALLOWED_START_KEYWORDS:
        raise ValueError(
            f"Only read-only SELECT / WITH / EXPLAIN queries are allowed "
            f"(query starts with '{first_word.upper()}')."
        )

    match = FORBIDDEN_KEYWORDS.search(cleaned)
    if match:
        raise ValueError(f"Forbidden keyword in read-only query: '{match.group(1).upper()}'.")

    limit_match = LIMIT_PATTERN.search(cleaned)
    if limit_match:
        if int(limit_match.group(1)) > MAX_ROWS:
            cleaned = LIMIT_PATTERN.sub(f"LIMIT {MAX_ROWS}", cleaned)
    else:
        cleaned = f"{cleaned} LIMIT {MAX_ROWS}"

    return cleaned


@mcp.tool()
def list_tables() -> str:
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute(query)
        tables = [row[0] for row in cursor.fetchall()]

    return json.dumps({"tables": tables, "count": len(tables)}, indent=2)


@mcp.tool()
def get_schema(table_name: str) -> str:
    query = sql.SQL(
        """
        SELECT c.column_name, c.data_type, c.is_nullable,
               EXISTS (
                   SELECT 1
                   FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu
                     ON tc.constraint_name = kcu.constraint_name
                   WHERE tc.constraint_type = 'PRIMARY KEY'
                     AND kcu.table_schema  = c.table_schema
                     AND kcu.table_name    = c.table_name
                     AND kcu.column_name   = c.column_name
               ) AS is_pk
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.table_name = {}
        ORDER BY c.ordinal_position
        """
    ).format(sql.Literal(table_name))

    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute(query)
        records = cursor.fetchall()

    if not records:
        return json.dumps({"error": f"Table '{table_name}' not found in schema 'public'."})

    columns = [
        {
            "name": row[0],
            "type": row[1],
            "nullable": row[2] == "YES",
            "primary_key": row[3],
        }
        for row in records
    ]

    return json.dumps({"table": table_name, "columns": columns}, indent=2)


@mcp.tool()
def run_query(query: str) -> str:
    safe_query = sanitize_query(query)

    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute(safe_query)
        columns = [desc.name for desc in cursor.description]
        rows = cursor.fetchmany(MAX_ROWS + 1)

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    payload = {
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "executed_query": safe_query,
    }

    return json.dumps(payload, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()