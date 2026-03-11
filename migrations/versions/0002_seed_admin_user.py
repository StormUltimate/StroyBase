"""Seed default admin user for first run.

Creates user login=admin, password=admin if no users exist.
Uses raw SQL to avoid ORM/session issues during migration.
"""
from __future__ import annotations

import bcrypt
from alembic import op
from sqlalchemy import text


revision = "0002_seed_admin_user"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    try:
        r = conn.execute(text('SELECT 1 FROM "user" WHERE login = :login'), {"login": "admin"})
        if r.fetchone() is None:
            pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
            conn.execute(
                text(
                    'INSERT INTO "user" (login, full_name, role, password_hash, is_active) '
                    "VALUES (:login, :name, :role, :pw, true)"
                ),
                {"login": "admin", "name": "Администратор", "role": "admin", "pw": pw_hash},
            )
    except Exception:
        # Таблица "user" может отсутствовать, если 0001 не выполнилась
        pass


def downgrade() -> None:
    conn = op.get_bind()
    try:
        conn.execute(text('DELETE FROM "user" WHERE login = :login'), {"login": "admin"})
    except Exception:
        pass
