"""
规格书模板仓储层

职责：
- CRUD 操作
- 列表查询（不含大字段）
- 详情查询（含完整配置）
"""
from typing import Optional
from datetime import datetime
from app.models.base import Opportunity_SessionLocal
from app.models.spec_template import SpecTemplate


class SpecTemplateRepo:
    def __init__(self):
        self.session_factory = Opportunity_SessionLocal

    def list(self) -> list[dict]:
        """列表查询（不含完整配置，减少传输）"""
        with self.session_factory() as db:
            rows = db.query(SpecTemplate).order_by(
                SpecTemplate.is_default.desc(), 
                SpecTemplate.id.desc()
            ).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "display_name": r.display_name,
                    "is_default": r.is_default,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ]

    def get_by_id(self, template_id: int) -> Optional[dict]:
        """详情查询（含完整配置）"""
        with self.session_factory() as db:
            r = db.query(SpecTemplate).filter(SpecTemplate.id == template_id).first()
            if not r:
                return None
            return {
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "is_default": r.is_default,
                "branding": r.branding,
                "display_options": r.display_options,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    def get_default(self) -> Optional[dict]:
        """获取默认模板"""
        with self.session_factory() as db:
            r = db.query(SpecTemplate).filter(SpecTemplate.is_default == True).first()
            if not r:
                return None
            return {
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "is_default": r.is_default,
                "branding": r.branding,
                "display_options": r.display_options,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }

    def create(self, data: dict) -> dict:
        """创建模板"""
        now = datetime.now().isoformat()
        with self.session_factory() as db:
            # 如果设为默认，先取消其他默认
            if data.get("is_default"):
                db.query(SpecTemplate).update({SpecTemplate.is_default: False})

            # 自动生成唯一 name
            name = data["name"]
            existing = db.query(SpecTemplate).filter(SpecTemplate.name == name).first()
            if existing:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                name = f"{name}_{timestamp}"

            template = SpecTemplate(
                name=name,
                display_name=data["display_name"],
                is_default=data.get("is_default", False),
                branding=data.get("branding", {}),
                layout=data.get("layout", {}),
                fields=data.get("fields", {}),
                display_options=data.get("display_options", {}),
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
                "branding": template.branding,
                "display_options": template.display_options,
                "created_at": template.created_at,
                "updated_at": template.updated_at,
            }

    def update(self, template_id: int, data: dict) -> Optional[dict]:
        """更新模板"""
        now = datetime.now().isoformat()
        with self.session_factory() as db:
            template = db.query(SpecTemplate).filter(SpecTemplate.id == template_id).first()
            if not template:
                return None

            # 如果设为默认，先取消其他默认
            if data.get("is_default"):
                db.query(SpecTemplate).filter(SpecTemplate.id != template_id).update(
                    {SpecTemplate.is_default: False}
                )

            # 更新字段
            if "name" in data:
                template.name = data["name"]
            if "display_name" in data:
                template.display_name = data["display_name"]
            if "is_default" in data:
                template.is_default = data["is_default"]
            if "branding" in data:
                template.branding = data["branding"]
            if "display_options" in data:
                template.display_options = data["display_options"]

            template.updated_at = now
            db.commit()
            db.refresh(template)

            return {
                "id": template.id,
                "name": template.name,
                "display_name": template.display_name,
                "is_default": template.is_default,
                "branding": template.branding,
                "display_options": template.display_options,
                "created_at": template.created_at,
                "updated_at": template.updated_at,
            }

    def delete(self, template_id: int) -> bool:
        """删除模板"""
        with self.session_factory() as db:
            template = db.query(SpecTemplate).filter(SpecTemplate.id == template_id).first()
            if not template:
                return False
            db.delete(template)
            db.commit()
            return True

    def set_default(self, template_id: int) -> bool:
        """设为默认模板"""
        with self.session_factory() as db:
            template = db.query(SpecTemplate).filter(SpecTemplate.id == template_id).first()
            if not template:
                return False
            # 取消其他默认
            db.query(SpecTemplate).update({SpecTemplate.is_default: False})
            template.is_default = True
            db.commit()
            return True
