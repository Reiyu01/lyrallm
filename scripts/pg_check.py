#!/usr/bin/env python3
"""
Check Postgres `token_usage` writes.

Usage:
  python Scripts/pg_check.py --last 20
  python Scripts/pg_check.py --request_id req_abcd1234

The script will try asyncpg first, then psycopg2. If neither is available it will
print the DSN and a psql command you can run manually.
"""
# def get_db_config():
#     try:
#         from lyrallm.config.config_manager import config_manager
#         cfg = config_manager.config.get('database', {})
#         return cfg
#     except Exception:
#         return {}
import argparse
import asyncio
import json
import sys
import pathlib

# Ensure project root is on sys.path so we can import project modules from anywhere
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Try to import the project's config_manager in a robust way
try:
    from lyrallm.config.config_manager import config_manager
except Exception:
    try:
        # fallback to relative package name if project layout differs
    from lyrallm.config.config_manager import config_manager
    except Exception:
        print("Failed to import config_manager from project. Ensure project layout is correct.")
        raise


def get_db_config():
    try:
        return config_manager.config.get('database', {})
    except Exception:
        return {}


async def query_asyncpg(dsn, sql, params=None):
    try:
        import asyncpg
    except Exception as e:
        raise
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch(sql, *(params or []))
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def query_psycopg2(dsn, sql, params=None):
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or [])
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def pretty_print_rows(rows):
    if not rows:
        print("No rows found.")
        return
    for r in rows:
        # pretty print important fields
        created = r.get('created_at') or r.get('timestamp')
        req = r.get('request_id')
        model = r.get('model_name')
        total = r.get('total_tokens')
        status = r.get('status')
        print(f"[{created}] request_id={req} model={model} total_tokens={total} status={status}")
        raw = r.get('raw') or r.get('raw')
        if raw:
            try:
                print(json.dumps(raw, ensure_ascii=False, indent=2))
            except Exception:
                print(raw)
        print("-"*60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--last', type=int, default=10, help='Show last N rows')
    parser.add_argument('--request_id', type=str, help='Filter by request_id')
    args = parser.parse_args()

    cfg = get_db_config()
    dsn = cfg.get('dsn') or cfg.get('url') or cfg.get('connection_string')

    if not dsn:
        print("Database DSN not found in config_manager. Please check your config file.")
        print("Database config from config_manager:", cfg)
        sys.exit(1)

    if args.request_id:
        sql = "SELECT * FROM token_usage WHERE request_id = $1 ORDER BY created_at DESC LIMIT 100"
        params = [args.request_id]
    else:
        sql = f"SELECT * FROM token_usage ORDER BY created_at DESC LIMIT {int(args.last)}"
        params = None

    # Try asyncpg
    try:
        rows = asyncio.run(query_asyncpg(dsn, sql, params))
        pretty_print_rows(rows)
        return
    except Exception:
        pass

    # Try psycopg2 (sync)
    try:
        rows = query_psycopg2(dsn, sql.replace('$1', '%s'), params)
        pretty_print_rows(rows)
        return
    except Exception:
        pass

    print("Could not query Postgres with asyncpg or psycopg2 available.")
    print("DSN:", dsn)
    print("You can run the following with psql if installed:")
    if args.request_id:
        print(f"psql \"{dsn}\" -c \"SELECT * FROM token_usage WHERE request_id = '{args.request_id}' ORDER BY created_at DESC;\"")
    else:
        print(f"psql \"{dsn}\" -c \"SELECT * FROM token_usage ORDER BY created_at DESC LIMIT {args.last};\"")


if __name__ == '__main__':
    main()
