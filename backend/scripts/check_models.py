import sys, os
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.repository.server_catalog_repo import ServerCatalogRepository
repo = ServerCatalogRepository()
try:
    ms = repo.list_models(published_only=True)
    print("published model count:", len(ms))
    for m in ms:
        n = m.get("name") or ""
        if "ES22" in n or "WA5480" in n or "ES22V3" in n:
            print("MATCH:", n, "| id=", m.get("id"), "| type_id=", m.get("server_type_id"),
                  "| base_config series=", (m.get("base_config") or {}).get("series"),
                  "| form=", (m.get("base_config") or {}).get("form"))
    print("--- sample names ---")
    for m in ms[:12]:
        print(" ", m.get("name"), "series=", (m.get("base_config") or {}).get("series"), "form=", (m.get("base_config") or {}).get("form"))
finally:
    repo.close()
