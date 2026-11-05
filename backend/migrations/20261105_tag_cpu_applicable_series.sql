-- 2026-11-05 数据修正：CPU 类料补平台适配标注（同屏共测标记：Polaris 机型推荐出 Intel CPU）。
-- 根因：applicable=None 按「通用件」语义放行任何系列；Intel/AMD CPU 漏标导致平台过滤失效。
-- 阵营判定与平台归置规则同源：Intel/Xeon/AMD/EPYC/霄龙 → Orion（x86 平台）；兆芯 KH → Polaris（已在库，不动）。
-- 回滚备份：D:\CPQ_Archive\kp_cpu_applicable_backup_20261105.json（含每行原 applicable 值）。
-- 待用户确认后执行。

UPDATE kp.kp_parts SET applicable = '{"series": ["Orion"]}'::jsonb
WHERE id IN (
  121, 418, 122, 123, 285, 310, 198, 420, 124, 191,
  434, 376, 385, 419, 244, 233, 239, 453, 455, 471
);
