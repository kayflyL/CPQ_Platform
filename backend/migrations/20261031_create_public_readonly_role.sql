-- 公开链路只读受限 DB 角色：公开端点专用连接，价格表物理不可见。
-- 原理：公开目录/线索端点用本角色连接数据库，只 GRANT 目录几张表的安全列；
-- parts/kp/opportunities/quotations 等一切含价表无授权——即使公开代码出漏洞，数据库拒发。
-- 密码走环境变量（仓库零密码）。跑法：
--   psql -v cpq_public_ro_password="$CPQ_PUBLIC_RO_PASSWORD" \
--        -f backend/migrations/20261031_create_public_readonly_role.sql
-- 回滚（如需）：DROP ROLE IF EXISTS cpq_public_ro;（先撤依赖它的连接）

\set ON_ERROR_STOP on
\set cpq_public_ro_password 'CHANGE_ME_BLOCKED'
-- 密码守卫：未通过 -v 传入真实密码时，除零直接中断脚本
SELECT 1 / (CASE WHEN :'cpq_public_ro_password' = 'CHANGE_ME_BLOCKED' THEN 0 ELSE 1 END) AS pwd_guard;

CREATE ROLE cpq_public_ro LOGIN PASSWORD :'cpq_public_ro_password';

-- 公开目录白名单列（与 public_intake 的白名单 SELECT 一一对应；加列须同步改）
GRANT USAGE ON SCHEMA l6;
GRANT SELECT (id, name, description, sort_order, showcase_config)
    ON l6.server_types TO cpq_public_ro;
GRANT SELECT (id, name, server_type_id, use, base_config_id, sort_order,
              description, image_url, lifecycle_status, product_content, is_published)
    ON l6.server_models TO cpq_public_ro;
GRANT SELECT (id, name, form, bays, series, config_content, model_id)
    ON l6.base_configs TO cpq_public_ro;

-- 显式拒绝面（默认无授权，此处仅为可读性声明；勿加 opportunities/kp/rules 的任何授权）
-- opportunities.opportunity_leads 亦不对本角色开放——线索写入走主连接，公开角色只读目录。

-- 验证（应报 permission denied for table opportunities）：
--   SET ROLE cpq_public_ro;
--   SELECT count(*) FROM opportunities.opportunities;   -- 预期：ERROR
--   SELECT count(*) FROM parts.parts_master;           -- 预期：ERROR（schema 不可见）
--   RESET ROLE;
