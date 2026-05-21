from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.admin.deps import CurrentAdminUser
from src.api.admin.render import admin_render
from src.core.system_settings import get_runtime_settings
from src.core.templates import make_t
from src.database.base import get_db_session

from .service import (
    DOCUMENT_ISSUE,
    DOCUMENT_RECEIPT,
    WarehouseError,
    build_document_payload,
    build_location_payload,
    build_material_payload,
    build_project_payload,
    build_reservation_payload,
    build_transfer_payload,
    build_warehouse_payload,
    create_document,
    create_location,
    create_material,
    create_project,
    create_reservation,
    create_warehouse,
    dashboard_stats,
    get_document,
    get_material,
    get_project,
    get_warehouse,
    issue_reservation,
    list_documents,
    list_locations,
    list_material_movements,
    list_materials,
    list_projects,
    list_reservations,
    list_stock_levels,
    list_warehouses,
    reverse_document,
    transfer_stock,
    update_material,
    update_project,
    update_warehouse,
)

router = APIRouter(prefix="/admin/com_warehouse", tags=["com_warehouse"])
_BASE = "/admin/com_warehouse"


async def _ct(db: AsyncSession):
    runtime = await get_runtime_settings(db)
    return make_t(runtime.locale, "com_warehouse")


def _flash(request: Request, flash_type: str, text: str) -> None:
    request.session["flash"] = {"type": flash_type, "text": text}


def _pop_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


def _form_bool(form: object, key: str) -> bool:
    return str(form.get(key, "")).lower() in {"1", "true", "on", "yes"}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/index.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        stats=await dashboard_stats(db),
        stock_levels=await list_stock_levels(db),
        reservations=await list_reservations(db),
        flash=_pop_flash(request),
    )


@router.get("/materials", response_class=HTMLResponse)
async def materials(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    q = request.query_params.get("q", "")
    return await admin_render(
        "admin/com_warehouse/materials.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        materials=await list_materials(db, q=q),
        filters={"q": q},
        flash=_pop_flash(request),
    )


@router.get("/materials/new", response_class=HTMLResponse)
async def material_new_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/material_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        material=None,
        flash=_pop_flash(request),
    )


@router.post("/materials/new")
async def material_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        material = await create_material(db, build_material_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/materials/new", status_code=303)
    _flash(request, "success", ct("com_warehouse.success.material_created", name=material.name))
    return RedirectResponse(f"{_BASE}/materials", status_code=303)


@router.get("/materials/{material_id}/edit", response_class=HTMLResponse)
async def material_edit_form(
    material_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    material = await get_material(db, material_id)
    if material is None:
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    return await admin_render(
        "admin/com_warehouse/material_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        material=material,
        flash=_pop_flash(request),
    )


@router.get("/materials/{material_id}/stock", response_class=HTMLResponse)
async def material_stock_card(
    material_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    material = await get_material(db, material_id)
    if material is None:
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    return await admin_render(
        "admin/com_warehouse/material_stock.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        material=material,
        stock_levels=await list_stock_levels(db, material_id=material.id),
        movements=await list_material_movements(db, material.id),
        flash=_pop_flash(request),
    )


@router.post("/materials/{material_id}/edit")
async def material_edit_submit(
    material_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    material = await get_material(db, material_id)
    if material is None:
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    ct = await _ct(db)
    form = await request.form()
    try:
        await update_material(db, material, build_material_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/materials/{material_id}/edit", status_code=303)
    _flash(request, "success", ct("com_warehouse.success.material_updated"))
    return RedirectResponse(f"{_BASE}/materials", status_code=303)


@router.get("/warehouses", response_class=HTMLResponse)
async def warehouses(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/warehouses.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        warehouses=await list_warehouses(db),
        locations=await list_locations(db),
        flash=_pop_flash(request),
    )


@router.get("/warehouses/new", response_class=HTMLResponse)
async def warehouse_new_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/warehouse_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        warehouse=None,
        flash=_pop_flash(request),
    )


@router.post("/warehouses/new")
async def warehouse_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        warehouse = await create_warehouse(
            db,
            build_warehouse_payload(**{**dict(form), "is_default": _form_bool(form, "is_default")}),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/warehouses/new", status_code=303)
    _flash(request, "success", ct("com_warehouse.success.warehouse_created", name=warehouse.name))
    return RedirectResponse(f"{_BASE}/warehouses", status_code=303)


@router.get("/warehouses/{warehouse_id}/edit", response_class=HTMLResponse)
async def warehouse_edit_form(
    warehouse_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    warehouse = await get_warehouse(db, warehouse_id)
    if warehouse is None:
        return RedirectResponse(f"{_BASE}/warehouses", status_code=303)
    return await admin_render(
        "admin/com_warehouse/warehouse_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        warehouse=warehouse,
        flash=_pop_flash(request),
    )


@router.post("/warehouses/{warehouse_id}/edit")
async def warehouse_edit_submit(
    warehouse_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    warehouse = await get_warehouse(db, warehouse_id)
    if warehouse is None:
        return RedirectResponse(f"{_BASE}/warehouses", status_code=303)
    ct = await _ct(db)
    form = await request.form()
    try:
        await update_warehouse(
            db,
            warehouse,
            build_warehouse_payload(**{**dict(form), "is_default": _form_bool(form, "is_default")}),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/warehouses/{warehouse_id}/edit", status_code=303)
    _flash(request, "success", ct("com_warehouse.success.warehouse_updated"))
    return RedirectResponse(f"{_BASE}/warehouses", status_code=303)


@router.post("/locations/new")
async def location_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        await create_location(db, build_location_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.location_created"))
    return RedirectResponse(f"{_BASE}/warehouses", status_code=303)


@router.get("/projects", response_class=HTMLResponse)
async def projects(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    q = request.query_params.get("q", "")
    return await admin_render(
        "admin/com_warehouse/projects.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        projects=await list_projects(db, q=q),
        filters={"q": q},
        flash=_pop_flash(request),
    )


@router.get("/projects/new", response_class=HTMLResponse)
async def project_new_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/project_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        project=None,
        flash=_pop_flash(request),
    )


@router.post("/projects/new")
async def project_new_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        project = await create_project(db, build_project_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/projects/new", status_code=303)
    _flash(request, "success", ct("com_warehouse.success.project_created", name=project.name))
    return RedirectResponse(f"{_BASE}/projects", status_code=303)


@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
async def project_edit_form(
    project_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    project = await get_project(db, project_id)
    if project is None:
        return RedirectResponse(f"{_BASE}/projects", status_code=303)
    return await admin_render(
        "admin/com_warehouse/project_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        project=project,
        flash=_pop_flash(request),
    )


@router.post("/projects/{project_id}/edit")
async def project_edit_submit(
    project_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    project = await get_project(db, project_id)
    if project is None:
        return RedirectResponse(f"{_BASE}/projects", status_code=303)
    ct = await _ct(db)
    form = await request.form()
    try:
        await update_project(db, project, build_project_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/projects/{project_id}/edit", status_code=303)
    _flash(request, "success", ct("com_warehouse.success.project_updated"))
    return RedirectResponse(f"{_BASE}/projects", status_code=303)


@router.get("/receipts/new", response_class=HTMLResponse)
async def receipt_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await _document_form(request, user, db, DOCUMENT_RECEIPT)


@router.post("/receipts/new")
async def receipt_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    return await _document_submit(request, db, DOCUMENT_RECEIPT, f"{_BASE}/receipts/new")


@router.get("/issues/new", response_class=HTMLResponse)
async def issue_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await _document_form(request, user, db, DOCUMENT_ISSUE)


@router.post("/issues/new")
async def issue_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    return await _document_submit(request, db, DOCUMENT_ISSUE, f"{_BASE}/issues/new")


async def _document_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession,
    document_type: str,
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/document_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        document_type=document_type,
        materials=await list_materials(db),
        warehouses=await list_warehouses(db),
        locations=await list_locations(db),
        projects=await list_projects(db),
        flash=_pop_flash(request),
    )


async def _document_submit(
    request: Request,
    db: AsyncSession,
    document_type: str,
    retry_url: str,
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        document = await create_document(
            db,
            build_document_payload(document_type=document_type, data=form),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(retry_url, status_code=303)
    _flash(request, "success", ct("com_warehouse.success.document_created", number=document.number))
    return RedirectResponse(_BASE, status_code=303)


@router.get("/reservations/new", response_class=HTMLResponse)
async def reservation_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/reservation_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        materials=await list_materials(db),
        warehouses=await list_warehouses(db),
        locations=await list_locations(db),
        projects=await list_projects(db),
        flash=_pop_flash(request),
    )


@router.post("/reservations/new")
async def reservation_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        reservation = await create_reservation(db, build_reservation_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/reservations/new", status_code=303)
    _flash(
        request,
        "success",
        ct("com_warehouse.success.reservation_created", id=reservation.id),
    )
    return RedirectResponse(_BASE, status_code=303)


@router.post("/reservations/{reservation_id}/issue")
async def reservation_issue_submit(
    reservation_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    try:
        document = await issue_reservation(db, reservation_id)
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(_BASE, status_code=303)
    _flash(
        request,
        "success",
        ct("com_warehouse.success.reservation_issued", number=document.number),
    )
    return RedirectResponse(f"{_BASE}/documents/{document.id}", status_code=303)


@router.get("/transfers/new", response_class=HTMLResponse)
async def transfer_form(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/transfer_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        materials=await list_materials(db),
        warehouses=await list_warehouses(db),
        locations=await list_locations(db),
        flash=_pop_flash(request),
    )


@router.post("/transfers/new")
async def transfer_submit(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        source, target = await transfer_stock(db, build_transfer_payload(**dict(form)))
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/transfers/new", status_code=303)
    _flash(
        request,
        "success",
        ct("com_warehouse.success.transfer_created", source=source.number, target=target.number),
    )
    return RedirectResponse(f"{_BASE}/documents/{target.id}", status_code=303)


@router.get("/documents", response_class=HTMLResponse)
async def documents(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/documents.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        receipts=await list_documents(db, DOCUMENT_RECEIPT),
        issues=await list_documents(db, DOCUMENT_ISSUE),
        flash=_pop_flash(request),
    )


@router.get("/documents/{document_id}", response_class=HTMLResponse)
async def document_detail(
    document_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    document = await get_document(db, document_id)
    if document is None:
        return RedirectResponse(f"{_BASE}/documents", status_code=303)
    return await admin_render(
        "admin/com_warehouse/document_detail.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        document=document,
        flash=_pop_flash(request),
    )


@router.post("/documents/{document_id}/reverse")
async def document_reverse(
    document_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    try:
        reverse = await reverse_document(db, document_id)
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
        return RedirectResponse(f"{_BASE}/documents/{document_id}", status_code=303)
    _flash(
        request,
        "success",
        ct("com_warehouse.success.document_reversed", number=reverse.number),
    )
    return RedirectResponse(f"{_BASE}/documents/{reverse.id}", status_code=303)
