-- 2026-11-05 存量归一化（首例，仅机械可判）：交付地区「葡萄牙」→「海外-葡萄牙」。
-- 葡萄牙已加入海外名单（constants/regions.ts 欧洲），旧值「葡萄牙」无分价关键词命中、
-- 被兜底错分国内桶；加「海外-」前缀后必命中海外桶，且为折叠选择器的合法编码值。
-- 回滚备份：D:\CPQ_Archive\delivery_region_portugal_backup_20261105.json（含整行 extra_fields 原文）。

UPDATE opportunities.opportunities
SET extra_fields = jsonb_set(extra_fields::jsonb, '{delivery_region}', '"海外-葡萄牙"')::text
WHERE extra_fields::jsonb ->> 'delivery_region' = '葡萄牙';
