# Plan: HTML Export + Browser Print (replaces WeasyPrint PDF)

Branch: `feature/html-export-report`
Based on: PR #188 approach, replacing `django-weasyprint` with a zero-dependency HTML endpoint.

---

## Why

WeasyPrint requires Cairo, Pango, and GLib as system packages, adds ~50 MB to the container image, and
can take 5–30 s per document. An HTML endpoint uses Django's template renderer (already in use), responds
in < 300 ms, and relies on the browser's native print-to-PDF — which already supports all the CSS in the
existing templates (`@page`, `break-inside: avoid`, `thead { display: table-header-group }`).

---

## Files to copy from PR #188 unchanged

These static assets and templates can be taken directly from PR #188 — no modifications needed:

```
apps/dashboard_reports/static/dashboard_reports/fonts/RedHatDisplay/RedHatDisplayVF-Italic.woff2
apps/dashboard_reports/static/dashboard_reports/fonts/RedHatDisplay/RedHatDisplayVF.woff2
apps/dashboard_reports/static/dashboard_reports/fonts/RedHatText/RedHatTextVF-Italic.woff2
apps/dashboard_reports/static/dashboard_reports/fonts/RedHatText/RedHatTextVF.woff2
apps/dashboard_reports/static/dashboard_reports/images/RedHatLogo.svg
apps/dashboard_reports/static/dashboard_reports/images/fa-arrow-circle-down-green.svg
apps/dashboard_reports/static/dashboard_reports/images/fa-arrow-circle-down-red.svg
apps/dashboard_reports/static/dashboard_reports/images/fa-arrow-circle-up-green.svg
apps/dashboard_reports/static/dashboard_reports/images/fa-arrow-circle-up-red.svg
apps/dashboard_reports/static/dashboard_reports/images/fa-minus-circle.svg
apps/dashboard_reports/templates/dashboard_reports/report_summary.html
apps/dashboard_reports/templates/dashboard_reports/report_roi.html
apps/dashboard_reports/templates/dashboard_reports/report_trends.html
```

---

## Files to create/modify (differ from PR #188)

### 1. `pyproject.toml` — NO change needed

Do **not** add `django-weasyprint`. No new Python dependency at all.

---

### 2. `apps/dashboard_reports/static/dashboard_reports/styles/style.css`

Take the file from PR #188, then apply these browser-print compatibility fixes:

**Problem:** `position: running(header)` and `content: element(header)` are CSS Paged Media Level 3
features that only WeasyPrint/Prince support. Browsers ignore them.

**Problem:** `counter(pages)` (total page count) is not reliably supported in browsers.

**Changes:**

```css
/* REMOVE from @page block: */
@top-center {
  content: element(header);
}

/* REMOVE from @page block: */
@bottom-center {
  content: counter(page) " of " counter(pages);
  ...
}

/* CHANGE header rule from: */
header {
  position: running(header);
  ...
}

/* TO — browser-compatible fixed header for print: */
header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  background: #151515;
  padding: 5mm 10mm;
  /* keep margin overrides from original */
}

/* ADD — push body content below the fixed header */
body {
  margin-top: 30mm;   /* match header height so content doesn't slide under it */
}

/* ADD — hide the print button when printing */
@media print {
  .no-print {
    display: none !important;
  }
}
```

The browser will repeat the fixed-position header element on every page when printing. The `@page`
margin/size rules still work — keep those as-is.

---

### 3. `apps/dashboard_reports/templates/dashboard_reports/base.html`

Take the file from PR #188 and add:
1. A "Print to PDF" button visible on screen, hidden when printing.
2. A `<script>` block that injects the real page total into a footer span (browsers don't support
   `counter(pages)`, but JS can count page breaks after layout).

```html
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <link rel="stylesheet" href="{% static 'dashboard_reports/styles/style.css' %}">
  <title>Automation Dashboard Report</title>
</head>
<body>
<header>
  <img src="{% static 'dashboard_reports/images/RedHatLogo.svg' %}" alt="Red Hat logo" />
</header>

<!-- Print button — hidden when printing via .no-print class -->
<div class="no-print" style="padding: 12px 10mm; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
  <button onclick="window.print()"
          style="padding: 8px 16px; font-size: 13px; cursor: pointer; background: #06c; color: #fff;
                 border: none; border-radius: 4px;">
    Print / Save as PDF
  </button>
</div>

<div class="content">
  {% block content %}
  {% endblock %}
</div>

<!-- Page footer rendered by browser print CSS, no JS needed for page number -->
</body>
</html>
```

---

### 4. `apps/dashboard_reports/viewsets/dashboard_report.py`

#### 4a. Imports — remove WeasyPrint, no new imports needed

```python
# REMOVE:
from django_weasyprint.views import WeasyTemplateResponse

# ADD (already available in Django):
from django.template.loader import render_to_string
```

#### 4b. `make_passthrough_renderer` — keep the PR #188 refactor

```python
def make_passthrough_renderer(media_type: str, fmt: str) -> type:
    return type(
        "PassthroughRenderer",
        (BaseRenderer,),
        {"media_type": media_type, "format": fmt, "render": lambda self, data, *a, **kw: data},
    )

PassthroughRenderer = make_passthrough_renderer(media_type="text/csv", fmt="csv")
PassthroughRendererHTML = make_passthrough_renderer(media_type="text/html", fmt="html")
# (not PassthroughRendererPDF — that's the PR #188 version)
```

#### 4c. Class constant

```python
# Rename MAX_PDF_JOB_TEMPLATES → MAX_HTML_JOB_TEMPLATES (or keep name, update comment)
MAX_HTML_JOB_TEMPLATES = 50
```

#### 4d. `_build_filter_labels` — copy exactly from PR #188, no changes

#### 4e. Context-building methods — rename `_build_pdf_*` → `_build_html_*`, same logic, different return

```python
# INSTEAD OF returning WeasyTemplateResponse:
return WeasyTemplateResponse(request, template=..., context=context, filename=filename, headers=...)

# RETURN a plain HttpResponse with rendered HTML:
html = render_to_string(template_name, context, request=request)
return HttpResponse(html, content_type="text/html; charset=UTF-8")
```

No `Content-Disposition` header — the browser opens it inline, user uses the print button.

Three methods to add:
- `_build_html_summary(self, request) -> HttpResponse`
- `_build_html_roi(self, request) -> HttpResponse`
- `_build_html_trends(self, request) -> HttpResponse`

#### 4f. `_export_csv` helper — copy exactly from PR #188

#### 4g. `_export_html` dispatcher — rename from `_export_pdf`

```python
def _export_html(self, request: Request, report_type: str) -> HttpResponse | JsonResponse:
    if report_type == "summary":
        return self._build_html_summary(request)
    if report_type == "roi":
        return self._build_html_roi(request)
    if report_type == "trends":
        return self._build_html_trends(request)
    return JsonResponse({"detail": "Something went wrong."}, status=400)
```

#### 4h. OpenAPI schema for export action

```python
# enum changes:
enum=["csv", "html"],
description="Export file format. Options: 'csv', 'html'.",

# responses:
(200, "text/csv; charset=UTF-8"): str,
(200, "text/html; charset=UTF-8"): str,   # replaces application/pdf
```

#### 4i. `export` action — `renderer_classes` and body

```python
@action(
    methods=["get"],
    detail=False,
    url_path="export",
    renderer_classes=[PassthroughRenderer, PassthroughRendererHTML],  # not PDF
)
@require_date_range
def export(self, request, *args, **kwargs):
    report_type = request.query_params.get("report_type", "summary")
    export_format = request.query_params.get("export_format", "csv")

    if export_format not in ("csv", "html"):
        return JsonResponse(
            {"detail": f"Invalid export format: {export_format}. Must be one of: csv, html."},
            status=400,
        )
    if report_type not in ("summary", "roi", "trends"):
        return JsonResponse(
            {"detail": f"Invalid report_type: {report_type}. Must be one of: summary, roi, trends."},
            status=400,
        )

    end_date = self.kwargs.get("end_date")
    filename = f"automation-dashboard-{report_type}-{end_date.date().isoformat()}"
    base_qs = self._filter_raw_jobdata_queryset(JobData.objects.all())
    qs = self.filter_queryset(self._build_aggregated_queryset(base_qs))

    if export_format == "csv":
        return self._export_csv(request, report_type, filename, base_qs, qs)
    if export_format == "html":
        return self._export_html(request, report_type)

    return JsonResponse({"detail": "Something went wrong."}, status=400)
```

---

### 5. Tests

#### `tests/unit/dashboard_reports/test_export_html_urls.py` (new, replaces `test_export_pdf_urls.py`)

The unit tests from PR #188 mock `WeasyTemplateResponse`. The HTML version doesn't need mocking at all
— `render_to_string` works fine in tests without a running web server.

Key changes vs the PDF test file:
- Remove all `patch("...WeasyTemplateResponse", ...)` mocks
- Change `export_format=pdf` → `export_format=html`
- Assert `Content-Type: text/html` instead of `application/pdf`
- No `Content-Disposition: attachment` check (HTML opens inline)
- The response body will be real rendered HTML — can assert `b"<html"` in `response.content`

#### `tests/integration/dashboard_reports/test_export_html_urls.py` (new)

Same structural changes as unit tests. Integration tests also no longer need WeasyPrint mocking.

#### `tests/integration/dashboard_reports/test_export_urls.py`
#### `tests/unit/dashboard_reports/test_export_urls.py`

Update the CSV export tests that now validate `export_format` only accepts `csv` and `html` (not `pdf`).

---

### 6. OpenAPI schema files

```
tools/openapi-schema/metrics-service.json
tools/openapi-schema/metrics-service.yaml
```

These are auto-generated. Regenerate after implementing:

```bash
uv run python manage.py spectacular --file tools/openapi-schema/metrics-service.yaml
# then convert yaml → json if needed
```

---

## Implementation order

1. Copy static assets and templates from PR #188 (`git cherry-pick` or manual copy)
2. Apply CSS browser-compat fixes + base.html print button
3. Modify viewset (imports → renderers → context methods → export action)
4. Write tests
5. Regenerate OpenAPI schema
6. `uv run poe check` to verify lint + unit tests pass

---

## What is NOT needed (vs PR #188)

| PR #188 item | Status in this branch |
|---|---|
| `django-weasyprint>=2.5.0` in pyproject.toml | **Drop** |
| `WeasyTemplateResponse` import | **Drop** |
| `PassthroughRendererPDF` | **Replace with `PassthroughRendererHTML`** |
| `POST /export/` for PDF | **Never added** — stays GET-only |
| WeasyPrint mocks in tests | **Drop** — no mocking needed |
| `MAX_PDF_JOB_TEMPLATES` name | **Rename** to `MAX_HTML_JOB_TEMPLATES` |

---

## Expected API behaviour after this change

```
GET /api/v1/dashboard_reports/report/export/?period=last_30_days&tz=UTC&report_type=summary&export_format=html
→ 200 text/html; charset=UTF-8
   Body: full rendered HTML page with print button
   Response time: < 300 ms

GET /api/v1/dashboard_reports/report/export/?...&export_format=csv
→ 200 text/csv (unchanged)

GET /api/v1/dashboard_reports/report/export/?...&export_format=pdf
→ 400 { "detail": "Invalid export format: pdf. Must be one of: csv, html." }
```
