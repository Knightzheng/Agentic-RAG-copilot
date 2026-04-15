"""清理本地开发数据库。"""

from __future__ import annotations

from urllib.parse import urlparse

import psycopg
from psycopg import sql

from app.core.config import settings

APP_SCHEMAS = ["app_obs", "app_mcp", "app_memory", "app_agent", "app_kb", "app_core"]


def main() -> None:
    """执行数据库清理。"""

    parsed = urlparse(settings.database_url.replace("+psycopg", ""))
    if parsed.path.lstrip("/") != "rag_lab":
        raise RuntimeError(f"安全保护：当前数据库不是 rag_lab，而是 {parsed.path.lstrip('/')}")

    with psycopg.connect(settings.database_url.replace("+psycopg", "")) as connection:
        with connection.cursor() as cursor:
            for schema_name in APP_SCHEMAS:
                cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))

            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            for (table_name,) in cursor.fetchall():
                cursor.execute(sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE").format(sql.Identifier(table_name)))

            cursor.execute("SELECT viewname FROM pg_views WHERE schemaname = 'public'")
            for (view_name,) in cursor.fetchall():
                cursor.execute(sql.SQL("DROP VIEW IF EXISTS public.{} CASCADE").format(sql.Identifier(view_name)))

            cursor.execute(
                "SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public'"
            )
            for (sequence_name,) in cursor.fetchall():
                cursor.execute(
                    sql.SQL("DROP SEQUENCE IF EXISTS public.{} CASCADE").format(sql.Identifier(sequence_name))
                )

            cursor.execute("DROP TABLE IF EXISTS public.alembic_version CASCADE")
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

        connection.commit()

    print("数据库 rag_lab 已清理完成。")


if __name__ == "__main__":
    main()
