---
name: server-db-merge-20261016
description: "2026-10-16单向合并本地14商机树到服务器(725行/17表,暂存+ON CONFLICT);关键坑=服务器DB用户是cpq非postgres;碰数据同步/迁移/直连服务器库先看"
metadata:
  node_type: memory
  type: project
  originSessionId: a2a57978-a2de-462e-929f-e984dba66df2
  modified: 2026-10-22T02:38:46.079Z
---

2026-10-16 发现入口分裂:上线(10-10)后真实业务一直录在**本地开发机**(14商机/725行子树),服务器6天几乎零新增——"线索没同步"真因=系统无本地↔服务器同步通道,服务器库唯一事实源的定调没被执行。已单向合并:本地14商机完整子树(报价473行明细/流程卡/节点/附件/消息/需求单/核价/助手消息/4个新用户)灌入服务器,17表逐表对账 ALL_OK,13条序列已 setval。

**Why:** ①两库 10-10 后各自生长,撞键真实存在(feed_users 1条/flow_cards 1条/flow_nodes 2条),故装载必须暂存表+ON CONFLICT DO NOTHING(服务器现值优先);②单事务+前置 pg_dump 备份(D:\CPQ_Archive\server_backup_20261016.dump,本地pg_dump18走ssh隧道)是可回滚底线。

**How to apply:** ①**服务器DB用户是 `cpq` 不是 `postgres`**(backend/.env POSTGRES_USER,密码认证failed先查用户名再查密码;密码提取过 ssh 要 `tr -d "\r"`);②**psycopg3 非autocommit陷阱(10-16踩实)**:连接后先跑过SELECT就开了隐式外层事务,`with conn.transaction()` 沦为 savepoint,断开连接=整体回滚,同连接里的"对账"看到的是自己未提交数据=假ALL_OK——写库脚本必须 `conn.autocommit=True` + 验证必须走独立连接;③服务器Zonky包无psql/pg_dump,服务器侧用 `~/cpq/backend/.venv/bin/python` + app配置连库,本机验证走 `ssh -f -N -L` 隧道+本地PG18 psql;④再合并:export=`D:\CPQ_Archive\merge_1016_export.py`(三层扇出:用户→opportunity_id→quotation_id/flow_id/thread_id,漏二层=迁空壳),loader=`~/merge_1016/loader.py`(v3 autocommit版);⑤纪律:录入只走服务器10.32.39.132:5173(手机5443),本地机只开发不录业务。列表口径:商机列表=总行数-ai_office- deleted(回收站),539总→列表197。相关:[[deploy-ubuntu-single-machine]] [[repro-writes-hit-real-db]] [[opportunity-identity]]
