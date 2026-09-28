from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils.safestring import mark_safe


@dataclass(frozen=True)
class ManualDefinition:
    key: str
    title: str
    description: str
    filename: str


MANUALS = (
    ManualDefinition(
        key="operativo",
        title="Manual operativo",
        description="Vista general del sistema para empresa, DPD y personal autorizado.",
        filename="manual_propietario_empresa.md",
    ),
    ManualDefinition(
        key="acceso",
        title="Acceso delegada",
        description="Ingreso, MFA, usuarios principales y recuperación de acceso.",
        filename="manual_acceso_delegada.md",
    ),
    ManualDefinition(
        key="solicitudes",
        title="Solicitudes",
        description="Revisión y atención de expedientes de derechos.",
        filename="manual_revision_solicitudes.md",
    ),
    ManualDefinition(
        key="usuarios",
        title="Usuarios",
        description="Creación, roles, bloqueo, activación y segundo factor.",
        filename="manual_usuarios.md",
    ),
    ManualDefinition(
        key="configuracion",
        title="Configuración",
        description="Identidad institucional, canales, responsables y marca.",
        filename="manual_configuracion_sistema.md",
    ),
    ManualDefinition(
        key="avisos",
        title="Contenido legal",
        description="Manejo de avisos, políticas, borradores y publicaciones.",
        filename="manual_contenido_avisos.md",
    ),
    ManualDefinition(
        key="comunicaciones",
        title="Comunicaciones",
        description="Registro y seguimiento de comunicaciones por expediente.",
        filename="manual_comunicaciones.md",
    ),
    ManualDefinition(
        key="evidencias",
        title="Evidencias",
        description="Verificación de identidad, documentos adjuntos y soportes.",
        filename="manual_evidencias.md",
    ),
)


MANUALS_BY_KEY = {manual.key: manual for manual in MANUALS}


def get_manual(key: str | None) -> ManualDefinition:
    if key and key in MANUALS_BY_KEY:
        return MANUALS_BY_KEY[key]
    return MANUALS[0]


def _manual_path(manual: ManualDefinition) -> Path:
    return Path(settings.BASE_DIR) / "docs" / manual.filename


def read_manual_markdown(manual: ManualDefinition) -> str:
    path = _manual_path(manual)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return (
            f"# {manual.title}\n\n"
            "El contenido de este manual no está disponible en este momento."
        )


def _inline(value: str) -> str:
    value = html.escape(value.strip())
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(
        cell and set(cell) <= {"-", ":"}
        for cell in cells
    )


def _table_cells(line: str) -> list[str]:
    return [
        _inline(cell)
        for cell in line.strip().strip("|").split("|")
    ]


def _render_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = rows[0]
    body = rows[1:]
    header_html = "".join(f"<th>{cell}</th>" for cell in head)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return (
        '<div class="manual-table-wrap"><table class="table manual-table">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody></table></div>"
    )


def render_manual_markdown(markdown: str):
    html_parts: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    table_rows: list[list[str]] = []
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            html_parts.append(
                "<p>" + " ".join(_inline(item) for item in paragraph) + "</p>"
            )
            paragraph = []

    def close_list():
        nonlocal list_type
        if list_type:
            html_parts.append(f"</{list_type}>")
            list_type = None

    def flush_table():
        nonlocal table_rows
        if table_rows:
            html_parts.append(_render_table(table_rows))
            table_rows = []

    def close_blocks():
        flush_paragraph()
        flush_table()
        close_list()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            flush_paragraph()
            flush_table()
            close_list()
            if in_code:
                html_parts.append(
                    "<pre><code>"
                    + html.escape("\n".join(code_lines))
                    + "</code></pre>"
                )
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            close_blocks()
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading_match:
            close_blocks()
            level = min(len(heading_match.group(1)) + 1, 5)
            html_parts.append(
                f"<h{level}>{_inline(heading_match.group(2))}</h{level}>"
            )
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            close_list()
            if not _is_table_separator(stripped):
                table_rows.append(_table_cells(stripped))
            continue

        flush_table()

        unordered_match = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if unordered_match or ordered_match:
            flush_paragraph()
            desired_list = "ul" if unordered_match else "ol"
            if list_type != desired_list:
                close_list()
                html_parts.append(f"<{desired_list}>")
                list_type = desired_list
            item = unordered_match.group(1) if unordered_match else ordered_match.group(1)
            html_parts.append(f"<li>{_inline(item)}</li>")
            continue

        close_list()
        paragraph.append(stripped)

    if in_code:
        html_parts.append(
            "<pre><code>"
            + html.escape("\n".join(code_lines))
            + "</code></pre>"
        )
    close_blocks()
    return mark_safe("\n".join(html_parts))
