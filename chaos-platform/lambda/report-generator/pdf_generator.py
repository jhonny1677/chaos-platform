"""
PDFGenerator — Converts an HTML string to PDF bytes using WeasyPrint.

WeasyPrint is a Python library that renders HTML/CSS to PDF using the Pango/Cairo
rendering pipeline. It produces significantly better output than wkhtmltopdf for
dark-themed reports with tables and does not require a running browser process.

Lambda deployment note:
  WeasyPrint requires system libraries (libpango, libcairo, libgdk-pixbuf).
  These are provided by the Lambda layer defined in the Terraform configuration.
  The layer is built from the `lambda-weasyprint` layer ARN which packages the
  required shared libraries for the Amazon Linux 2023 runtime environment.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PDFGenerator:
    def to_pdf(self, html_string: str) -> bytes:
        """
        Render HTML to PDF and return the raw PDF bytes.
        Raises RuntimeError if WeasyPrint is unavailable (e.g. local dev without the layer).
        """
        try:
            from weasyprint import HTML, CSS  # type: ignore[import]
            from weasyprint.text.fonts import FontConfiguration  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "WeasyPrint is not available. "
                "Ensure the Lambda layer is attached or run `pip install weasyprint` locally."
            ) from exc

        logger.info("Rendering HTML to PDF (%d chars)", len(html_string))

        font_config = FontConfiguration()
        base_css = CSS(
            string="""
            @page {
                size: A4;
                margin: 20mm;
            }
            body {
                font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
                font-size: 11pt;
                line-height: 1.5;
            }
            table { border-collapse: collapse; width: 100%; }
            th, td { padding: 6pt; }
            pre { white-space: pre-wrap; word-break: break-all; }
            """,
            font_config=font_config,
        )

        document = HTML(string=html_string).render(
            stylesheets=[base_css],
            font_config=font_config,
            presentational_hints=True,
        )

        pdf_bytes = document.write_pdf()
        logger.info("PDF generated: %d bytes", len(pdf_bytes))
        return pdf_bytes
