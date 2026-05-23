from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.admin.deps import CurrentAdminUser
from src.api.admin.render import admin_render
from src.core.system_settings import get_runtime_settings
from src.core.templates import make_t
from src.database.base import get_db_session

from .pdf import document_pdf_bytes
from .service import (
    DOCUMENT_ISSUE,
    DOCUMENT_RECEIPT,
    WarehouseError,
    build_budget_item_payload,
    build_budget_payload,
    build_document_payload,
    build_location_payload,
    build_material_batch_payload,
    build_material_payload,
    build_project_budget_section_payload,
    build_project_direction_payload,
    build_project_payload,
    build_reservation_payload,
    build_transfer_payload,
    build_warehouse_payload,
    count_materials,
    create_budget,
    create_budget_item,
    create_document,
    create_location,
    create_material,
    create_material_batch,
    create_project,
    create_project_budget_section,
    create_project_direction,
    create_reservation,
    create_warehouse,
    dashboard_stats,
    get_document,
    get_material,
    get_material_batch,
    get_project,
    get_warehouse,
    import_materials_from_sql_dump,
    import_materials_from_xlsx_workbook,
    issue_reservation,
    list_batch_inventory,
    list_documents,
    list_locations,
    list_material_batch_movements,
    list_material_batches,
    list_material_movements,
    list_material_page,
    list_materials,
    list_project_budgets,
    list_project_directions,
    list_projects,
    list_reservations,
    list_stock_levels,
    list_units,
    list_warehouses,
    project_material_balance,
    reverse_document,
    transfer_stock,
    update_material,
    update_material_batch,
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


@router.get("/batch-inventory", response_class=HTMLResponse)
async def batch_inventory(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    return await admin_render(
        "admin/com_warehouse/batch_inventory.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        rows=await list_batch_inventory(db),
        flash=_pop_flash(request),
    )


@router.get("/materials", response_class=HTMLResponse)
async def materials(
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    raw_q = request.query_params.get("q", "").strip()
    q = raw_q if len(raw_q) >= 3 else ""
    page_size = 50
    try:
        page = max(int(request.query_params.get("page", "1")), 1)
    except ValueError:
        page = 1
    total = await count_materials(db, q=q)
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    return await admin_render(
        "admin/com_warehouse/materials.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        materials=await list_material_page(
            db,
            q=q,
            limit=page_size,
            offset=(page - 1) * page_size,
        ),
        filters={"q": raw_q},
        pagination={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "q": q,
            "has_previous": page > 1,
            "has_next": page < total_pages,
            "previous_page": max(page - 1, 1),
            "next_page": min(page + 1, total_pages),
            "from_item": ((page - 1) * page_size + 1) if total else 0,
            "to_item": min(page * page_size, total),
            "ignored_short_query": bool(raw_q and not q),
        },
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
        batches=[],
        units=await list_units(db),
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
        batches=await list_material_batches(db, material.id),
        units=await list_units(db),
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


@router.get("/materials/{material_id}/batches/{batch_id}/history", response_class=HTMLResponse)
async def material_batch_history(
    material_id: int,
    batch_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    material = await get_material(db, material_id)
    batch = await get_material_batch(db, material_id=material_id, batch_id=batch_id)
    if material is None or batch is None:
        return RedirectResponse(f"{_BASE}/materials/{material_id}/edit", status_code=303)
    return await admin_render(
        "admin/com_warehouse/material_batch_history.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        material=material,
        batch=batch,
        movements=await list_material_batch_movements(
            db,
            material_id=material.id,
            batch_number=batch.batch_number,
        ),
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


@router.post("/materials/{material_id}/batches/new")
async def material_batch_new_submit(
    material_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        await create_material_batch(
            db,
            build_material_batch_payload(**{**dict(form), "material_id": material_id}),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.batch_created"))
    return RedirectResponse(f"{_BASE}/materials/{material_id}/edit", status_code=303)


@router.post("/materials/{material_id}/batches/{batch_id}/edit")
async def material_batch_edit_submit(
    material_id: int,
    batch_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    batch = await get_material_batch(db, material_id=material_id, batch_id=batch_id)
    if batch is None:
        _flash(request, "danger", ct("com_warehouse.error.batch_not_found"))
        return RedirectResponse(f"{_BASE}/materials/{material_id}/edit", status_code=303)
    form = await request.form()
    try:
        await update_material_batch(
            db,
            batch,
            build_material_batch_payload(
                **{
                    **dict(form),
                    "material_id": material_id,
                    "batch_number": batch.batch_number,
                }
            ),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.batch_updated"))
    return RedirectResponse(f"{_BASE}/materials/{material_id}/edit", status_code=303)


@router.post("/materials/import-sql")
async def material_import_sql(
    request: Request,
    user: CurrentAdminUser,
    import_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    content = await import_file.read()
    if not content:
        _flash(request, "danger", ct("com_warehouse.error.import_file_required"))
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    try:
        sql_text = content.decode("utf-8")
    except UnicodeDecodeError:
        _flash(request, "danger", ct("com_warehouse.error.import_file_invalid"))
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    try:
        result = await import_materials_from_sql_dump(
            db,
            sql_text,
        )
    except SQLAlchemyError as exc:
        await db.rollback()
        _flash(
            request,
            "danger",
            ct("com_warehouse.error.import_failed", error=str(exc.__cause__ or exc)),
        )
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    except (SyntaxError, ValueError) as exc:
        await db.rollback()
        _flash(
            request,
            "danger",
            ct("com_warehouse.error.import_failed", error=str(exc)),
        )
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    _flash(
        request,
        "success",
        ct(
            "com_warehouse.success.material_imported",
            rows=result.rows,
            created=result.created,
            updated=result.updated,
            duplicates=result.duplicate_material_rows,
            units=result.units_created,
            batches=result.batches_created,
        ),
    )
    return RedirectResponse(f"{_BASE}/materials", status_code=303)


@router.post("/materials/import-xlsx")
async def material_import_xlsx(
    request: Request,
    user: CurrentAdminUser,
    import_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    content = await import_file.read()
    if not content:
        _flash(request, "danger", ct("com_warehouse.error.import_file_required"))
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    try:
        result = await import_materials_from_xlsx_workbook(db, content)
    except SQLAlchemyError as exc:
        await db.rollback()
        _flash(
            request,
            "danger",
            ct("com_warehouse.error.import_failed", error=str(exc.__cause__ or exc)),
        )
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    except (SyntaxError, ValueError) as exc:
        await db.rollback()
        _flash(
            request,
            "danger",
            ct("com_warehouse.error.import_failed", error=str(exc)),
        )
        return RedirectResponse(f"{_BASE}/materials", status_code=303)
    _flash(
        request,
        "success",
        ct(
            "com_warehouse.success.material_imported",
            rows=result.rows,
            created=result.created,
            updated=result.updated,
            duplicates=result.duplicate_material_rows,
            units=result.units_created,
            batches=result.batches_created,
        ),
    )
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
        balance=[],
        budgets=[],
        directions=[],
        materials=[],
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
        budgets=await list_project_budgets(db, project.id),
        balance=await project_material_balance(db, project.id),
        directions=await list_project_directions(db, project.id),
        materials=await list_materials(db),
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


@router.post("/projects/{project_id}/directions/new")
async def project_direction_new_submit(
    project_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        await create_project_direction(
            db,
            build_project_direction_payload(
                **{
                    **dict(form),
                    "project_id": project_id,
                }
            ),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.direction_created"))
    return RedirectResponse(f"{_BASE}/projects/{project_id}/edit", status_code=303)


@router.post("/projects/{project_id}/directions/{direction_id}/sections/new")
async def project_budget_section_new_submit(
    project_id: int,
    direction_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        await create_project_budget_section(
            db,
            build_project_budget_section_payload(
                **{**dict(form), "direction_id": direction_id},
            ),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.budget_section_created"))
    return RedirectResponse(f"{_BASE}/projects/{project_id}/edit", status_code=303)


@router.post("/projects/{project_id}/budgets/new")
async def project_budget_new_submit(
    project_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        await create_budget(
            db,
            build_budget_payload(**{**dict(form), "project_id": project_id}),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.budget_created"))
    return RedirectResponse(f"{_BASE}/projects/{project_id}/edit", status_code=303)


@router.post("/projects/{project_id}/budgets/{budget_id}/items/new")
async def project_budget_item_new_submit(
    project_id: int,
    budget_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ct = await _ct(db)
    form = await request.form()
    try:
        await create_budget_item(
            db,
            build_budget_item_payload(**{**dict(form), "budget_id": budget_id}),
        )
    except WarehouseError as exc:
        _flash(request, "danger", ct(exc.key, **exc.kwargs))
    else:
        _flash(request, "success", ct("com_warehouse.success.budget_item_created"))
    return RedirectResponse(f"{_BASE}/projects/{project_id}/edit", status_code=303)


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
    batches = await list_material_batches(db)
    batch_groups: dict[int, list[object]] = {}
    for batch in batches:
        batch_groups.setdefault(batch.material_id, []).append(batch)
    return await admin_render(
        "admin/com_warehouse/document_form.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        document_type=document_type,
        materials=await list_materials(db),
        batches=batches,
        batch_groups=batch_groups,
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


@router.get("/documents/{document_id}/pdf", response_class=HTMLResponse)
async def document_pdf_view(
    document_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    document = await get_document(db, document_id)
    if document is None:
        return RedirectResponse(f"{_BASE}/documents", status_code=303)
    return await admin_render(
        "admin/com_warehouse/document_pdf.html",
        request=request,
        db=db,
        user=user,
        ct=await _ct(db),
        document=document,
    )


@router.get("/documents/{document_id}/pdf-file")
async def document_pdf_file(
    document_id: int,
    request: Request,
    user: CurrentAdminUser,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    document = await get_document(db, document_id)
    if document is None:
        return RedirectResponse(f"{_BASE}/documents", status_code=303)
    ct = await _ct(db)
    filename = f"{document.number}.pdf"
    return Response(
        content=document_pdf_bytes(
            document,
            labels={
                "title": ct(f"com_warehouse.document_type.{document.document_type}"),
                "date": ct("com_warehouse.col.date"),
                "warehouse": ct("com_warehouse.col.warehouse"),
                "project": ct("com_warehouse.col.project"),
                "partner": ct("com_warehouse.col.partner"),
                "reference": ct("com_warehouse.col.reference"),
                "items": ct("com_warehouse.section.items"),
                "item_header": (
                    f"{ct('com_warehouse.col.sku')} / {ct('com_warehouse.col.material')} / "
                    f"{ct('com_warehouse.col.batch')} / {ct('com_warehouse.col.quantity')}"
                ),
                "notes": ct("com_warehouse.col.notes"),
            },
        ),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
