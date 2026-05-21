from __future__ import annotations

from .models import (
    Budget,
    BudgetItem,
    ConstructionProject,
    Material,
    StockDocument,
    StockDocumentItem,
    StockLevel,
    StockLocation,
    StockMovement,
    StockReservation,
    Warehouse,
)

_TABLES_DROP_ORDER = [
    StockMovement.__table__,
    StockReservation.__table__,
    StockLevel.__table__,
    StockDocumentItem.__table__,
    StockDocument.__table__,
    BudgetItem.__table__,
    Budget.__table__,
    ConstructionProject.__table__,
    StockLocation.__table__,
    Warehouse.__table__,
    Material.__table__,
]

_TABLES_CREATE_ORDER = list(reversed(_TABLES_DROP_ORDER))


async def upgrade_schema(engine: object) -> None:
    async with engine.begin() as conn:
        for table in _TABLES_CREATE_ORDER:
            await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))


async def uninstall_schema(engine: object) -> None:
    async with engine.begin() as conn:
        for table in _TABLES_DROP_ORDER:
            await conn.run_sync(lambda c, t=table: t.drop(c, checkfirst=True))
