-- 服务器3D模型 · 兆芯 CPU 部件补登记(2026-11-06,幂等)。
-- 背景:cpu.ts 工厂本有 sp5(AMD)/kh(兆芯) 双形态,但 20261103 种子只登记了 AMD 默认行,
-- layout_config.family 是形态族唯一入口且编辑页无控件写它 → 兆芯款自上线起不可达("最后一厘米没接")。
-- 本行补上:layout_config='{"family":"kh"}',编辑页 load() 读 family 即渲染兆芯形态(前端零改动)。
INSERT INTO l6.server_3d_models (name, kind, part_type, layout_config, created_at, updated_at)
SELECT '兆芯 CPU 部件模型', 'part', 'cpu', '{"family":"kh"}',
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM l6.server_3d_models WHERE kind = 'part' AND part_type = 'cpu' AND layout_config LIKE '%"family":"kh"%');
