-- 导出模板幽灵绑定清理 + 复合字段「业务名-商机创建日期」（2026-11-01）。
-- 背景：opportunity_name 字段 2026-07-21 注册后当日删除，但模板 JSON 里的绑定残留；
-- 填充器对缺失键静默取空（data.get(field_key,"")），导致 B1 预览/导出恒为空白。
-- 本脚本三件事（幂等可重跑）：
--   1) 注册复合别名字段 biz_created_date（值由 preview_data_loader 生成：业务名-YYYYMMDD）；
--   2) 所有导出模板中 fieldKey=opportunity_name 的静态绑定改绑 biz_created_date；
--   3) 模板快照里的 {{opportunity_name}} 占位标记文本同步替换（编辑器显示用）。
-- 配套代码（必须同版部署）：backend/app/services/preview_data_loader.py 的 biz_created_date 别名。
-- 本地已执行（2026-11-01）；服务器发版时重放。备份见 D:\CPQ_Archive\univer_templates_backup_20261101.json。

INSERT INTO rules.business_fields
  (key, label, category, source, scope, type, display_type, group_name,
   enabled, export_visible, description, sort_order, permission, tenant_id, used_in_pages, is_core_field,
   created_by, updated_by, created_at, updated_at)
SELECT 'biz_created_date', '业务名-商机创建日期', 'opportunity', 'opportunity', 'opportunity',
       'text', 'text', '基本信息',
       TRUE, TRUE,
       '复合别名：业务名-商机创建日期YYYYMMDD（模板头部单格绑定用，与导出文件名同款日期格式）',
       0, 'editable', 'default', '[]', FALSE,
       'system', 'system', TO_CHAR(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM rules.business_fields WHERE key = 'biz_created_date');

UPDATE opportunities.univer_templates
SET bindings = (
    SELECT jsonb_agg(
        CASE WHEN b ->> 'fieldKey' = 'opportunity_name'
             THEN jsonb_set(b, '{fieldKey}', '"biz_created_date"', TRUE)
             ELSE b END
    )
    FROM jsonb_array_elements(bindings::jsonb) AS b
)
WHERE EXISTS (
    SELECT 1 FROM jsonb_array_elements(bindings::jsonb) AS b
    WHERE b ->> 'fieldKey' = 'opportunity_name'
);

UPDATE opportunities.univer_templates
SET workbook_snapshot = replace(workbook_snapshot::text, '{{opportunity_name}}', '{{biz_created_date}}')::json
WHERE workbook_snapshot::text LIKE '%{{opportunity_name}}%';

INSERT INTO rules.field_audit_logs (field_key, action, changes, operator, operated_at)
SELECT 'biz_created_date', 'create',
       '{"note": "复合别名：业务名-商机创建日期（迁移 20261101_export_template_biz_created_date.sql）"}',
       'system', TO_CHAR(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM rules.field_audit_logs WHERE field_key = 'biz_created_date');
