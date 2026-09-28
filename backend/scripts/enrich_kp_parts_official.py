"""用厂商官网/官方规格页补全 KP 配件规格。

原则：只补高置信度字段；已存在的同名字段不覆盖。
默认 dry-run，加 --apply 才写库，并在写库前创建独立备份表。
"""
from __future__ import annotations

import argparse
from datetime import datetime

import psycopg2
from _localdb import db_password  # 2026-09-14 安全加固：密码不再硬编码


DSN = {
    "host": "localhost",
    "dbname": "cpq_platform",
    "user": "postgres",
    "password": db_password(),
}


# part_id -> [(spec_key, spec_value), ...]
OFFICIAL_SPECS: dict[int, list[tuple[str, str]]] = {
    # NVIDIA RTX 5090 系列，参考 NVIDIA 官方 RTX 5090 规格。
    291: [
        ("Architecture", "Blackwell"),
        ("Boost Clock", "2.41 GHz"),
        ("Capacity", "32 GB"),
        ("CUDA Cores", "21760"),
        ("Cooling", "Blower"),
        ("Form Factor", "2-Slot"),
        ("Interface", "PCI Express Gen 5"),
        ("Memory Bandwidth", "1792 GB/sec"),
        ("Memory Interface", "512-bit"),
        ("tdp", "575"),
    ],
    335: [
        ("Architecture", "Blackwell"),
        ("Boost Clock", "2.41 GHz"),
        ("Capacity", "32 GB"),
        ("CUDA Cores", "21760"),
        ("Cooling", "Blower"),
        ("Form Factor", "2-Slot"),
        ("Interface", "PCI Express Gen 5"),
        ("Memory Bandwidth", "1792 GB/sec"),
        ("Memory Interface", "512-bit"),
        ("tdp", "575"),
    ],
    356: [
        ("Architecture", "Blackwell"),
        ("Boost Clock", "2.41 GHz"),
        ("Capacity", "32 GB"),
        ("CUDA Cores", "21760"),
        ("Form Factor", "2-Slot"),
        ("Interface", "PCI Express Gen 5"),
        ("Memory Bandwidth", "1792 GB/sec"),
        ("Memory Interface", "512-bit"),
        ("tdp", "575"),
    ],
    380: [
        ("Architecture", "Blackwell"),
        ("Boost Clock", "2.41 GHz"),
        ("Capacity", "32 GB"),
        ("CUDA Cores", "21760"),
        ("Cooling", "Blower"),
        ("Form Factor", "2-Slot"),
        ("Interface", "PCI Express Gen 5"),
        ("Memory Bandwidth", "1792 GB/sec"),
        ("Memory Interface", "512-bit"),
        ("tdp", "575"),
    ],
    # NVIDIA RTX PRO 6000 Blackwell，参考 NVIDIA 官方规格。
    280: [
        ("Architecture", "Blackwell"),
        ("Capacity", "96 GB"),
        ("Form Factor", '5.4" H x 12.0" L, dual slot'),
        ("Interface", "PCIe 5.0 x16"),
        ("Memory Bandwidth", "1792 GB/sec"),
        ("tdp", "600"),
    ],
    332: [
        ("Architecture", "Blackwell"),
        ("Capacity", "96 GB"),
        ("Form Factor", '5.4" H x 12.0" L, dual slot'),
        ("Interface", "PCIe 5.0 x16"),
        ("Memory Bandwidth", "1792 GB/sec"),
        ("tdp", "600"),
    ],
    # NVIDIA L20，参考 NVIDIA 官方 L20 规格。
    343: [
        ("Architecture", "Ada Lovelace"),
        ("Capacity", "48 GB"),
        ("Interface", "PCIe Gen4 x16"),
        ("Memory Bandwidth", "864 GB/s"),
        ("tdp", "275"),
    ],
    # AMD Radeon PRO W7900 Dual Slot，参考 AMD 官方规格。
    372: [
        ("Architecture", "RDNA3"),
        ("Capacity", "48 GB"),
        ("Compute Units", "96"),
        ("Cooling", "Active"),
        ("Interface", "PCIe 4.0 x16"),
        ("Memory Bandwidth", "864 GB/s"),
        ("Memory Interface", "384-bit"),
        ("tdp", "295"),
    ],
    # AMD Radeon PRO R9700，参考 AMD 官方规格。
    274: [
        ("Architecture", "RDNA4"),
        ("Boost Clock", "Up to 2920 MHz"),
        ("Capacity", "32 GB GDDR6"),
        ("Compute Units", "64"),
        ("Cooling", "Active"),
        ("Interface", "PCIe 5.0 x16"),
        ("Memory Bandwidth", "640 GB/s"),
        ("Memory Interface", "256-bit"),
        ("tdp", "300"),
    ],
    # AMD EPYC 9575F，参考 AMD 官方产品页。
    376: [
        ("Architecture", "Zen 5"),
        ("Threads", "128"),
        ("Memory Support", "DDR5-6400 12-channel"),
        ("Socket", "SP5"),
        ("tdp", "400"),
    ],
    # Intel Xeon Gold 6544Y，参考 Intel ARK 官方规格。
    385: [
        ("Architecture", "Emerald Rapids"),
        ("Cores", "16"),
        ("Threads", "32"),
        ("Base Clock", "3.6 GHz"),
        ("Boost Clock", "4.1 GHz"),
        ("L3 Cache", "45 MB"),
        ("Memory Support", "DDR5-5200 8-channel"),
        ("Socket", "LGA 4677"),
        ("tdp", "270"),
    ],
}


OFFICIAL_DATASHEET_URLS = {
    274: "https://www.amd.com/en/products/professional-graphics/amd-radeon-pro-r9700",
    280: "https://www.nvidia.com/en-us/design-visualization/rtx-pro-6000/",
    291: "https://www.nvidia.com/en-us/geforce/graphics-cards/rtx-5090/",
    332: "https://www.nvidia.com/en-us/design-visualization/rtx-pro-6000/",
    335: "https://www.nvidia.com/en-us/geforce/graphics-cards/rtx-5090/",
    343: "https://www.nvidia.com/en-us/data-center/l20/",
    356: "https://www.nvidia.com/en-us/geforce/graphics-cards/rtx-5090/",
    372: "https://www.amd.com/en/products/professional-graphics/amd-radeon-pro-w7900-dual-slot",
    376: "https://www.amd.com/en/products/processors/server/epyc/9005-series/amd-epyc-9575f.html",
    380: "https://www.nvidia.com/en-us/geforce/graphics-cards/rtx-5090/",
    385: "https://ark.intel.com/content/www/us/en/ark/products/237893/intel-xeon-6544y-processor-160m-cache-2-10-ghz.html",
}


def backup_official(cur) -> None:
    for backup_table, source_table in [
        ("kp.kp_parts_bak_official_20260912", "kp.kp_parts"),
        ("kp.kp_part_specs_bak_official_20260912", "kp.kp_part_specs"),
    ]:
        cur.execute(f"drop table if exists {backup_table}")
        cur.execute(f"create table {backup_table} as select * from {source_table}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    try:
        rows = []
        for part_id, specs in sorted(OFFICIAL_SPECS.items()):
            rows.append((part_id, specs))
            print(f"{part_id}: {len(specs)} 条官网规格")
            for key, value in specs:
                print(f"    {key} = {value}")

        if not args.apply:
            print("DRY-RUN，未写库。")
            conn.rollback()
            return 0

        backup_official(cur)
        print("已创建备份表: kp.kp_parts_bak_official_20260912 / kp.kp_part_specs_bak_official_20260912")

        for part_id, specs in rows:
            for key, value in specs:
                cur.execute(
                    """
                    insert into kp.kp_part_specs (part_id, spec_key, spec_value, sort_order)
                    values (%s, %s, %s, 0)
                    on conflict (part_id, spec_key) do nothing
                    """,
                    (part_id, key, value),
                )
            url = OFFICIAL_DATASHEET_URLS.get(part_id)
            if url:
                cur.execute(
                    "update kp.kp_parts set datasheet_url = %s, updated_at = %s where id = %s and (datasheet_url is null or datasheet_url = '')",
                    (url, datetime.now(), part_id),
                )
        conn.commit()
        print("已提交官网规格。")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
