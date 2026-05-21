from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
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

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_ARCHIVED = "archived"
VALID_STATUSES = {STATUS_ACTIVE, STATUS_INACTIVE, STATUS_ARCHIVED}

DOCUMENT_RECEIPT = "receipt"
DOCUMENT_ISSUE = "issue"
DOCUMENT_ADJUSTMENT = "adjustment"
VALID_DOCUMENT_TYPES = {DOCUMENT_RECEIPT, DOCUMENT_ISSUE, DOCUMENT_ADJUSTMENT}

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
    status: str
    budget_total: Decimal
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
class DashboardStats:
    materials: int
    warehouses: int
    projects: int
    active_reservations: int
    low_stock: int


def normalize_code(value: str, fallback: str = "") -> str:
    cleaned = _CODE_RE.sub("-", (value or fallback).strip().upper()).strip("-")
    return cleaned or fallback.strip().upper()


def normalize_status(status: str | None) -> str:
    candidate = (status or STATUS_ACTIVE).strip().lower()
    return candidate if candidate in VALID_STATUSES else STATUS_ACTIVE


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


def build_material_payload(**data: object) -> MaterialPayload:
    name = str(data.get("name") or "").strip()
    if not name:
        raise WarehouseError("com_warehouse.error.material_name_required")
    sku = normalize_code(str(data.get("sku") or ""), fallback=name)
    if not sku:
        raise WarehouseError("com_warehouse.error.sku_required")
    return MaterialPayload(
        sku=sku,
        ean=str(data.get("ean") or "").strip(),
        name=name,
        description=str(data.get("description") or "").strip(),
        category=str(data.get("category") or "").strip(),
        unit=str(data.get("unit") or "ks").strip() or "ks",
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
        status=normalize_status(str(data.get("status") or "")),
        budget_total=_decimal(data.get("budget_total")),
        notes=str(data.get("notes") or "").strip(),
    )


def build_document_payload(
    *,
    document_type: str,
    number: object,
    warehouse_id: object,
    project_id: object,
    partner: object,
    reference: object,
    notes: object,
    material_id: object,
    location_id: object,
    quantity: object,
    unit_price: object,
    batch_number: object,
    expires_on: object,
    note: object,
) -> DocumentPayload:
    clean_type = str(document_type or "").strip().lower()
    if clean_type not in VALID_DOCUMENT_TYPES:
        raise WarehouseError("com_warehouse.error.document_type_invalid")
    clean_number = normalize_code(str(number or ""), fallback=clean_type)
    item = DocumentItemPayload(
        material_id=_required_int(material_id, "com_warehouse.error.material_required"),
        location_id=_optional_int(location_id),
        quantity=_positive_decimal(quantity, "com_warehouse.error.quantity_positive"),
        unit_price=_decimal(unit_price),
        batch_number=str(batch_number or "").strip(),
        expires_on=_optional_date(expires_on),
        note=str(note or "").strip(),
    )
    return DocumentPayload(
        number=clean_number,
        document_type=clean_type,
        warehouse_id=_required_int(warehouse_id, "com_warehouse.error.warehouse_required"),
        project_id=_optional_int(project_id),
        partner=str(partner or "").strip(),
        reference=str(reference or "").strip(),
        notes=str(notes or "").strip(),
        items=[item],
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


async def list_materials(db: AsyncSession, *, q: str | None = None) -> list[Material]:
    query = select(Material)
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
        await db.execute(select(Material).where(Material.id == material_id))
    ).scalar_one_or_none()


async def create_material(db: AsyncSession, payload: MaterialPayload) -> Material:
    if await _exists_by(db, Material, Material.sku, payload.sku, None):
        raise WarehouseError("com_warehouse.error.sku_exists", sku=payload.sku)
    if payload.ean and await _exists_by(db, Material, Material.ean, payload.ean, None):
        raise WarehouseError("com_warehouse.error.ean_exists", ean=payload.ean)
    material = Material(**payload.__dict__)
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
    for key, value in payload.__dict__.items():
        setattr(material, key, value)
    await db.commit()
    await db.refresh(material)
    return material


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
    query = select(ConstructionProject)
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
        await db.execute(select(ConstructionProject).where(ConstructionProject.id == project_id))
    ).scalar_one_or_none()


async def create_project(db: AsyncSession, payload: ProjectPayload) -> ConstructionProject:
    if await _exists_by(db, ConstructionProject, ConstructionProject.code, payload.code, None):
        raise WarehouseError("com_warehouse.error.project_code_exists", code=payload.code)
    project = ConstructionProject(**payload.__dict__)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


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


async def create_document(db: AsyncSession, payload: DocumentPayload) -> StockDocument:
    if await _exists_by(db, StockDocument, StockDocument.number, payload.number, None):
        raise WarehouseError("com_warehouse.error.document_number_exists", number=payload.number)
    if payload.document_type == DOCUMENT_ISSUE and payload.project_id is None:
        raise WarehouseError("com_warehouse.error.project_required")

    document = StockDocument(
        number=payload.number,
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


async def create_reservation(db: AsyncSession, payload: ReservationPayload) -> StockReservation:
    level = await _get_stock_level(
        db,
        warehouse_id=payload.warehouse_id,
        location_id=payload.location_id,
        material_id=payload.material_id,
        batch_number="",
        create=False,
    )
    if level is None or level.quantity_available < payload.quantity:
        raise WarehouseError("com_warehouse.error.insufficient_available_stock")

    reservation = StockReservation(**payload.__dict__)
    db.add(reservation)
    level.quantity_reserved += payload.quantity
    db.add(
        StockMovement(
            material_id=payload.material_id,
            warehouse_id=payload.warehouse_id,
            location_id=payload.location_id,
            project_id=payload.project_id,
            movement_type=MOVEMENT_RESERVE,
            quantity=payload.quantity,
            reason="reservation",
        )
    )
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
    return (await db.execute(query)).scalars().all()


async def _apply_document_item(
    db: AsyncSession,
    document: StockDocument,
    item: DocumentItemPayload,
) -> None:
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
            create=False,
        )
        if level is None or level.quantity_available < item.quantity:
            raise WarehouseError("com_warehouse.error.insufficient_available_stock")
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
