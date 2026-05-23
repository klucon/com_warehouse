from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CORE_PATH = Path(__file__).resolve().parents[2].parent / "klucon-cms"
if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))

import src.components  # noqa: E402

COMPONENTS_PATH = Path(__file__).resolve().parents[1] / "src" / "components"
src.components.__path__.append(str(COMPONENTS_PATH))

from src.components.com_warehouse.pdf import document_pdf_bytes  # noqa: E402
from src.components.com_warehouse.schema import upgrade_schema  # noqa: E402
from src.components.com_warehouse.service import (  # noqa: E402
    DOCUMENT_ISSUE,
    DOCUMENT_RECEIPT,
    build_budget_item_payload,
    build_budget_payload,
    build_document_payload,
    build_material_payload,
    build_project_budget_section_payload,
    build_project_direction_payload,
    build_project_payload,
    build_reservation_payload,
    build_transfer_payload,
    build_warehouse_payload,
    create_budget,
    create_budget_item,
    create_document,
    create_material,
    create_project,
    create_project_budget_section,
    create_project_direction,
    create_reservation,
    create_warehouse,
    get_document,
    import_materials_from_sql_dump,
    issue_reservation,
    list_material_batches,
    list_material_movements,
    list_materials,
    list_project_budgets,
    list_project_directions,
    list_reservations,
    list_stock_levels,
    list_units,
    parse_material_sql_dump,
    project_material_balance,
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
            build_material_payload(name="Test cement 25 kg", sku="CEM-25", ean="8590000000011"),
        )
        brick = await create_material(db, build_material_payload(name="Test brick", sku="BRICK"))
        auto_material = await create_material(
            db,
            build_material_payload(name="Auto cislo", sku="AUTO"),
        )
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(name="Test warehouse", code="MAIN", is_default=True),
        )
        project = await create_project(
            db, build_project_payload(name="Test project A", code="A001")
        )
        auto_receipt = await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_RECEIPT,
                warehouse_id=warehouse.id,
                material_id=auto_material.id,
                quantity="1",
            ),
        )
        assert len(auto_receipt.number) == 14
        assert auto_receipt.number.isdigit()

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
            build_material_payload(name="Test sand", sku="PISKY"),
        )
        source = await create_warehouse(
            db,
            build_warehouse_payload(name="Test warehouse", code="MAIN", is_default=True),
        )
        target = await create_warehouse(
            db,
            build_warehouse_payload(name="Target test warehouse", code="SITE", is_default=False),
        )
        project = await create_project(
            db, build_project_payload(name="Test project A", code="A001")
        )

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
        material = await create_material(db, build_material_payload(name="Test board", sku="OSB"))
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(name="Test warehouse", code="MAIN", is_default=True),
        )
        project = await create_project(
            db, build_project_payload(name="Test project B", code="B001")
        )

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


@pytest.mark.asyncio
async def test_import_materials_from_sql_dump_normalizes_units_and_duplicates(
    tmp_path: Path,
) -> None:
    sql = """
    INSERT INTO `material` VALUES
    ('1.','1100000011','Jistič BD 250 NE 305','','KS'),
    ('2.','1100100437','Kabel 1 kV CYKY/NYY-J 4 x 16RE','12MC02156','M'),
    ('3.','1100100437','Kabel 1 kV CYKY/NYY-J 4 x 16RE','12MC11463','M'),
    ('4.','1100000999','Materiál se závorkou (sada)','','ST ');
    """
    rows = parse_material_sql_dump(sql)
    assert len(rows) == 4
    assert rows[3]["unit"] == "ST"

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await import_materials_from_sql_dump(db, sql)
        assert result.rows == 4
        assert result.created == 3
        assert result.skipped == 1
        assert result.units_created == 3
        assert result.batches_created == 2

        materials = await list_materials(db)
        assert {material.sku for material in materials} == {
            "1100000011",
            "1100100437",
            "1100000999",
        }
        assert {unit.code for unit in await list_units(db)} == {"KS", "M", "ST"}
        cable = next(material for material in materials if material.sku == "1100100437")
        batches = await list_material_batches(db, cable.id)
        assert {batch.batch_number for batch in batches} == {"12MC02156", "12MC11463"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_removes_legacy_unique_ean_before_sql_import(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE com_warehouse_materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku VARCHAR(80) NOT NULL,
                    ean VARCHAR(32) NOT NULL DEFAULT '',
                    name VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    category VARCHAR(100) NOT NULL DEFAULT '',
                    unit VARCHAR(20) NOT NULL DEFAULT 'ks',
                    vat_rate NUMERIC(5, 2) NOT NULL DEFAULT 21,
                    default_price NUMERIC(14, 4) NOT NULL DEFAULT 0,
                    min_stock NUMERIC(14, 3) NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_com_warehouse_material_ean "
                "ON com_warehouse_materials (ean)"
            )
        )

    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    sql = """
    INSERT INTO `material` VALUES
    ('1.','1100000011','Jistič BD 250 NE 305','','KS'),
    ('2.','1100000021','Pilíř betonový SS300/KKE1P','','KS');
    """
    async with session_factory() as db:
        result = await import_materials_from_sql_dump(db, sql)
        assert result.created == 2
        assert len(await list_materials(db)) == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_document_pdf_bytes_are_generated(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        material = await create_material(db, build_material_payload(name="Test cable", sku="KAB"))
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(name="Test warehouse", code="MAIN", is_default=True),
        )
        document = await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_RECEIPT,
                number="PR-PDF",
                warehouse_id=warehouse.id,
                project_id="",
                material_id=material.id,
                location_id="",
                quantity="12",
                unit_price="10",
                batch_number="12MC02156",
            ),
        )
        batches = await list_material_batches(db, material.id)
        assert [batch.batch_number for batch in batches] == ["12MC02156"]
        loaded = await get_document(db, document.id)
        assert loaded is not None
        pdf = document_pdf_bytes(loaded)
        assert pdf.startswith(b"%PDF-1.4")
        assert b"PR-PDF" in pdf
        assert b"%%EOF" in pdf

    await engine.dispose()


@pytest.mark.asyncio
async def test_project_operational_fields_budget_sections_and_balance(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'warehouse.sqlite'}")
    await upgrade_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        project = await create_project(
            db,
            build_project_payload(
                name="Test project",
                code="PROJECT-01",
                egd_montage_code="1030083972",
                external_project_code="25_101_105",
                calloff_number="4502163241",
                public_contract_number="VZ-1",
                foreman="Test foreman",
                egd_technician="Test technician",
            ),
        )
        assert project.calloff_number == "4502163241"
        direction = await create_project_direction(
            db,
            build_project_direction_payload(
                project_id=project.id,
                name="Test direction",
                code="DIRECTION-1",
            ),
        )
        assert direction.code == "DIRECTION-1"
        for code in ("MATERIAL", "DIRECT", "SERVICE"):
            await create_project_budget_section(
                db,
                build_project_budget_section_payload(direction_id=direction.id, source_type=code),
            )

        directions = await list_project_directions(db, project.id)
        assert len(directions) == 1
        assert {section.source_type for section in directions[0].sections} == {
            "MATERIAL",
            "DIRECT",
            "SERVICE",
        }
        material = await create_material(
            db, build_material_payload(name="Test material", sku="TEST-MAT")
        )
        budget = await create_budget(
            db,
            build_budget_payload(project_id=project.id, name="Test budget"),
        )
        section = directions[0].sections[0]
        item = await create_budget_item(
            db,
            build_budget_item_payload(
                budget_id=budget.id,
                material_id=material.id,
                section_id=section.id,
                quantity="90",
            ),
        )
        assert item.section_id == section.id
        budgets = await list_project_budgets(db, project.id)
        assert budgets[0].items[0].section.source_type in {"MATERIAL", "DIRECT", "SERVICE"}
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(name="Test warehouse", code="TEST-WAREHOUSE"),
        )
        await create_document(
            db,
            build_document_payload(
                document_type=DOCUMENT_ISSUE,
                number="ISSUE-TEST-1",
                warehouse_id=warehouse.id,
                project_id=project.id,
                material_id=material.id,
                quantity="100",
            ),
        )
        balance = await project_material_balance(db, project.id)
        assert balance[0].budget_quantity == 90
        assert balance[0].issued_quantity == 100
        assert balance[0].remaining_quantity == 0
        assert balance[0].over_budget_quantity == 10

    await engine.dispose()
