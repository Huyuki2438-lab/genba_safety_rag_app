from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from backend.app.core.config import settings


BASE_DIR = settings.BASE_DIR
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_CSS_PATH = BASE_DIR / "static" / "pdf.css"

PRINT_BASE_CSS = """
@page {
  size: A4;
  margin: 10mm;
}

html,
body {
  width: 100%;
}

body {
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

@media print {
  body {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
""".strip()

jinja_env = Environment(
  loader=FileSystemLoader(str(TEMPLATES_DIR.resolve())),
  autoescape=select_autoescape(["html", "xml"]),
)


def _load_inline_css() -> str:
  css_parts = [PRINT_BASE_CSS]
  if STATIC_CSS_PATH.is_file():
    css_parts.append(STATIC_CSS_PATH.read_text(encoding="utf-8"))
  return "\n\n".join(css_parts)


def _inject_inline_css(rendered_html: str, css_text: str) -> str:
  style_tag = (
    "<style media=\"all\">\n"
    f"{css_text}\n"
    "</style>\n"
    "<style media=\"print\">\n"
    f"{css_text}\n"
    "</style>"
  )

  if "</head>" in rendered_html:
    return rendered_html.replace("</head>", f"{style_tag}</head>", 1)

  return (
    "<!doctype html>"
    "<html><head><meta charset=\"utf-8\">"
    f"{style_tag}"
    "</head><body>"
    f"{rendered_html}"
    "</body></html>"
  )


def render_template(template_name: str, context: dict[str, object] | None = None) -> str:
  try:
    template = jinja_env.get_template(template_name)
  except TemplateNotFound as exc:
    raise HTTPException(status_code=404, detail=f"Template not found: {template_name}") from exc

  return template.render(**(context or {}))


def render_template_for_pdf(template_name: str, context: dict[str, object] | None = None) -> str:
  rendered_html = render_template(template_name, context)
  return _inject_inline_css(rendered_html, _load_inline_css())
