from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CORE_PATH = Path(__file__).resolve().parents[2].parent / "klucon-cms"
if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))

import src.components  # noqa: E402

COMPONENTS_PATH = Path(__file__).resolve().parents[1] / "src" / "components"
src.components.__path__.append(str(COMPONENTS_PATH))

from src.components.com_warehouse.schema import upgrade_schema  # noqa: E402
from src.components.com_warehouse.service import (  # noqa: E402
    DOCUMENT_ISSUE,
    DOCUMENT_RECEIPT,
    build_document_payload,
    build_material_payload,
    build_project_payload,
    build_reservation_payload,
    build_transfer_payload,
    build_warehouse_payload,
    create_document,
    create_material,
    create_project,
    create_reservation,
    create_warehouse,
    issue_reservation,
    list_material_movements,
    list_reservations,
    list_stock_levels,
    reverse_document,
    transfer_stock,
)


async def stock_qty(db, material_id: int) -> str:
    return str((await list_stock_levels(db, material_id=material_id))[0].quantity_on_hand)


class MultiForm:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def get(self, key: str, default: object = None) -> object:
        value = self.data.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value

    def getlist(self, key: str) -> list[object]:
        value = self.data.get(key, [])
        return value if isinstance(value, list) else [value]


@pytest.mark.asyncio
async def test_multi_item_documents_and_reversals(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        cement = await create_material(
            db,
            build_material_payload(name="Cement 25 kg", sku="CEM-25", ean="8590000000011"),
        )
        brick = await create_material(db, build_material_payload(name="Cihla", sku="BRICK"))
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(name="Hlavni sklad", code="MAIN", is_default=True),
        )
        project = await create_project(db, build_project_payload(name="Stavba A", code="A001"))

        receipt = await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_RECEIPT,
                data=MultiForm(
                    {
                        "number": "PR-2",
                        "warehouse_id": str(warehouse.id),
                        "project_id": "",
                        "material_id": [str(cement.id), str(brick.id), ""],
                        "location_id": ["", "", ""],
                        "quantity": ["10", "20", ""],
                        "unit_price": ["100", "5", ""],
                        "batch_number": ["B1", "", ""],
                        "expires_on": ["", "", ""],
                        "note": ["", "", ""],
                    }
                ),
            ),
        )
        issue = await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_ISSUE,
                data=MultiForm(
                    {
                        "number": "VY-2",
                        "warehouse_id": str(warehouse.id),
                        "project_id": str(project.id),
                        "material_id": [str(cement.id), str(brick.id)],
                        "location_id": ["", ""],
                        "quantity": ["3", "4"],
                        "unit_price": ["100", "5"],
                        "batch_number": ["B1", ""],
                        "expires_on": ["", ""],
                        "note": ["", ""],
                    }
                ),
            ),
        )

        assert await stock_qty(db, cement.id) == "7.000"
        assert await stock_qty(db, brick.id) == "16.000"

        reverse_issue = await reverse_document(db, issue.id)
        assert reverse_issue.number == "STORNO-VY-2"
        assert await stock_qty(db, cement.id) == "10.000"
        assert await stock_qty(db, brick.id) == "20.000"

        reverse_receipt = await reverse_document(db, receipt.id)
        assert reverse_receipt.number == "STORNO-PR-2"
        assert await stock_qty(db, cement.id) == "0.000"
        assert await stock_qty(db, brick.id) == "0.000"
        assert len(await list_material_movements(db, cement.id)) == 4

    await engine.dispose()


@pytest.mark.asyncio
async def test_reservation_issue_and_transfer(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        material = await create_material(
            db,
            build_material_payload(name="Pisek", sku="PISKY"),
        )
        source = await create_warehouse(
            db,
            build_warehouse_payload(name="Hlavni sklad", code="MAIN", is_default=True),
        )
        target = await create_warehouse(
            db,
            build_warehouse_payload(name="Prirucni sklad", code="SITE", is_default=False),
        )
        project = await create_project(db, build_project_payload(name="Stavba A", code="A001"))

        await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_RECEIPT,
                number="PR-3",
                warehouse_id=source.id,
                project_id="",
                material_id=material.id,
                location_id="",
                quantity="20",
                unit_price="10",
                batch_number="",
                expires_on="",
                note="",
            ),
        )
        reservation = await create_reservation(
            db,
            build_reservation_payload(
                material_id=material.id,
                warehouse_id=source.id,
                location_id="",
                project_id=project.id,
                quantity="6",
            ),
        )
        reservations = await list_reservations(db)
        assert str(reservations[0].quantity_available_now) == "6.000"
        assert str(reservations[0].quantity_missing) == "0"
        source_levels = await list_stock_levels(db, material_id=material.id)
        assert str(source_levels[0].quantity_on_hand) == "20.000"
        assert str(source_levels[0].quantity_reserved) == "0.000"
        assert str(source_levels[0].quantity_available) == "20.000"

        issue = await issue_reservation(db, reservation.id)
        assert issue.number == "VYR-1"
        source_levels = await list_stock_levels(db, material_id=material.id)
        assert str(source_levels[0].quantity_on_hand) == "14.000"
        assert str(source_levels[0].quantity_reserved) == "0.000"

        transfer_out, transfer_in = await transfer_stock(
            db,
            build_transfer_payload(
                number="TR-1",
                source_warehouse_id=source.id,
                target_warehouse_id=target.id,
                material_id=material.id,
                quantity="4",
                unit_price="10",
            ),
        )
        assert transfer_out.number == "TR-1-OUT"
        assert transfer_in.number == "TR-1-IN"

        levels = await list_stock_levels(db, material_id=material.id)
        by_warehouse = {level.warehouse_id: level for level in levels}
        assert str(by_warehouse[source.id].quantity_on_hand) == "10.000"
        assert str(by_warehouse[target.id].quantity_on_hand) == "4.000"
        assert len(await list_material_movements(db, material.id)) == 4

    await engine.dispose()


@pytest.mark.asyncio
async def test_reservation_can_exceed_stock_and_issue_negative(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        material = await create_material(db, build_material_payload(name="OSB deska", sku="OSB"))
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(name="Hlavni sklad", code="MAIN", is_default=True),
        )
        project = await create_project(db, build_project_payload(name="Stavba B", code="B001"))

        await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_RECEIPT,
                number="PR-4",
                warehouse_id=warehouse.id,
                project_id="",
                material_id=material.id,
                location_id="",
                quantity="2",
                unit_price="300",
                batch_number="",
                expires_on="",
                note="",
            ),
        )
        reservation = await create_reservation(
            db,
            build_reservation_payload(
                material_id=material.id,
                warehouse_id=warehouse.id,
                location_id="",
                project_id=project.id,
                quantity="6",
            ),
        )

        reservations = await list_reservations(db)
        assert str(reservations[0].quantity_available_now) == "2.000"
        assert str(reservations[0].quantity_missing) == "4.000"

        issue = await issue_reservation(db, reservation.id)
        assert issue.number == "VYR-1"
        assert await stock_qty(db, material.id) == "-4.000"

    await engine.dispose()
