from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from textwrap import shorten
from unicodedata import normalize

from .models import StockDocument


def _ascii(value: object) -> str:
    text = normalize("NFKD", str(value or ""))
    return text.encode("ascii", "ignore").decode("ascii")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}"


def document_pdf_bytes(document: StockDocument, labels: dict[str, str] | None = None) -> bytes:
    labels = labels or {}
    title = labels.get("title", document.document_type)
    lines = [
        f"{title}: {document.number}",
        f"{labels.get('date', 'Date')}: {document.issued_at.strftime('%d.%m.%Y %H:%M')}",
        f"{labels.get('warehouse', 'Warehouse')}: {document.warehouse.name}",
        f"{labels.get('project', 'Project')}: {document.project.name if document.project else '-'}",
        f"{labels.get('partner', 'Partner')}: {document.partner or '-'}",
        f"{labels.get('reference', 'Reference')}: {document.reference or '-'}",
        "",
        labels.get("items", "Items"),
        labels.get(
            "item_header",
            "ID / Code       Name                                      Batch        Quantity",
        ),
    ]
    for item in document.items:
        unit = item.material.unit_ref.code if item.material.unit_ref else item.material.unit
        name = shorten(_ascii(item.material.name), width=40, placeholder="...")
        sku = shorten(_ascii(item.material.sku), width=14, placeholder="")
        batch = shorten(_ascii(item.batch_number or "-"), width=12, placeholder="")
        lines.append(f"{sku:<14} {name:<40} {batch:<12} {_qty(item.quantity)} {unit}")
    if document.notes:
        lines.extend(["", f"{labels.get('notes', 'Notes')}:", _ascii(document.notes)])
    return _build_pdf(lines)


def _build_pdf(lines: list[str]) -> bytes:
    page_lines = [lines[index : index + 42] for index in range(0, len(lines), 42)] or [[]]
    objects: list[bytes] = []
    page_ids: list[int] = []

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page in page_lines:
        content = _page_content(page)
        content_id = len(objects) + 1
        objects.append(
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
        page_id = len(objects) + 1
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode("ascii"))
        output.write(obj)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return output.getvalue()


def _page_content(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(_ascii(line))}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("ascii")
