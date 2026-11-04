-- 服务器3D模型 · 部件库扩展(2026-11-03):kind 区分整机/部件,part_type 标部件类型。
-- kind='machine'(默认)=整机(可绑机型上配置页);kind='part'=部件库(独立预览,不参与机型绑定)。
-- 首个部件种子:CPU 部件模型(kind='part', part_type='cpu'),预览由前端 server3d/parts/cpu.ts 工厂产出。
-- 刻字定调:只出品牌字(AMD/兆芯),不出现具体型号(2026-11-03)。
ALTER TABLE l6.server_3d_models ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'machine';
ALTER TABLE l6.server_3d_models ADD COLUMN IF NOT EXISTS part_type TEXT;

INSERT INTO l6.server_3d_models (name, kind, part_type, layout_config, created_at, updated_at)
SELECT 'CPU 部件模型', 'part', 'cpu', NULL,
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM l6.server_3d_models WHERE kind = 'part' AND part_type = 'cpu');

INSERT INTO l6.server_3d_models (name, kind, part_type, layout_config, created_at, updated_at)
SELECT '风扇墙模块', 'part', 'fan', NULL,
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM l6.server_3d_models WHERE kind = 'part' AND part_type = 'fan');
