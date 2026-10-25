---
name: template-json-opaque-blob
description: template_json is an opaque JSON blob in the backend; frontend-only CellBinding fields round-trip with no backend change
metadata: 
  node_type: memory
  type: project
  originSessionId: 5ee965ff-4ccf-48b8-a0c5-dc70366cfe56
---

`ExportTemplate.template_json` is stored in the backend as an **opaque JSON blob** — a `Text` column (`backend/app/models/export_template.py`), serialized with `json.dumps` / `json.loads` (`backend/app/repository/export_template_repo.py`), and the API request bodies declare `template_json` as a bare `dict` (`backend/app/api/export_templates.py`, `TemplateCreateRequest`/`TemplateUpdateRequest`). There is **no** Pydantic model for `CellBinding` / `TemplatePartData` anywhere in the backend — those are frontend-only concepts (`frontend/src/types/template.ts`).

**Why:** It's tempting to assume a strict schema would strip unknown keys. It doesn't — no `extra="ignore"/"forbid"` validation touches the inner keys.

**How to apply:** Adding an OPTIONAL field to a frontend `CellBinding` (e.g. `availableFields`, `availableMaxColumn`, added 2026-07-11 for the config_summary whitelist feature) round-trips through save→reload automatically with **zero backend change**. The pricing engine reads individual keys via `.get()` and ignores ones it doesn't use. (Minor: the `list` endpoint's `to_dict(include_buffer=False)` only pops `fileBuffer` from cover/config_sheet — it does not touch `bindings[]`.) Related: [[docs-code-drift]].
