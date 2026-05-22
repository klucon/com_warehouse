from __future__ import annotations

from sqlalchemy import inspect, text

from .models import (
    Budget,
    BudgetItem,
    ConstructionProject,
    Material,
    MaterialBatch,
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
