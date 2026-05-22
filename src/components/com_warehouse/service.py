from __future__ import annotations

import re
from ast import literal_eval
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_ARCHIVED = "archived"
VALID_STATUSES = {STATUS_ACTIVE, STATUS_INACTIVE, STATUS_ARCHIVED}

DOCUMENT_RECEIPT = "receipt"
DOCUMENT_ISSUE = "issue"
DOCUMENT_ADJUSTMENT = "adjustment"
VALID_DOCUMENT_TYPES = {DOCUMENT_RECEIPT, DOCUMENT_ISSUE, DOCUMENT_ADJUSTMENT}
DOCUMENT_STATUS_POSTED = "posted"
DOCUMENT_STATUS_REVERSED = "reversed"

MOVEMENT_RECEIPT = "receipt"
MOVEMENT_ISSUE = "issue"
MOVEMENT_RESERVE = "reserve"
MOVEMENT_RELEASE = "release"

RESERVATION_ACTIVE = "active"
RESERVATION_PARTIAL = "partial"
RESERVATION_RELEASED = "released"
RESERVATION_CANCELLED = "cancelled"
VALID_RESERVATION_STATUSES = {
    RESERVATION_ACTIVE,
    RESERVATION_PARTIAL,
    RESERVATION_RELEASED,
    RESERVATION_CANCELLED,
}

_CODE_RE = re.compile(r"[^A-Z0-9._-]+")


class WarehouseError(ValueError):
    def __init__(self, key: str, **kwargs: object) -> None:
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


@dataclass(frozen=True)
class MaterialPayload:
    sku: str
    ean: str
    name: str
    description: str
    category: str
    unit: str
    unit_id: int | None
    vat_rate: Decimal
    default_price: Decimal
    min_stock: Decimal
    status: str
    notes: str


@dataclass(frozen=True)
class WarehousePayload:
    code: str
    name: str
    address: str
    status: str
    is_default: bool


@dataclass(frozen=True)
class LocationPayload:
    warehouse_id: int
    code: str
    name: str
    status: str


@dataclass(frozen=True)
class ProjectPayload:
    code: str
    name: str
    customer: str
    address: str
    egd_montage_code: str
    external_project_code: str
    calloff_number: str
    public_contract_number: str
    foreman: str
    egd_technician: str
    status: str
    budget_total: Decimal
    notes: str


@dataclass(frozen=True)
class ProjectDirectionPayload:
    project_id: int
    code: str
    name: str
    status: str
    notes: str


@dataclass(frozen=True)
class ProjectBudgetSectionPayload:
    direction_id: int
    source_type: str
    name: str
    status: str
    notes: str


@dataclass(frozen=True)
class BudgetPayload:
    project_id: int
    name: str
    status: str


@dataclass(frozen=True)
class BudgetItemPayload:
    budget_id: int
    material_id: int
    section_id: int | None
    quantity: Decimal
    unit_price: Decimal
    notes: str


@dataclass(frozen=True)
class MaterialBatchPayload:
    material_id: int
    batch_number: str
    status: str
    notes: str


@dataclass(frozen=True)
class DocumentItemPayload:
    material_id: int
    location_id: int | None
    quantity: Decimal
    unit_price: Decimal
    batch_number: str
    expires_on: date | None
    note: str


@dataclass(frozen=True)
class DocumentPayload:
    number: str
    document_type: str
    warehouse_id: int
    project_id: int | None
    partner: str
    reference: str
    notes: str
    items: list[DocumentItemPayload]


@dataclass(frozen=True)
class ReservationPayload:
    material_id: int
    warehouse_id: int
    location_id: int | None
    project_id: int
    quantity: Decimal
    required_on: date | None
    note: str


@dataclass(frozen=True)
class TransferPayload:
    number: str
    source_warehouse_id: int
    source_location_id: int | None
    target_warehouse_id: int
    target_location_id: int | None
    material_id: int
    quantity: Decimal
    unit_price: Decimal
    batch_number: str
    note: str


@dataclass(frozen=True)
class DashboardStats:
    materials: int
    warehouses: int
    projects: int
    active_reservations: int
    low_stock: int


@dataclass(frozen=True)
class MaterialImportResult:
    rows: int
    created: int
    updated: int
    skipped: int
    units_created: int
    batches_created: int


@dataclass(frozen=True)
class ProjectMaterialBalance:
    material: Material
    budget_quantity: Decimal
    issued_quantity: Decimal
    remaining_quantity: Decimal
    over_budget_quantity: Decimal


def normalize_code(value: str, fallback: str = "") -> str:
    cleaned = _CODE_RE.sub("-", (value or fallback).strip().upper()).strip("-")
    return cleaned or fallback.strip().upper()


def normalize_status(status: str | None) -> str:
    candidate = (status or STATUS_ACTIVE).strip().lower()
    return candidate if candidate in VALID_STATUSES else STATUS_ACTIVE


def normalize_unit_code(value: object, fallback: str = "KS") -> str:
    code = normalize_code(str(value or ""), fallback=fallback)
    return code[:20] or fallback


def _decimal(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _positive_decimal(value: object, key: str) -> Decimal:
    number = _decimal(value)
    if number <= 0:
        raise WarehouseError(key)
    return number


def _optional_int(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        number = int(raw)
    except ValueError:
        return None
    return number if number > 0 else None


def _required_int(value: object, key: str) -> int:
    number = _optional_int(value)
    if number is None:
        raise WarehouseError(key)
    return number


def _optional_date(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _form_values(data: object, key: str) -> list[object]:
    getlist = getattr(data, "getlist", None)
    if callable(getlist):
        return list(getlist(key))
    if isinstance(data, dict):
        value = data.get(key)
    else:
        value = getattr(data, "get", lambda _key, _default=None: _default)(key)
    if isinstance(value, list | tuple):
        return list(value)
    return [value]


def _form_value(data: object, key: str, default: object = "") -> object:
    value = getattr(data, "get", lambda _key, _default=None: _default)(key, default)
    if isinstance(value, list | tuple):
        return value[0] if value else default
    return value


def build_material_payload(**data: object) -> MaterialPayload:
    name = str(data.get("name") or "").strip()
    if not name:
        raise WarehouseError("com_warehouse.error.material_name_required")
    sku = normalize_code(str(data.get("sku") or ""), fallback=name)
    if not sku:
        raise WarehouseError("com_warehouse.error.sku_required")
    unit = normalize_unit_code(data.get("unit") or data.get("unit_code") or "KS")
    return MaterialPayload(
        sku=sku,
        ean=str(data.get("ean") or "").strip(),
        name=name,
        description=str(data.get("description") or "").strip(),
        category=str(data.get("category") or "").strip(),
        unit=unit,
        unit_id=_optional_int(data.get("unit_id")),
        vat_rate=_decimal(data.get("vat_rate"), "21"),
        default_price=_decimal(data.get("default_price")),
        min_stock=_decimal(data.get("min_stock")),
        status=normalize_status(str(data.get("status") or "")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_warehouse_payload(**data: object) -> WarehousePayload:
    name = str(data.get("name") or "").strip()
    if not name:
        raise WarehouseError("com_warehouse.error.warehouse_name_required")
    code = normalize_code(str(data.get("code") or ""), fallback=name)
    return WarehousePayload(
        code=code,
        name=name,
        address=str(data.get("address") or "").strip(),
        status=normalize_status(str(data.get("status") or "")),
        is_default=bool(data.get("is_default")),
    )


def build_location_payload(**data: object) -> LocationPayload:
    name = str(data.get("name") or "").strip()
    code = normalize_code(str(data.get("code") or ""), fallback=name)
    if not code:
        raise WarehouseError("com_warehouse.error.location_code_required")
    return LocationPayload(
        warehouse_id=_required_int(
            data.get("warehouse_id"), "com_warehouse.error.warehouse_required"
        ),
        code=code,
        name=name,
        status=normalize_status(str(data.get("status") or "")),
    )


def build_project_payload(**data: object) -> ProjectPayload:
    name = str(data.get("name") or "").strip()
    if not name:
        raise WarehouseError("com_warehouse.error.project_name_required")
    return ProjectPayload(
        code=normalize_code(str(data.get("code") or ""), fallback=name),
        name=name,
        customer=str(data.get("customer") or "").strip(),
        address=str(data.get("address") or "").strip(),
        egd_montage_code=str(data.get("egd_montage_code") or "").strip(),
        external_project_code=str(data.get("external_project_code") or "").strip(),
        calloff_number=str(data.get("calloff_number") or "").strip(),
        public_contract_number=str(data.get("public_contract_number") or "").strip(),
        foreman=str(data.get("foreman") or "").strip(),
        egd_technician=str(data.get("egd_technician") or "").strip(),
        status=normalize_status(str(data.get("status") or "")),
        budget_total=_decimal(data.get("budget_total")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_project_direction_payload(**data: object) -> ProjectDirectionPayload:
    name = str(data.get("name") or "").strip()
    if not name:
        raise WarehouseError("com_warehouse.error.direction_name_required")
    return ProjectDirectionPayload(
        project_id=_required_int(data.get("project_id"), "com_warehouse.error.project_required"),
        code=normalize_code(str(data.get("code") or ""), fallback=name),
        name=name,
        status=normalize_status(str(data.get("status") or "")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_project_budget_section_payload(**data: object) -> ProjectBudgetSectionPayload:
    source_type = normalize_code(str(data.get("source_type") or ""), fallback="")
    if not source_type:
        raise WarehouseError("com_warehouse.error.budget_section_code_required")
    name = str(data.get("name") or "").strip() or source_type
    return ProjectBudgetSectionPayload(
        direction_id=_required_int(
            data.get("direction_id"), "com_warehouse.error.direction_required"
        ),
        source_type=source_type,
        name=name,
        status=normalize_status(str(data.get("status") or "")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_budget_payload(**data: object) -> BudgetPayload:
    name = str(data.get("name") or "").strip()
    if not name:
        raise WarehouseError("com_warehouse.error.budget_name_required")
    return BudgetPayload(
        project_id=_required_int(data.get("project_id"), "com_warehouse.error.project_required"),
        name=name,
        status=str(data.get("status") or "draft").strip().lower() or "draft",
    )


def build_budget_item_payload(**data: object) -> BudgetItemPayload:
    return BudgetItemPayload(
        budget_id=_required_int(data.get("budget_id"), "com_warehouse.error.budget_required"),
        material_id=_required_int(data.get("material_id"), "com_warehouse.error.material_required"),
        section_id=_optional_int(data.get("section_id")),
        quantity=_positive_decimal(data.get("quantity"), "com_warehouse.error.quantity_positive"),
        unit_price=_decimal(data.get("unit_price")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_material_batch_payload(**data: object) -> MaterialBatchPayload:
    batch_number = str(data.get("batch_number") or "").strip()
    if not batch_number:
        raise WarehouseError("com_warehouse.error.batch_number_required")
    return MaterialBatchPayload(
        material_id=_required_int(data.get("material_id"), "com_warehouse.error.material_required"),
        batch_number=batch_number,
        status=normalize_status(str(data.get("status") or "")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_document_payload(
    *,
    document_type: str,
    data: object | None = None,
    number: object = "",
    warehouse_id: object = "",
    project_id: object = "",
    partner: object = "",
    reference: object = "",
    notes: object = "",
    material_id: object = "",
    location_id: object = "",
    quantity: object = "",
    unit_price: object = "",
    batch_number: object = "",
    expires_on: object = "",
    note: object = "",
) -> DocumentPayload:
    if data is not None:
        number = _form_value(data, "number")
        warehouse_id = _form_value(data, "warehouse_id")
        project_id = _form_value(data, "project_id")
        partner = _form_value(data, "partner")
        reference = _form_value(data, "reference")
        notes = _form_value(data, "notes")
        material_values = _form_values(data, "material_id")
        location_values = _form_values(data, "location_id")
        quantity_values = _form_values(data, "quantity")
        unit_price_values = _form_values(data, "unit_price")
        batch_values = _form_values(data, "batch_number")
        expires_values = _form_values(data, "expires_on")
        note_values = _form_values(data, "note")
    else:
        material_values = _form_values({"material_id": material_id}, "material_id")
        location_values = _form_values({"location_id": location_id}, "location_id")
        quantity_values = _form_values({"quantity": quantity}, "quantity")
        unit_price_values = _form_values({"unit_price": unit_price}, "unit_price")
        batch_values = _form_values({"batch_number": batch_number}, "batch_number")
        expires_values = _form_values({"expires_on": expires_on}, "expires_on")
        note_values = _form_values({"note": note}, "note")

    clean_type = str(document_type or "").strip().lower()
    if clean_type not in VALID_DOCUMENT_TYPES:
        raise WarehouseError("com_warehouse.error.document_type_invalid")
    raw_number = str(number or "").strip()
    clean_number = normalize_code(raw_number, fallback=raw_number) if raw_number else ""
    items: list[DocumentItemPayload] = []
    for index, raw_material_id in enumerate(material_values):
        if not str(raw_material_id or "").strip():
            continue
        raw_quantity = quantity_values[index] if index < len(quantity_values) else ""
        items.append(
            DocumentItemPayload(
                material_id=_required_int(raw_material_id, "com_warehouse.error.material_required"),
                location_id=_optional_int(
                    location_values[index] if index < len(location_values) else ""
                ),
                quantity=_positive_decimal(raw_quantity, "com_warehouse.error.quantity_positive"),
                unit_price=_decimal(
                    unit_price_values[index] if index < len(unit_price_values) else ""
                ),
                batch_number=str(batch_values[index] if index < len(batch_values) else "").strip(),
                expires_on=_optional_date(
                    expires_values[index] if index < len(expires_values) else ""
                ),
                note=str(note_values[index] if index < len(note_values) else "").strip(),
            )
        )
    if not items:
        raise WarehouseError("com_warehouse.error.document_item_required")
    return DocumentPayload(
        number=clean_number,
        document_type=clean_type,
        warehouse_id=_required_int(warehouse_id, "com_warehouse.error.warehouse_required"),
        project_id=_optional_int(project_id),
        partner=str(partner or "").strip(),
        reference=str(reference or "").strip(),
        notes=str(notes or "").strip(),
        items=items,
    )


def build_reservation_payload(**data: object) -> ReservationPayload:
    return ReservationPayload(
        material_id=_required_int(data.get("material_id"), "com_warehouse.error.material_required"),
        warehouse_id=_required_int(
            data.get("warehouse_id"), "com_warehouse.error.warehouse_required"
        ),
        location_id=_optional_int(data.get("location_id")),
        project_id=_required_int(data.get("project_id"), "com_warehouse.error.project_required"),
        quantity=_positive_decimal(data.get("quantity"), "com_warehouse.error.quantity_positive"),
        required_on=_optional_date(data.get("required_on")),
        note=str(data.get("note") or "").strip(),
    )


def build_transfer_payload(**data: object) -> TransferPayload:
    source_warehouse_id = _required_int(
        data.get("source_warehouse_id"), "com_warehouse.error.source_warehouse_required"
    )
    target_warehouse_id = _required_int(
        data.get("target_warehouse_id"), "com_warehouse.error.target_warehouse_required"
    )
    source_location_id = _optional_int(data.get("source_location_id"))
    target_location_id = _optional_int(data.get("target_location_id"))
    if source_warehouse_id == target_warehouse_id and source_location_id == target_location_id:
        raise WarehouseError("com_warehouse.error.transfer_same_location")
    return TransferPayload(
        number=normalize_code(str(data.get("number") or ""), fallback="TRANSFER"),
        source_warehouse_id=source_warehouse_id,
        source_location_id=source_location_id,
        target_warehouse_id=target_warehouse_id,
        target_location_id=target_location_id,
        material_id=_required_int(data.get("material_id"), "com_warehouse.error.material_required"),
        quantity=_positive_decimal(data.get("quantity"), "com_warehouse.error.quantity_positive"),
        unit_price=_decimal(data.get("unit_price")),
        batch_number=str(data.get("batch_number") or "").strip(),
        note=str(data.get("note") or "").strip(),
    )


async def _exists_by(
    db: AsyncSession, model: type, field: object, value: str, exclude_id: int | None
) -> bool:
    query = select(model).where(field == value)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    return (await db.execute(query)).scalar_one_or_none() is not None


async def dashboard_stats(db: AsyncSession) -> DashboardStats:
    materials = await db.scalar(select(func.count(Material.id)))
    warehouses = await db.scalar(select(func.count(Warehouse.id)))
    projects = await db.scalar(select(func.count(ConstructionProject.id)))
    reservations = await db.scalar(
        select(func.count(StockReservation.id)).where(
            StockReservation.status.in_([RESERVATION_ACTIVE, RESERVATION_PARTIAL])
        )
    )
    levels = (
        await db.execute(
            select(StockLevel, Material)
            .join(Material, Material.id == StockLevel.material_id)
            .where(Material.min_stock > 0)
        )
    ).all()
    low_stock = sum(
        1 for level, material in levels if level.quantity_available < material.min_stock
    )
    return DashboardStats(
        materials=int(materials or 0),
        warehouses=int(warehouses or 0),
        projects=int(projects or 0),
        active_reservations=int(reservations or 0),
        low_stock=low_stock,
    )


async def list_units(db: AsyncSession) -> list[Unit]:
    query = select(Unit).order_by(Unit.code.asc())
    return (await db.execute(query)).scalars().all()


async def get_or_create_unit(db: AsyncSession, code: str, *, name: str = "") -> tuple[Unit, bool]:
    clean_code = normalize_unit_code(code)
    unit = (
        await db.execute(select(Unit).where(Unit.code == clean_code))
    ).scalar_one_or_none()
    if unit is not None:
        return unit, False
    unit = Unit(code=clean_code, name=name.strip() or clean_code)
    db.add(unit)
    await db.flush()
    return unit, True


async def list_materials(db: AsyncSession, *, q: str | None = None) -> list[Material]:
    query = select(Material).options(selectinload(Material.unit_ref))
    clean_q = (q or "").strip()
    if clean_q:
        like = f"%{clean_q}%"
        query = query.where(
            Material.name.like(like) | Material.sku.like(like) | Material.ean.like(like)
        )
    query = query.order_by(Material.name.asc(), Material.id.asc())
    return (await db.execute(query)).scalars().all()


async def get_material(db: AsyncSession, material_id: int) -> Material | None:
    return (
        await db.execute(
            select(Material)
            .where(Material.id == material_id)
            .options(selectinload(Material.unit_ref), selectinload(Material.batches))
        )
    ).scalar_one_or_none()


async def list_material_batches(
    db: AsyncSession, material_id: int | None = None
) -> list[MaterialBatch]:
    query = select(MaterialBatch).options(selectinload(MaterialBatch.material))
    if material_id:
        query = query.where(MaterialBatch.material_id == material_id)
    query = query.order_by(MaterialBatch.batch_number.asc(), MaterialBatch.id.asc())
    return (await db.execute(query)).scalars().all()


async def get_or_create_material_batch(
    db: AsyncSession,
    material_id: int,
    batch_number: str,
    *,
    notes: str = "",
) -> tuple[MaterialBatch, bool]:
    clean_batch = batch_number.strip()
    if not clean_batch:
        raise WarehouseError("com_warehouse.error.batch_number_required")
    batch = (
        await db.execute(
            select(MaterialBatch).where(
                MaterialBatch.material_id == material_id,
                MaterialBatch.batch_number == clean_batch,
            )
        )
    ).scalar_one_or_none()
    if batch is not None:
        batch.last_seen_at = datetime.now()
        if notes and notes not in batch.notes:
            batch.notes = f"{batch.notes}\n{notes}".strip()
        return batch, False
    batch = MaterialBatch(
        material_id=material_id,
        batch_number=clean_batch,
        notes=notes.strip(),
    )
    db.add(batch)
    await db.flush()
    return batch, True


async def create_material_batch(
    db: AsyncSession, payload: MaterialBatchPayload
) -> MaterialBatch:
    material = await get_material(db, payload.material_id)
    if material is None:
        raise WarehouseError("com_warehouse.error.material_required")
    batch = (
        await db.execute(
            select(MaterialBatch).where(
                MaterialBatch.material_id == payload.material_id,
                MaterialBatch.batch_number == payload.batch_number,
            )
        )
    ).scalar_one_or_none()
    if batch is not None:
        raise WarehouseError(
            "com_warehouse.error.batch_number_exists", batch=payload.batch_number
        )
    batch = MaterialBatch(**payload.__dict__)
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


async def list_material_movements(db: AsyncSession, material_id: int) -> list[StockMovement]:
    query = (
        select(StockMovement)
        .where(StockMovement.material_id == material_id)
        .options(
            selectinload(StockMovement.document),
            selectinload(StockMovement.warehouse),
            selectinload(StockMovement.location),
            selectinload(StockMovement.project),
        )
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    )
    return (await db.execute(query)).scalars().all()


async def create_material(db: AsyncSession, payload: MaterialPayload) -> Material:
    if await _exists_by(db, Material, Material.sku, payload.sku, None):
        raise WarehouseError("com_warehouse.error.sku_exists", sku=payload.sku)
    if payload.ean and await _exists_by(db, Material, Material.ean, payload.ean, None):
        raise WarehouseError("com_warehouse.error.ean_exists", ean=payload.ean)
    values = payload.__dict__.copy()
    if payload.unit_id is None:
        unit, _created = await get_or_create_unit(db, payload.unit)
        values["unit_id"] = unit.id
        values["unit"] = unit.code
    material = Material(**values)
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


async def update_material(
    db: AsyncSession, material: Material, payload: MaterialPayload
) -> Material:
    if await _exists_by(db, Material, Material.sku, payload.sku, material.id):
        raise WarehouseError("com_warehouse.error.sku_exists", sku=payload.sku)
    if payload.ean and await _exists_by(db, Material, Material.ean, payload.ean, material.id):
        raise WarehouseError("com_warehouse.error.ean_exists", ean=payload.ean)
    values = payload.__dict__.copy()
    if payload.unit_id is None:
        unit, _created = await get_or_create_unit(db, payload.unit)
        values["unit_id"] = unit.id
        values["unit"] = unit.code
    for key, value in values.items():
        setattr(material, key, value)
    await db.commit()
    await db.refresh(material)
    return material


def parse_material_sql_dump(sql_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for values_sql in _iter_material_insert_values(sql_text):
        for raw_row in _split_sql_value_rows(values_sql):
            values = literal_eval(f"({raw_row})")
            if len(values) != 5:
                continue
            external_id, supplier_code, name, batch, unit = values
            rows.append(
                {
                    "external_id": str(external_id or "").strip(),
                    "sku": str(supplier_code or "").strip(),
                    "name": str(name or "").strip(),
                    "batch_number": str(batch or "").strip(),
                    "unit": normalize_unit_code(unit),
                }
            )
    return rows


def _iter_material_insert_values(sql_text: str) -> list[str]:
    inserts: list[str] = []
    pattern = re.compile(r"INSERT\s+INTO\s+`?material`?\s+VALUES\s*", re.IGNORECASE)
    for match in pattern.finditer(sql_text):
        start = match.end()
        in_string = False
        escape = False
        for index, char in enumerate(sql_text[start:], start=start):
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == "'":
                    in_string = False
                continue
            if char == "'":
                in_string = True
            elif char == ";":
                inserts.append(sql_text[start:index])
                break
    return inserts


def _split_sql_value_rows(values_sql: str) -> list[str]:
    rows: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escape = False
    for char in values_sql.strip():
        if in_string:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_string = False
            continue
        if char == "'":
            in_string = True
            current.append(char)
        elif char == "(":
            if depth:
                current.append(char)
            depth += 1
        elif char == ")":
            depth -= 1
            if depth:
                current.append(char)
            elif current:
                rows.append("".join(current))
                current = []
        elif depth:
            current.append(char)
    return rows


async def import_materials_from_sql_dump(db: AsyncSession, sql_text: str) -> MaterialImportResult:
    rows = parse_material_sql_dump(sql_text)
    created = 0
    updated = 0
    skipped = 0
    units_created = 0
    batches_created = 0
    seen_skus: set[str] = set()
    materials_by_sku: dict[str, Material] = {}
    for row in rows:
        sku = normalize_code(row["sku"], fallback=row["name"])
        name = row["name"]
        if not sku or not name:
            skipped += 1
            continue
        material = materials_by_sku.get(sku)
        if material is None:
            material = (
                await db.execute(select(Material).where(Material.sku == sku))
            ).scalar_one_or_none()
        notes = f"Import ID: {row['external_id']}" if row["external_id"] else ""
        if sku not in seen_skus:
            seen_skus.add(sku)
            unit, was_created = await get_or_create_unit(db, row["unit"])
            units_created += int(was_created)
            if material is None:
                material = Material(
                    sku=sku,
                    name=name,
                    unit=unit.code,
                    unit_id=unit.id,
                    notes=notes,
                )
                db.add(material)
                await db.flush()
                created += 1
            else:
                material.name = name
                material.unit = unit.code
                material.unit_id = unit.id
                if notes and notes not in material.notes:
                    material.notes = f"{material.notes}\n{notes}".strip()
                updated += 1
            materials_by_sku[sku] = material
        else:
            skipped += 1
        if material is not None and row["batch_number"]:
            batch_notes = f"Import ID: {row['external_id']}" if row["external_id"] else ""
            _batch, was_created = await get_or_create_material_batch(
                db,
                material.id,
                row["batch_number"],
                notes=batch_notes,
            )
            batches_created += int(was_created)
    await db.commit()
    return MaterialImportResult(
        rows=len(rows),
        created=created,
        updated=updated,
        skipped=skipped,
        units_created=units_created,
        batches_created=batches_created,
    )


async def list_warehouses(db: AsyncSession) -> list[Warehouse]:
    query = select(Warehouse).order_by(Warehouse.is_default.desc(), Warehouse.name.asc())
    return (await db.execute(query)).scalars().all()


async def get_warehouse(db: AsyncSession, warehouse_id: int) -> Warehouse | None:
    return (
        await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    ).scalar_one_or_none()


async def create_warehouse(db: AsyncSession, payload: WarehousePayload) -> Warehouse:
    if await _exists_by(db, Warehouse, Warehouse.code, payload.code, None):
        raise WarehouseError("com_warehouse.error.warehouse_code_exists", code=payload.code)
    if payload.is_default:
        await _clear_default_warehouses(db)
    warehouse = Warehouse(**payload.__dict__)
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def update_warehouse(
    db: AsyncSession, warehouse: Warehouse, payload: WarehousePayload
) -> Warehouse:
    if await _exists_by(db, Warehouse, Warehouse.code, payload.code, warehouse.id):
        raise WarehouseError("com_warehouse.error.warehouse_code_exists", code=payload.code)
    if payload.is_default:
        await _clear_default_warehouses(db)
    for key, value in payload.__dict__.items():
        setattr(warehouse, key, value)
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def _clear_default_warehouses(db: AsyncSession) -> None:
    for warehouse in (
        await db.execute(select(Warehouse).where(Warehouse.is_default.is_(True)))
    ).scalars():
        warehouse.is_default = False


async def list_locations(db: AsyncSession, warehouse_id: int | None = None) -> list[StockLocation]:
    query = select(StockLocation).options(selectinload(StockLocation.warehouse))
    if warehouse_id:
        query = query.where(StockLocation.warehouse_id == warehouse_id)
    query = query.order_by(StockLocation.code.asc())
    return (await db.execute(query)).scalars().all()


async def create_location(db: AsyncSession, payload: LocationPayload) -> StockLocation:
    location = StockLocation(**payload.__dict__)
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


async def list_projects(db: AsyncSession, *, q: str | None = None) -> list[ConstructionProject]:
    query = select(ConstructionProject).options(selectinload(ConstructionProject.directions))
    clean_q = (q or "").strip()
    if clean_q:
        like = f"%{clean_q}%"
        query = query.where(
            ConstructionProject.name.like(like) | ConstructionProject.code.like(like)
        )
    query = query.order_by(ConstructionProject.status.asc(), ConstructionProject.name.asc())
    return (await db.execute(query)).scalars().all()


async def get_project(db: AsyncSession, project_id: int) -> ConstructionProject | None:
    return (
        await db.execute(
            select(ConstructionProject)
            .where(ConstructionProject.id == project_id)
            .options(
                selectinload(ConstructionProject.directions).selectinload(
                    ProjectDirection.sections
                )
            )
        )
    ).scalar_one_or_none()


async def create_project(db: AsyncSession, payload: ProjectPayload) -> ConstructionProject:
    if await _exists_by(db, ConstructionProject, ConstructionProject.code, payload.code, None):
        raise WarehouseError("com_warehouse.error.project_code_exists", code=payload.code)
    project = ConstructionProject(**payload.__dict__)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_project_directions(
    db: AsyncSession, project_id: int | None = None
) -> list[ProjectDirection]:
    query = select(ProjectDirection).options(selectinload(ProjectDirection.sections))
    if project_id:
        query = query.where(ProjectDirection.project_id == project_id)
    query = query.order_by(ProjectDirection.code.asc(), ProjectDirection.id.asc())
    return (await db.execute(query)).scalars().all()


async def create_project_direction(
    db: AsyncSession, payload: ProjectDirectionPayload
) -> ProjectDirection:
    existing = (
        await db.execute(
            select(ProjectDirection).where(
                ProjectDirection.project_id == payload.project_id,
                ProjectDirection.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise WarehouseError("com_warehouse.error.direction_code_exists", code=payload.code)
    direction = ProjectDirection(
        project_id=payload.project_id,
        code=payload.code,
        name=payload.name,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(direction)
    await db.commit()
    await db.refresh(direction)
    return direction


async def create_project_budget_section(
    db: AsyncSession, payload: ProjectBudgetSectionPayload
) -> ProjectBudgetSection:
    existing = (
        await db.execute(
            select(ProjectBudgetSection).where(
                ProjectBudgetSection.direction_id == payload.direction_id,
                ProjectBudgetSection.source_type == payload.source_type,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise WarehouseError(
            "com_warehouse.error.budget_section_code_exists", code=payload.source_type
        )
    section = ProjectBudgetSection(**payload.__dict__)
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


async def list_project_budgets(db: AsyncSession, project_id: int) -> list[Budget]:
    query = (
        select(Budget)
        .where(Budget.project_id == project_id)
        .options(
            selectinload(Budget.items)
            .selectinload(BudgetItem.material)
            .selectinload(Material.unit_ref),
            selectinload(Budget.items).selectinload(BudgetItem.section),
        )
        .order_by(Budget.created_at.desc(), Budget.id.desc())
    )
    return (await db.execute(query)).scalars().all()


async def create_budget(db: AsyncSession, payload: BudgetPayload) -> Budget:
    budget = Budget(project_id=payload.project_id, name=payload.name, status=payload.status)
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


async def create_budget_item(db: AsyncSession, payload: BudgetItemPayload) -> BudgetItem:
    budget = (
        await db.execute(select(Budget).where(Budget.id == payload.budget_id))
    ).scalar_one_or_none()
    if budget is None:
        raise WarehouseError("com_warehouse.error.budget_required")
    if payload.section_id is not None:
        section = (
            await db.execute(
                select(ProjectBudgetSection)
                .join(ProjectDirection, ProjectDirection.id == ProjectBudgetSection.direction_id)
                .where(
                    ProjectBudgetSection.id == payload.section_id,
                    ProjectDirection.project_id == budget.project_id,
                )
            )
        ).scalar_one_or_none()
        if section is None:
            raise WarehouseError("com_warehouse.error.budget_section_required")
    item = BudgetItem(**payload.__dict__)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def project_material_balance(
    db: AsyncSession, project_id: int
) -> list[ProjectMaterialBalance]:
    budget_rows = (
        await db.execute(
            select(BudgetItem.material_id, func.sum(BudgetItem.quantity))
            .join(Budget, Budget.id == BudgetItem.budget_id)
            .where(Budget.project_id == project_id)
            .group_by(BudgetItem.material_id)
        )
    ).all()
    issue_rows = (
        await db.execute(
            select(StockMovement.material_id, func.sum(-StockMovement.quantity))
            .where(
                StockMovement.project_id == project_id,
                StockMovement.movement_type == MOVEMENT_ISSUE,
            )
            .group_by(StockMovement.material_id)
        )
    ).all()
    budget_by_material = {
        int(material_id): Decimal(str(quantity or 0)) for material_id, quantity in budget_rows
    }
    issued_by_material = {
        int(material_id): Decimal(str(quantity or 0)) for material_id, quantity in issue_rows
    }
    material_ids = sorted(set(budget_by_material) | set(issued_by_material))
    if not material_ids:
        return []
    materials = (
        await db.execute(
            select(Material)
            .where(Material.id.in_(material_ids))
            .options(selectinload(Material.unit_ref))
        )
    ).scalars()
    by_id = {material.id: material for material in materials}
    balance: list[ProjectMaterialBalance] = []
    for material_id in material_ids:
        material = by_id.get(material_id)
        if material is None:
            continue
        budget_quantity = budget_by_material.get(material_id, Decimal("0"))
        issued_quantity = issued_by_material.get(material_id, Decimal("0"))
        balance.append(
            ProjectMaterialBalance(
                material=material,
                budget_quantity=budget_quantity,
                issued_quantity=issued_quantity,
                remaining_quantity=max(budget_quantity - issued_quantity, Decimal("0")),
                over_budget_quantity=max(issued_quantity - budget_quantity, Decimal("0")),
            )
        )
    return balance


async def update_project(
    db: AsyncSession,
    project: ConstructionProject,
    payload: ProjectPayload,
) -> ConstructionProject:
    if await _exists_by(
        db, ConstructionProject, ConstructionProject.code, payload.code, project.id
    ):
        raise WarehouseError("com_warehouse.error.project_code_exists", code=payload.code)
    for key, value in payload.__dict__.items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)
    return project


async def list_stock_levels(
    db: AsyncSession, *, material_id: int | None = None
) -> list[StockLevel]:
    query = (
        select(StockLevel)
        .options(
            selectinload(StockLevel.material),
            selectinload(StockLevel.warehouse),
            selectinload(StockLevel.location),
        )
        .order_by(StockLevel.updated_at.desc(), StockLevel.id.desc())
    )
    if material_id:
        query = query.where(StockLevel.material_id == material_id)
    return (await db.execute(query)).scalars().all()


async def list_documents(db: AsyncSession, document_type: str | None = None) -> list[StockDocument]:
    query = (
        select(StockDocument)
        .options(selectinload(StockDocument.warehouse), selectinload(StockDocument.project))
        .order_by(StockDocument.issued_at.desc(), StockDocument.id.desc())
    )
    if document_type:
        query = query.where(StockDocument.document_type == document_type)
    return (await db.execute(query)).scalars().all()


async def get_document(db: AsyncSession, document_id: int) -> StockDocument | None:
    query = (
        select(StockDocument)
        .where(StockDocument.id == document_id)
        .options(
            selectinload(StockDocument.warehouse),
            selectinload(StockDocument.project),
            selectinload(StockDocument.items)
            .selectinload(StockDocumentItem.material)
            .selectinload(Material.unit_ref),
            selectinload(StockDocument.items).selectinload(StockDocumentItem.location),
            selectinload(StockDocument.movements)
            .selectinload(StockMovement.material)
            .selectinload(Material.unit_ref),
            selectinload(StockDocument.movements).selectinload(StockMovement.location),
        )
    )
    return (await db.execute(query)).scalar_one_or_none()


async def create_document(db: AsyncSession, payload: DocumentPayload) -> StockDocument:
    number = payload.number or await _next_timestamp_document_number(db)
    if await _exists_by(db, StockDocument, StockDocument.number, number, None):
        raise WarehouseError("com_warehouse.error.document_number_exists", number=number)
    if payload.document_type == DOCUMENT_ISSUE and payload.project_id is None:
        raise WarehouseError("com_warehouse.error.project_required")

    document = StockDocument(
        number=number,
        document_type=payload.document_type,
        warehouse_id=payload.warehouse_id,
        project_id=payload.project_id,
        partner=payload.partner,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(document)
    await db.flush()

    for item_payload in payload.items:
        item = StockDocumentItem(document_id=document.id, **item_payload.__dict__)
        db.add(item)
        await _apply_document_item(db, document, item_payload)

    await db.commit()
    await db.refresh(document)
    return document


async def reverse_document(db: AsyncSession, document_id: int) -> StockDocument:
    document = await get_document(db, document_id)
    if document is None:
        raise WarehouseError("com_warehouse.error.document_not_found")
    if document.status == DOCUMENT_STATUS_REVERSED:
        raise WarehouseError("com_warehouse.error.document_already_reversed")
    if document.document_type == DOCUMENT_RECEIPT:
        reverse_type = DOCUMENT_ISSUE
    elif document.document_type == DOCUMENT_ISSUE:
        reverse_type = DOCUMENT_RECEIPT
    else:
        raise WarehouseError("com_warehouse.error.document_type_invalid")

    reverse_payload = DocumentPayload(
        number=await _next_reverse_number(db, document.number),
        document_type=reverse_type,
        warehouse_id=document.warehouse_id,
        project_id=document.project_id,
        partner=document.partner,
        reference=document.number,
        notes=f"Reverse of {document.number}",
        items=[
            DocumentItemPayload(
                material_id=item.material_id,
                location_id=item.location_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                batch_number=item.batch_number,
                expires_on=item.expires_on,
                note=f"Reverse of {document.number}",
            )
            for item in document.items
        ],
    )
    reverse = await _create_document_uncommitted(
        db,
        reverse_payload,
        require_project_for_issue=False,
    )
    document.status = DOCUMENT_STATUS_REVERSED
    await db.commit()
    await db.refresh(reverse)
    return reverse


async def create_reservation(db: AsyncSession, payload: ReservationPayload) -> StockReservation:
    reservation = StockReservation(**payload.__dict__)
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)
    return reservation


async def list_reservations(db: AsyncSession) -> list[StockReservation]:
    query = (
        select(StockReservation)
        .options(
            selectinload(StockReservation.material),
            selectinload(StockReservation.warehouse),
            selectinload(StockReservation.project),
        )
        .order_by(StockReservation.created_at.desc(), StockReservation.id.desc())
    )
    reservations = (await db.execute(query)).scalars().all()
    for reservation in reservations:
        level = await _get_stock_level(
            db,
            warehouse_id=reservation.warehouse_id,
            location_id=reservation.location_id,
            material_id=reservation.material_id,
            batch_number="",
            create=False,
        )
        available = max(level.quantity_available, Decimal("0")) if level else Decimal("0")
        open_quantity = reservation.quantity_open
        reservation.quantity_available_now = min(available, open_quantity)
        reservation.quantity_missing = max(open_quantity - available, Decimal("0"))
    return reservations


async def get_reservation(db: AsyncSession, reservation_id: int) -> StockReservation | None:
    query = (
        select(StockReservation)
        .where(StockReservation.id == reservation_id)
        .options(
            selectinload(StockReservation.material),
            selectinload(StockReservation.warehouse),
            selectinload(StockReservation.project),
            selectinload(StockReservation.location),
        )
    )
    return (await db.execute(query)).scalar_one_or_none()


async def issue_reservation(db: AsyncSession, reservation_id: int) -> StockDocument:
    reservation = await get_reservation(db, reservation_id)
    if reservation is None:
        raise WarehouseError("com_warehouse.error.reservation_not_found")
    if reservation.status in {RESERVATION_RELEASED, RESERVATION_CANCELLED}:
        raise WarehouseError("com_warehouse.error.reservation_closed")
    quantity = reservation.quantity_open
    if quantity <= 0:
        raise WarehouseError("com_warehouse.error.reservation_closed")

    document = await _create_document_uncommitted(
        db,
        DocumentPayload(
            number=await _next_prefixed_number(db, "VYR", reservation.id),
            document_type=DOCUMENT_ISSUE,
            warehouse_id=reservation.warehouse_id,
            project_id=reservation.project_id,
            partner="",
            reference=f"RES-{reservation.id}",
            notes=f"Issue from reservation #{reservation.id}",
            items=[
                DocumentItemPayload(
                    material_id=reservation.material_id,
                    location_id=reservation.location_id,
                    quantity=quantity,
                    unit_price=Decimal("0"),
                    batch_number="",
                    expires_on=None,
                    note=reservation.note,
                )
            ],
        ),
    )
    reservation.quantity_released += quantity
    reservation.status = RESERVATION_RELEASED
    await db.commit()
    await db.refresh(document)
    return document


async def transfer_stock(
    db: AsyncSession, payload: TransferPayload
) -> tuple[StockDocument, StockDocument]:
    source_number = await _next_prefixed_number(db, f"{payload.number}-OUT", 0)
    target_number = await _next_prefixed_number(db, f"{payload.number}-IN", 0)
    issue_payload = DocumentPayload(
        number=source_number,
        document_type=DOCUMENT_ISSUE,
        warehouse_id=payload.source_warehouse_id,
        project_id=None,
        partner="",
        reference=target_number,
        notes=payload.note,
        items=[
            DocumentItemPayload(
                material_id=payload.material_id,
                location_id=payload.source_location_id,
                quantity=payload.quantity,
                unit_price=payload.unit_price,
                batch_number=payload.batch_number,
                expires_on=None,
                note=payload.note,
            )
        ],
    )
    receipt_payload = DocumentPayload(
        number=target_number,
        document_type=DOCUMENT_RECEIPT,
        warehouse_id=payload.target_warehouse_id,
        project_id=None,
        partner="",
        reference=source_number,
        notes=payload.note,
        items=[
            DocumentItemPayload(
                material_id=payload.material_id,
                location_id=payload.target_location_id,
                quantity=payload.quantity,
                unit_price=payload.unit_price,
                batch_number=payload.batch_number,
                expires_on=None,
                note=payload.note,
            )
        ],
    )
    source = await _create_document_uncommitted(db, issue_payload, require_project_for_issue=False)
    target = await _create_document_uncommitted(db, receipt_payload)
    await db.commit()
    await db.refresh(source)
    await db.refresh(target)
    return source, target


async def _apply_document_item(
    db: AsyncSession,
    document: StockDocument,
    item: DocumentItemPayload,
) -> None:
    if item.batch_number:
        await get_or_create_material_batch(db, item.material_id, item.batch_number)
    if document.document_type == DOCUMENT_RECEIPT:
        level = await _get_stock_level(
            db,
            warehouse_id=document.warehouse_id,
            location_id=item.location_id,
            material_id=item.material_id,
            batch_number=item.batch_number,
            create=True,
        )
        assert level is not None
        previous_qty = level.quantity_on_hand
        level.quantity_on_hand += item.quantity
        if item.expires_on:
            level.expires_on = item.expires_on
        if item.unit_price > 0:
            total_value = previous_qty * level.average_price + item.quantity * item.unit_price
            level.average_price = total_value / level.quantity_on_hand
        movement_type = MOVEMENT_RECEIPT
        movement_qty = item.quantity
    elif document.document_type == DOCUMENT_ISSUE:
        level = await _get_stock_level(
            db,
            warehouse_id=document.warehouse_id,
            location_id=item.location_id,
            material_id=item.material_id,
            batch_number=item.batch_number,
            create=True,
        )
        assert level is not None
        level.quantity_on_hand -= item.quantity
        movement_type = MOVEMENT_ISSUE
        movement_qty = -item.quantity
    else:
        raise WarehouseError("com_warehouse.error.document_type_invalid")

    db.add(
        StockMovement(
            document_id=document.id,
            material_id=item.material_id,
            warehouse_id=document.warehouse_id,
            location_id=item.location_id,
            project_id=document.project_id,
            movement_type=movement_type,
            quantity=movement_qty,
            unit_price=item.unit_price,
            batch_number=item.batch_number,
            expires_on=item.expires_on,
            reason=document.document_type,
        )
    )


async def _create_document_uncommitted(
    db: AsyncSession,
    payload: DocumentPayload,
    *,
    require_project_for_issue: bool = True,
) -> StockDocument:
    number = payload.number or await _next_timestamp_document_number(db)
    if await _exists_by(db, StockDocument, StockDocument.number, number, None):
        raise WarehouseError("com_warehouse.error.document_number_exists", number=number)
    if (
        require_project_for_issue
        and payload.document_type == DOCUMENT_ISSUE
        and payload.project_id is None
    ):
        raise WarehouseError("com_warehouse.error.project_required")

    document = StockDocument(
        number=number,
        document_type=payload.document_type,
        warehouse_id=payload.warehouse_id,
        project_id=payload.project_id,
        partner=payload.partner,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(document)
    await db.flush()
    for item_payload in payload.items:
        item = StockDocumentItem(document_id=document.id, **item_payload.__dict__)
        db.add(item)
        await _apply_document_item(db, document, item_payload)
    return document


async def _next_reverse_number(db: AsyncSession, original_number: str) -> str:
    base = normalize_code(f"STORNO-{original_number}", fallback="STORNO")
    candidate = base
    suffix = 1
    while await _exists_by(db, StockDocument, StockDocument.number, candidate, None):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


async def _next_prefixed_number(db: AsyncSession, prefix: str, source_id: int) -> str:
    base = normalize_code(f"{prefix}-{source_id}" if source_id else prefix, fallback=prefix)
    candidate = base
    suffix = 1
    while await _exists_by(db, StockDocument, StockDocument.number, candidate, None):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


async def _next_timestamp_document_number(db: AsyncSession) -> str:
    base = datetime.now().strftime("%Y%m%d%H%M")
    for suffix in range(1, 100):
        candidate = f"{base}{suffix:02d}"
        if not await _exists_by(db, StockDocument, StockDocument.number, candidate, None):
            return candidate
    return await _next_prefixed_number(db, base, 0)


async def _get_stock_level(
    db: AsyncSession,
    *,
    warehouse_id: int,
    location_id: int | None,
    material_id: int,
    batch_number: str,
    create: bool,
) -> StockLevel | None:
    query = select(StockLevel).where(
        StockLevel.warehouse_id == warehouse_id,
        StockLevel.material_id == material_id,
        StockLevel.batch_number == batch_number,
    )
    if location_id is None:
        query = query.where(StockLevel.location_id.is_(None))
    else:
        query = query.where(StockLevel.location_id == location_id)
    level = (await db.execute(query)).scalar_one_or_none()
    if level is None and create:
        level = StockLevel(
            warehouse_id=warehouse_id,
            location_id=location_id,
            material_id=material_id,
            batch_number=batch_number,
        )
        db.add(level)
        await db.flush()
    return level
