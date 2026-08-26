import io, os
p = os.path.join(r"D:\CPQ_Platform_V1", "backend", "app", "services", "requirement_rule_catalog.py")
with io.open(p, "r", encoding="utf-8") as f:
    s = f.read()
anchor = "def platform_series_map(enabled_types: Optional[list[str]] = None) -> list[dict]:"
insert = (
    "\n\n# 部件家族 → 关键词（用于功耗/负载粗估；可被 power_calibration.part_family_keywords 覆盖。\n"
    "# 数据落在规则库（默认值 + 规则覆盖），candidate_search 只读不内联。)\n"
    "DEFAULT_PART_FAMILY_KEYWORDS: dict[str, dict[str, list[str]]] = {\n"
    "    \"cpu\": {\"cat_upper\": [\"CPU\"]},\n"
    "    \"memory\": {\"cat_upper\": [\"MEM\"], \"cat\": [\"内存\"]},\n"
    "    \"nvme\": {\"name_upper\": [\"NVME\"]},\n"
    "    \"disk\": {\"cat\": [\"硬盘\", \"SSD\", \"HDD\", \"DISK\", \"盘\"]},\n"
    "    \"nic\": {\"cat_upper\": [\"NIC\", \"NETWORK\"], \"cat\": [\"网卡\"]},\n"
    "    \"raid\": {\"cat_upper\": [\"RAID\", \"HBA\"], \"cat\": [\"阵列\"]},\n"
    "    \"sata\": {\"name_upper\": [\"SATA\"]},\n"
    "    \"sas\": {\"name_upper\": [\"SAS\"]},\n"
    "}\n\n\n"
    "def part_family_keywords(enabled_types: Optional[list[str]] = None) -> dict[str, dict[str, list[str]]]:\n"
    "    \"\"\"部件家族关键词（默认值 + 规则/配置覆盖，后者覆盖前者）。\"\"\"\n"
    "    out = {k: {kk: list(vv) for kk, vv in v.items()} for k, v in DEFAULT_PART_FAMILY_KEYWORDS.items()}\n"
    "    for row in active_bodies(\"power_calibration\", enabled_types):\n"
    "        if isinstance(row, dict) and isinstance(row.get(\"part_family_keywords\"), dict):\n"
    "            pfm = row[\"part_family_keywords\"]\n"
    "            for fam, kws in pfm.items():\n"
    "                if isinstance(kws, dict):\n"
    "                    out[str(fam)] = {str(k): [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in kws.items() if k in (\"cat_upper\", \"cat\", \"name_upper\")}\n"
    "    return out\n")
assert anchor in s, "anchor not found"
s = s.replace(anchor, insert + anchor, 1)
with io.open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)
print("inserted part_family_keywords")
