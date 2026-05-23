from __future__ import annotations

from sqlalchemy import inspect, text

from .models import (
    Budget,
    BudgetItem,
    ConstructionProject,
    Material,
    MaterialBatch,
    MaterialRequest,
    MaterialRequestItem,
    ProjectBudgetSection,
    ProjectDirection,
    StockDocument,
    StockDocumentItem,
    StockLevel,
    StockLocation,
    StockMovement,
    StockReservation,
    Unit,
    Warehouse,
)

_TABLES_DROP_ORDER = [
    StockMovement.__table__,
    StockReservation.__table__,
    StockLevel.__table__,
    StockDocumentItem.__table__,
    StockDocument.__table__,
    MaterialRequestItem.__table__,
    MaterialRequest.__table__,
    ProjectBudgetSection.__table__,
    ProjectDirection.__table__,
    BudgetItem.__table__,
    Budget.__table__,
    ConstructionProject.__table__,
    StockLocation.__table__,
    Warehouse.__table__,
    MaterialBatch.__table__,
    Material.__table__,
    Unit.__table__,
]

_TABLES_CREATE_ORDER = list(reversed(_TABLES_DROP_ORDER))


async def upgrade_schema(engine: object) -> None:
    async with engine.begin() as conn:
        for table in _TABLES_CREATE_ORDER:
            await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))
        await conn.run_sync(_migrate_existing_schema)


async def uninstall_schema(engine: object) -> None:
    async with engine.begin() as conn:
        for table in _TABLES_DROP_ORDER:
            await conn.run_sync(lambda c, t=table: t.drop(c, checkfirst=True))


def _migrate_existing_schema(conn: object) -> None:
    inspector = inspect(conn)
    _drop_material_ean_unique_constraints(conn, inspector)
    material_columns = {
        column["name"] for column in inspector.get_columns("com_warehouse_materials")
    }
    if "unit_id" not in material_columns:
        conn.execute(text("ALTER TABLE com_warehouse_materials ADD COLUMN unit_id INTEGER"))
    budget_item_columns = {
        column["name"] for column in inspector.get_columns("com_warehouse_budget_items")
    }
    if "section_id" not in budget_item_columns:
        conn.execute(text("ALTER TABLE com_warehouse_budget_items ADD COLUMN section_id INTEGER"))
    project_columns = {
        column["name"] for column in inspector.get_columns("com_warehouse_projects")
    }
    for column_name, column_type in {
        "egd_montage_code": "VARCHAR(80)",
        "external_project_code": "VARCHAR(80)",
        "calloff_number": "VARCHAR(80)",
        "public_contract_number": "VARCHAR(80)",
        "foreman": "VARCHAR(120)",
        "egd_technician": "VARCHAR(120)",
    }.items():
        if column_name not in project_columns:
            conn.execute(
                text(
                    f"ALTER TABLE com_warehouse_projects "
                    f"ADD COLUMN {column_name} {column_type} NOT NULL DEFAULT ''"
                )
            )


def _drop_material_ean_unique_constraints(conn: object, inspector: object) -> None:
    dropped: set[str] = set()
    constraints = inspector.get_unique_constraints("com_warehouse_materials")
    for constraint in constraints:
        if constraint.get("column_names") != ["ean"]:
            continue
        name = constraint.get("name")
        if not name or str(name) in dropped:
            continue
        _drop_unique_constraint(conn, str(name))
        dropped.add(str(name))

    indexes = inspector.get_indexes("com_warehouse_materials")
    for index in indexes:
        if not index.get("unique") or index.get("column_names") != ["ean"]:
            continue
        name = index.get("name")
        if not name or str(name) in dropped:
            continue
        _drop_unique_constraint(conn, str(name))
        dropped.add(str(name))


def _drop_unique_constraint(conn: object, name: str) -> None:
    dialect = conn.dialect.name
    if dialect in {"mysql", "mariadb"}:
        conn.execute(text(f"ALTER TABLE com_warehouse_materials DROP INDEX `{name}`"))
    elif dialect == "postgresql":
        conn.execute(text(f'ALTER TABLE com_warehouse_materials DROP CONSTRAINT "{name}"'))
    elif dialect == "sqlite" and not name.startswith("sqlite_autoindex_"):
        conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
