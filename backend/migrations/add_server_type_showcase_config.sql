-- Migration: add_server_type_showcase_config
-- 为 server_types 表添加 showcase_config JSONB 列，用于存储 3D 展示配置

ALTER TABLE l6.server_types
    ADD COLUMN IF NOT EXISTS showcase_config JSONB;

COMMENT ON COLUMN l6.server_types.showcase_config IS
'3D 展示配置（JSONB）:
{
  "glb_path": string | null,           -- GLB 文件路径（null 表示无 3D 展示）
  "title": string,                      -- 展示卡片标题
  "description": string,                -- 展示卡片描述
  "bullets": [string],                  -- 要点列表
  "render": {                           -- 3D 渲染参数（可选）
    "light": {                          -- 浅色主题参数
      "ambient_intensity": float,       -- 环境光强度 (0-2)
      "key_light_intensity": float,     -- 主光源强度 (0-3)
      "fill_light_intensity": float,    -- 补光强度 (0-1)
      "key_light_color": string,        -- 主光源颜色（hex）
      "fill_light_color": string,       -- 补光颜色（hex）
      "background_color": string,       -- 背景颜色（hex，可选）
      "tone_mapping": string,           -- 色调映射（NoToneMapping/LinearToneMapping/ACESFilmicToneMapping）
      "exposure": float                 -- 曝光度 (0-3)
    },
    "dark": { ... },                    -- 深色主题参数（同 light）
    "camera_fov": float,                -- 相机 FOV（默认 45）
    "auto_rotate_speed": float,         -- 自动旋转速度（默认 0.8）
    "enable_damping": boolean,          -- 启用阻尼（默认 true）
    "damping_factor": float             -- 阻尼因子（默认 0.08）
  }
}';