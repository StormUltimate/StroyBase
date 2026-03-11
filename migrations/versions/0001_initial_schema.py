"""Initial database schema for StroyBase.

This migration reflects the current SQLAlchemy models in app/models.py.
Creates default admin user (login=admin, password=admin) for first run.
"""
from __future__ import annotations

import bcrypt
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Порядок создания: сначала базовые таблицы, затем зависимые (по FK).
    # Core hierarchy: Project, Building, Floor
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("contract_number", sa.String(length=100), nullable=True),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("type_construction", sa.String(length=100), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("building_class", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("work_type", sa.String(length=100), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("area_m2", sa.Float(), nullable=True),
        sa.Column("total_area_m2", sa.Float(), nullable=True),
        sa.Column("floors_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "floors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("floor_type", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("area_m2", sa.Float(), nullable=True),
        sa.Column("total_area_m2", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "building_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role_name", sa.String(length=100), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("contact_person", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
    )

    # Doc types
    op.create_table(
        "doc_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=True, server_default="100"),
    )

    # Plans and marks (documents ссылается на marks)
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
    )

    op.create_table(
        "marks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id"), nullable=True),
        sa.Column("x", sa.Float(), nullable=True),
        sa.Column("y", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    # Documents (после plans, marks)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id"), nullable=True),
        sa.Column("mark_id", sa.Integer(), sa.ForeignKey("marks.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("stored_path", sa.String(length=255), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("file_modified_at", sa.DateTime(), nullable=True),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("is_document_image", sa.Boolean(), nullable=True),
        sa.Column("contract_number", sa.String(length=100), nullable=True),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("counterparty", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("contract_status", sa.String(length=100), nullable=True),
    )

    # Association: document_work_types (после documents, doc_types)
    op.create_table(
        "document_work_types",
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("doc_type_id", sa.Integer(), sa.ForeignKey("doc_types.id", ondelete="CASCADE"), primary_key=True),
    )

    # Materials and related
    op.create_table(
        "material_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("material_categories.id"), nullable=True),
    )

    # User and tasks (floor_materials ссылается на tasks)
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=True, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("refresh_token", sa.String(length=512), nullable=True),
        sa.Column("refresh_token_expiry", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_user_login", "user", ["login"], unique=True)
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id"), nullable=True),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True, server_default="К выполнению"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "floor_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("gost", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=100), nullable=True),
        sa.Column("price_per_unit", sa.Numeric(10, 2), nullable=True),
        sa.Column("planned_quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("actual_quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True, server_default="Запланировано"),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("arrival_date", sa.Date(), nullable=True),
        sa.Column("install_date", sa.Date(), nullable=True),
        sa.Column("demolition_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("certificate_document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("material_categories.id"), nullable=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("floor_materials.id"), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=True, server_default=sa.func.current_date()),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="Запланировано"),
        sa.Column("note", sa.Text(), nullable=True),
    )

    # Association: material_documents, order_documents (после floor_materials, documents, orders)
    op.create_table(
        "material_documents",
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("floor_materials.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("doc_type", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_main", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "order_documents",
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "floor_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("passport_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )

    op.create_table(
        "floor_quantities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )

    # Material movements
    op.create_table(
        "material_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("volume_m3", sa.Numeric(12, 4), nullable=True),
        sa.Column("length_m", sa.Numeric(12, 4), nullable=True),
        sa.Column("weight_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("movement_type", sa.String(length=50), nullable=True),
        sa.Column("movement_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "movement_documents",
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("material_movements.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("doc_type", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )

    # Works and progress
    op.create_table(
        "works",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("planned_completion_date", sa.Date(), nullable=True),
        sa.Column("percent_complete", sa.Float(), nullable=True),
        sa.Column("initial_executed", sa.Float(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("system_subsection", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "work_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_id", sa.Integer(), sa.ForeignKey("works.id", ondelete="CASCADE"), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("daily_execution", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    # Daily workforce and performers
    op.create_table(
        "daily_workforce",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("contractor_name", sa.String(length=255), nullable=True),
        sa.Column("workers_count", sa.Integer(), nullable=True),
        sa.Column("workers_count_night", sa.Integer(), nullable=True),
        sa.Column("shift_hours", sa.Float(), nullable=True),
        sa.Column("shift_hours_night", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "work_performers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    # Schedule works and plan tasks
    op.create_table(
        "schedule_works",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_end", sa.Date(), nullable=True),
        sa.Column("fact_start", sa.Date(), nullable=True),
        sa.Column("fact_end", sa.Date(), nullable=True),
        sa.Column("percent_complete", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_table(
        "plan_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=True),
        sa.Column("dependency_id", sa.Integer(), sa.ForeignKey("plan_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    # Seed default admin (login=admin, password=admin) for first run
    conn = op.get_bind()
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


def downgrade() -> None:
    # Remove seed admin before dropping user table
    conn = op.get_bind()
    conn.execute(text('DELETE FROM "user" WHERE login = :login'), {"login": "admin"})

    # Drop in reverse order of creation to satisfy FKs
    op.drop_table("plan_tasks")
    op.drop_table("schedule_works")
    op.drop_table("work_performers")
    op.drop_table("daily_workforce")
    op.drop_table("work_progress")
    op.drop_table("works")
    op.drop_table("movement_documents")
    op.drop_table("material_movements")
    op.drop_table("order_documents")
    op.drop_table("material_documents")
    op.drop_table("orders")
    op.drop_table("floor_quantities")
    op.drop_table("floor_equipment")
    op.drop_table("floor_materials")
    op.drop_table("tasks")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_index("ix_user_login", table_name="user")
    op.drop_table("user")
    op.drop_table("material_categories")
    op.drop_table("marks")
    op.drop_table("plans")
    op.drop_table("document_work_types")
    op.drop_table("documents")
    op.drop_table("doc_types")
    op.drop_table("building_participants")
    op.drop_table("floors")
    op.drop_table("buildings")
    op.drop_table("projects")

