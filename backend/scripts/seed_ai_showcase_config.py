"""种子数据：迁移 AI 系列的硬编码 showcase 配置到数据库。

将 showcase-config.ts 中的 AI 系列配置持久化到 l6.server_types.showcase_config。
"""
import json
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.config import get_settings
from app.models.base import l6_engine


def seed_ai_showcase_config():
    """迁移 AI 系列的 3D 展示配置到数据库。"""
    s = get_settings()

    # AI 系列配置（从 showcase-config.ts 迁移）
    ai_config = {
        "glb_path": "/models/ai-server.glb",
        "title": "AI 加速计算服务器",
        "description": "面向大模型训练与高密度推理，多 GPU 并行扩展，提供超高算力与高带宽互联。",
        "bullets": [
            "多路 GPU 并行，支撑大规模训练与推理",
            "高速互联，跨卡低延迟通信",
            "高功率散热设计，稳定满载运行",
        ],
        "render": {
            "light": {
                "ambient_intensity": 0.6,
                "key_light_intensity": 1.45,
                "fill_light_intensity": 0.35,
                "key_light_color": "#ffffff",
                "fill_light_color": "#bfd4ff",
                "background_color": "#000000",
                "tone_mapping": "NoToneMapping",
                "exposure": 1.0,
            },
            "dark": {
                "ambient_intensity": 0.9,
                "key_light_intensity": 1.1,
                "fill_light_intensity": 0.5,
                "key_light_color": "#ffffff",
                "fill_light_color": "#bfd4ff",
                "background_color": "#000000",
                "tone_mapping": "NoToneMapping",
                "exposure": 1.0,
            },
            "camera_fov": 45,
            "auto_rotate_speed": 0.8,
            "enable_damping": True,
            "damping_factor": 0.08,
        }
    }

    with l6_engine.begin() as conn:
        # 查找 AI 系列的 type_id
        result = conn.execute(
            text("SELECT id FROM l6.server_types WHERE name LIKE '%AI%' OR name LIKE '%加速%'")
        ).fetchone()

        if not result:
            print("❌ 未找到 AI 系列记录，请先创建 server_types 记录")
            return False

        type_id = result[0]
        print(f"[OK] 找到 AI 系列记录 (id={type_id})")

        # 更新 showcase_config
        config_json = json.dumps(ai_config, ensure_ascii=False)
        conn.execute(
            text("UPDATE l6.server_types SET showcase_config = CAST(:config AS jsonb) WHERE id = :id"),
            {"config": config_json, "id": type_id}
        )

        print(f"[OK] 已更新 AI 系列的 showcase_config")
        print(f"   配置内容: {json.dumps(ai_config, indent=2, ensure_ascii=False)}")

    return True


if __name__ == "__main__":
    print("=== 开始迁移 AI 系列展示配置 ===")
    success = seed_ai_showcase_config()
    if success:
        print("=== [OK] 迁移完成 ===")
    else:
        print("=== [FAIL] 迁移失败 ===")
        sys.exit(1)