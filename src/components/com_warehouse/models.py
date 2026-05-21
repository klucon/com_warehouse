from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Material(Base):
    __tablename__ = "com_warehouse_materials"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_com_warehouse_material_sku"),
        UniqueConstraint("ean", name="uq_com_warehouse_material_ean"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    ean: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="ks", nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("21.00"), nullable=False
    )
    default_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("0"), nullable=False
    )
    min_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    stock_levels: Mapped[list[StockLevel]] = relationship(
        "StockLevel", back_populates="material", lazy="select"
    )
    movements: Mapped[list[StockMovement]] = relationship(
        "StockMovement", back_populates="material", lazy="select"
    )
    reservations: Mapped[list[StockReservation]] = relationship(
        "StockReservation", back_populates="material", lazy="select"
    )


class Warehouse(Base):
    __tablename__ = "com_warehouse_warehouses"
    __table_args__ = (UniqueConstraint("code", name="uq_com_warehouse_warehouse_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    locations: Mapped[list[StockLocation]] = relationship(
        "StockLocation", back_populates="warehouse", lazy="select"
    )
    stock_levels: Mapped[list[StockLevel]] = relationship(
        "StockLevel", back_populates="warehouse", lazy="select"
    )


class StockLocation(Base):
    __tablename__ = "com_warehouse_locations"
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_com_warehouse_location"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_warehouses.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    warehouse: Mapped[Warehouse] = relationship("Warehouse", back_populates="locations")
    stock_levels: Mapped[list[StockLevel]] = relationship(
        "StockLevel", back_populates="location", lazy="select"
    )


class ConstructionProject(Base):
    __tablename__ = "com_warehouse_projects"
    __table_args__ = (UniqueConstraint("code", name="uq_com_warehouse_project_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    budget_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    reservations: Mapped[list[StockReservation]] = relationship(
        "StockReservation", back_populates="project", lazy="select"
    )
    documents: Mapped[list[StockDocument]] = relationship(
        "StockDocument", back_populates="project", lazy="select"
    )
    budgets: Mapped[list[Budget]] = relationship("Budget", back_populates="project", lazy="select")


class Budget(Base):
    __tablename__ = "com_warehouse_budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("com_warehouse_projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    project: Mapped[ConstructionProject] = relationship(
        "ConstructionProject", back_populates="budgets"
    )
    items: Mapped[list[BudgetItem]] = relationship(
        "BudgetItem", back_populates="budget", lazy="select"
    )


class BudgetItem(Base):
    __tablename__ = "com_warehouse_budget_items"
    __table_args__ = (
        UniqueConstraint("budget_id", "material_id", name="uq_com_warehouse_budget_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("com_warehouse_budgets.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_materials.id"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("0"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    budget: Mapped[Budget] = relationship("Budget", back_populates="items")
    material: Mapped[Material] = relationship("Material")


class StockDocument(Base):
    __tablename__ = "com_warehouse_documents"
    __table_args__ = (UniqueConstraint("number", name="uq_com_warehouse_document_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(80), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_warehouses.id"), nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_projects.id"), nullable=True
    )
    partner: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    reference: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    project: Mapped[ConstructionProject | None] = relationship(
        "ConstructionProject", back_populates="documents"
    )
    items: Mapped[list[StockDocumentItem]] = relationship(
        "StockDocumentItem", back_populates="document", lazy="select"
    )
    movements: Mapped[list[StockMovement]] = relationship(
        "StockMovement", back_populates="document", lazy="select"
    )


class StockDocumentItem(Base):
    __tablename__ = "com_warehouse_document_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_documents.id"), nullable=False
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_materials.id"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_locations.id"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("0"), nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    document: Mapped[StockDocument] = relationship("StockDocument", back_populates="items")
    material: Mapped[Material] = relationship("Material")
    location: Mapped[StockLocation | None] = relationship("StockLocation")


class StockLevel(Base):
    __tablename__ = "com_warehouse_stock_levels"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "location_id",
            "material_id",
            "batch_number",
            name="uq_com_warehouse_stock_level",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_warehouses.id"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_locations.id"), nullable=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_materials.id"), nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0"), nullable=False
    )
    quantity_reserved: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0"), nullable=False
    )
    average_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("0"), nullable=False
    )
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    warehouse: Mapped[Warehouse] = relationship("Warehouse", back_populates="stock_levels")
    location: Mapped[StockLocation | None] = relationship(
        "StockLocation", back_populates="stock_levels"
    )
    material: Mapped[Material] = relationship("Material", back_populates="stock_levels")

    @property
    def quantity_available(self) -> Decimal:
        return self.quantity_on_hand - self.quantity_reserved


class StockMovement(Base):
    __tablename__ = "com_warehouse_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_documents.id"), nullable=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_materials.id"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_warehouses.id"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_locations.id"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_projects.id"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("0"), nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    document: Mapped[StockDocument | None] = relationship(
        "StockDocument", back_populates="movements"
    )
    material: Mapped[Material] = relationship("Material", back_populates="movements")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    location: Mapped[StockLocation | None] = relationship("StockLocation")
    project: Mapped[ConstructionProject | None] = relationship("ConstructionProject")


class StockReservation(Base):
    __tablename__ = "com_warehouse_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_materials.id"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("com_warehouse_warehouses.id"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("com_warehouse_locations.id"), nullable=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("com_warehouse_projects.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_released: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal("0"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    required_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    material: Mapped[Material] = relationship("Material", back_populates="reservations")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    location: Mapped[StockLocation | None] = relationship("StockLocation")
    project: Mapped[ConstructionProject] = relationship(
        "ConstructionProject", back_populates="reservations"
    )

    @property
    def quantity_open(self) -> Decimal:
        return self.quantity - self.quantity_released
