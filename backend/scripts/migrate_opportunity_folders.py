#!/usr/bin/env python3
"""
迁移脚本：重命名商机存储文件夹，加入客户名前缀

旧格式: storage/opportunities/OPP-xxx/文件.xlsx
新格式: storage/opportunities/客户名_OPP-xxx/文件.xlsx

运行方式:
    cd backend && python -m scripts.migrate_opportunity_folders [--dry-run]
"""
import sys
import os
from pathlib import Path

# 添加 backend 到 path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import argparse


def get_db_session():
    """获取数据库 session"""
    from app.models.base import Opportunity_SessionLocal
    return Opportunity_SessionLocal()


def sanitize_customer_name(name: str) -> str:
    """清理客户名用于文件夹命名"""
    import re
    if not name:
        return "未命名"
    # Keep: letters, digits, CJK, spaces, parentheses, brackets, dash, underscore
    cleaned = re.sub(r"[^\w一-鿿\s()\[\]\-_]", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_ ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned[:50]
    return cleaned or "未命名"


def migrate(dry_run: bool = False):
    """执行迁移"""
    from app.models.opportunity import Opportunity
    from app.models.feed_attachment import FeedAttachment
    from app.services.storage_adapter import get_storage

    session = get_db_session()
    storage = get_storage()

    try:
        # 获取所有商机
        opportunities = session.query(Opportunity).filter(
            Opportunity.status != "deleted"
        ).all()

        print(f"找到 {len(opportunities)} 个商机")

        migrated_count = 0
        skipped_count = 0
        error_count = 0

        for opp in opportunities:
            opp_id = opp.opportunity_id
            customer_name = opp.customer_name or ""

            # 构建新旧文件夹名
            old_folder = opp_id  # 旧格式: OPP-xxx
            new_folder = f"{sanitize_customer_name(customer_name)}_{opp_id}"

            old_path = storage.base_path / "opportunities" / old_folder
            new_path = storage.base_path / "opportunities" / new_folder

            # 检查旧文件夹是否存在
            if not old_path.exists():
                # 可能已经迁移过，检查新路径
                if new_path.exists():
                    print(f"[SKIP] {opp_id}: 已迁移 ({new_folder})")
                    skipped_count += 1
                else:
                    print(f"[INFO] {opp_id}: 无存储文件夹")
                    skipped_count += 1
                continue

            # 检查新路径是否已存在
            if new_path.exists():
                print(f"[WARN] {opp_id}: 新文件夹已存在，跳过 ({new_folder})")
                skipped_count += 1
                continue

            if dry_run:
                print(f"[DRY-RUN] {opp_id}: {old_folder} -> {new_folder}")
                migrated_count += 1
            else:
                try:
                    # 重命名文件夹
                    import shutil
                    shutil.move(str(old_path), str(new_path))
                    print(f"[OK] {opp_id}: {old_folder} -> {new_folder}")

                    # 更新数据库中的 storage_key
                    old_prefix = f"opportunities/{old_folder}"
                    new_prefix = f"opportunities/{new_folder}"

                    attachments = session.query(FeedAttachment).filter(
                        FeedAttachment.opportunity_id == opp_id,
                        FeedAttachment.deleted_at.is_(None)
                    ).all()

                    for att in attachments:
                        if att.storage_key and att.storage_key.startswith(old_prefix):
                            att.storage_key = att.storage_key.replace(old_prefix, new_prefix, 1)

                    session.commit()
                    migrated_count += 1
                except Exception as e:
                    print(f"[ERROR] {opp_id}: {e}")
                    session.rollback()
                    error_count += 1

        print(f"\n迁移完成: 成功 {migrated_count}, 跳过 {skipped_count}, 失败 {error_count}")

    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移商机存储文件夹命名")
    parser.add_argument("--dry-run", action="store_true", help="只打印变更，不执行")
    args = parser.parse_args()

    print("=" * 60)
    print("商机存储文件夹迁移脚本")
    print("=" * 60)
    print(f"存储根目录: {Path(__file__).parent.parent / 'storage'}")
    print(f"模式: {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    print("=" * 60)

    migrate(dry_run=args.dry_run)