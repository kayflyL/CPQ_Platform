"""
Univer 导出模板仓储层

职责：
- CRUD 操作
- 列表查询（不含 workbook_snapshot，减少传输）
- 详情查询（含完整 snapshot）
"""
from typing import Optional
from datetime import datetime
from app.models.base import Opportunity_SessionLocal
from app.models.univer_template import UniverTemplate


class UniverTemplateRepo:
    def __init__(self):
        self.session_factory = Opportunity_SessionLocal

    def list(self) -> list[dict]:
        """列表查询（不含 workbook_snapshot）"""
        with self.session_factory() as db:
            rows = db.query(UniverTemplate).order_by(UniverTemplate.is_default.desc(), UniverTemplate.id.desc()).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "display_name": r.display_name,
                    "is_default": r.is_default,
                    "bindings": r.bindings,
                    "sheet_config": r.sheet_config,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    def get_by_id(self, template_id: int) -> Optional[dict]:
        """详情查询（含完整 snapshot）"""
        with self.session_factory() as db:
            r = db.query(UniverTemplate).filter(UniverTemplate.id == template_id).first()
            if not r:
                return None
            return {
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "is_default": r.is_default,
                "workbook_snapshot": r.workbook_snapshot,
                "bindings": r.bindings,
                "sheet_config": r.sheet_config,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    def get_default(self) -> Optional[dict]:
        """获取默认模板"""
        with self.session_factory() as db:
            r = db.query(UniverTemplate).filter(UniverTemplate.is_default == True).first()
            if not r:
                return None
            return {
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "is_default": r.is_default,
                "workbook_snapshot": r.workbook_snapshot,
                "bindings": r.bindings,
                "sheet_config": r.sheet_config,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    def create(self, data: dict) -> dict:
        """创建模板"""
        now = datetime.now().isoformat()
        with self.session_factory() as db:
            # 如果设为默认，先取消其他默认
            if data.get("is_default"):
                db.query(UniverTemplate).update({UniverTemplate.is_default: False})

            # 自动生成唯一 name（如果已存在则追加时间戳）
            name = data["name"]
            existing = db.query(UniverTemplate).filter(UniverTemplate.name == name).first()
            if existing:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                name = f"{name}_{timestamp}"

            template = UniverTemplate(
                name=name,
                display_name=data["display_name"],
                is_default=data.get("is_default", False),
                workbook_snapshot=data["workbook_snapshot"],
                bindings=data.get("bindings", []),
                sheet_config=data.get("sheet_config", {}),
                created_at=now,
                updated_at=now,
            )
            db.add(template)
            db.commit()
            db.refresh(template)
            return {
                "id": template.id,
                "name": template.name,
                "display_name": template.display_name,
                "is_default": template.is_default,
                "workbook_snapshot": template.workbook_snapshot,
                "bindings": template.bindings,
                "sheet_config": template.sheet_config,
                "created_at": template.created_at,
                "updated_at": template.updated_at,
            }

    def update(self, template_id: int, data: dict) -> Optional[dict]:
        """更新模板"""
        now = datetime.now().isoformat()
        with self.session_factory() as db:
            template = db.query(UniverTemplate).filter(UniverTemplate.id == template_id).first()
            if not template:
                return None

            # 如果设为默认，先取消其他默认
            if data.get("is_default"):
                db.query(UniverTemplate).filter(UniverTemplate.id != template_id).update(
                    {UniverTemplate.is_default: False}
                )

            # 更新字段
            if "name" in data:
                template.name = data["name"]
            if "display_name" in data:
                template.display_name = data["display_name"]
            if "is_default" in data:
                template.is_default = data["is_default"]
            if "workbook_snapshot" in data:
                template.workbook_snapshot = data["workbook_snapshot"]
            if "bindings" in data:
                template.bindings = data["bindings"]
            if "sheet_config" in data:
                template.sheet_config = data["sheet_config"]

            template.updated_at = now
            db.commit()
            db.refresh(template)

            return {
                "id": template.id,
                "name": template.name,
                "display_name": template.display_name,
                "is_default": template.is_default,
                "workbook_snapshot": template.workbook_snapshot,
                "bindings": template.bindings,
                "sheet_config": template.sheet_config,
                "created_at": template.created_at,
                "updated_at": template.updated_at,
            }

    def delete(self, template_id: int) -> bool:
        """删除模板"""
        with self.session_factory() as db:
            template = db.query(UniverTemplate).filter(UniverTemplate.id == template_id).first()
            if not template:
                return False
            db.delete(template)
            db.commit()
            return True

    def set_default(self, template_id: int) -> bool:
        """设为默认模板"""
        with self.session_factory() as db:
            template = db.query(UniverTemplate).filter(UniverTemplate.id == template_id).first()
            if not template:
                return False
            # 取消其他默认
            db.query(UniverTemplate).update({UniverTemplate.is_default: False})
            template.is_default = True
            db.commit()
            return True
