---
name: firecrawl-spec-extract-poc
description: "Firecrawl 结构化抽取已验证可行(厂商GPU规格页→{spec_key,spec_value});key在backend/.env;v2用formats:[{type:json,schema}]非jsonOptions;一次~5credits"
metadata: 
  node_type: memory
  type: project
  originSessionId: 0aa265ad-5de4-4f99-a706-563646f639bb
  modified: 2026-08-10T09:40:57.002Z
---

> **⚠️ 2026-08-10 核实(重要)：本条引用的补 spec 脚本——`apply_extract_specs.py`、`apply_lookup_specs.py`、Firecrawl 批量脚本——已全部在 08-10 codex 大清理中删除。现 `backend/scripts/` 无任何 Firecrawl/补 spec 脚本（仅 `backfill_missing_specs.py`，且它走 WebSearch 不走 Firecrawl）。要再用 Firecrawl 批量补 spec 得重建。下面的 v2 打法知识（formats、search→extract、显存自检、并发限流、国产卡留手填）仍有效可参考；`FIRECRAWL_API_KEY` 应仍在 backend/.env。

2026-07-31 验证:Firecrawl v2 `/scrape` 带 `formats:[{type:"json",schema:{...},prompt}]` 能从 NVIDIA L40S 规格页抽出 11 个结构化字段(显存/带宽/TDP/接口/散热/CUDA核数等),全部正确,直接映射料号库 `{spec_key,spec_value}` 结构。**"自动补料号库 spec"这条路成立。**

**关键 gotcha(v2 API):**
- 结构化抽取字段是 `formats:[{type:"json",schema:{}}]`,**不是** `jsonOptions`(v1 残留 → 报 `unrecognized_keys` 400)。
- 拿不准字段名时,调 `POST /v2/support/docs-search`({question}) 问官方文档,最权威。

**环境/接入:**
- key 存 `backend/.env` 的 `FIRECRAWCRAWL_API_KEY`(已 gitignore);`set -a;. backend/.env;set +a` 读出。
- curl 需 `--ssl-no-revoke`(见 [[windows-curl-ssl-no-revoke]]);Python SDK/requests 不受影响。
- skill 装在 `~/.claude/skills/firecrawl/`(见 [[claude-3p-environment]])。
- 成本:一次结构化抽取 ~5 credits。

**How to apply:**
- 给料号库/KP库做"自动补spec":按品类定义 schema → Firecrawl extract 出草稿 → 人在 Parts 编辑弹窗确认后落库(延续 [[derive-must-have-manual-fallback]] 推导仅作参考原则,不直接驱动报价)。
- **国产卡页(浪潮/壁仞/天数智芯等)未测**,是 [[kp-spec-coverage-sparse]] 的真缺口,也是下一步该优先试的——国产厂商页结构各异,schema 要单独调。

**Why:** 补记忆里反复出现的"料号库 spec 大量为空 / GPU线缆实测为空 / 全靠手填"根因;现已证明技术上走得通。

**进展(2026-07-31):** 已对真实 kp 件跑通 search→extract→INSERT 全链路——GPU card 分类下 id=254(AMD R9700)、id=258(RTX 5090),共 20 条 spec 落库 `kp.kp_part_specs`(spec_id 379–398)。search 走 `/v2/search` 返回 `data.web[]`,挑官方页再 scrape。直连 DB 方法见 [[cpq-db-direct-query]]。两件原 spec 全空=纯新增;部分填写的件逻辑是跳过已存在的 spec_key。

**进展(2026-08-02,批量):** 扫了 GPU 分类(category 3,34 件)→ **20 件自动补齐,14 件留手填**。批量打法(已验证,后续扫 CPU/NIC 等可复用):
- **按型号去重**:34 件只有 ~19 独特型号,每型号 search+extract 一次再套到同型号件上,省 credit。
- **干跑(dry-run)→ 缓存 → 落库**:先只抽取不写、存 `%TEMP%/gpu_extract_cache.json`,人过目后再 INSERT;重试只重跑失败型号,不重花成功型号的 credit。
- **显存自检**:抽出显存(GB)与库里 `Capacity` 比,差>2G 标红跳过——拦住了 A800(页是 40G 工作站卡≠80G 数据中心卡)、L20(首搜落到 2009 Tesla Fermi PDF)等错页。
- **坑**:并发 search 易限流返空(R9700 单搜成功、并发 no-hit);重抽改串行+sleep2s 解决。
- **国产卡(壁仞/沐曦/天数/武桐树)抽到的都是官网首页级垃圾**,按 [[kp-spec-coverage-sparse]]「国产卡留手填」原则不自动灌。
- 用 `python -X utf8` + curl `--ssl-no-revoke` + SQLAlchemy(`backend/.env` 的 `FIRECRAWL_API_KEY`),注意 [[cpq-db-direct-query]] 的 /tmp 路径坑——脚本写文件用 `%TEMP%` 或 stdin,别用 `/tmp` 字面路径。

**容量核验(2026-08-02,Firecrawl `/search` 查权威页):** 别凭记忆改显存,我的 GPU SKU 记忆不可靠,改前必查官方页:
- **RTX PRO 5000 Blackwell 有 48G 和 72G 两个配置**(NVIDIA 官方 datasheet 原文 "48 or 72 GB"),id=149 的 72G **是对的**,曾被误判成错误——别再改。
- **沐曦 曦云C550 = 144GB HBM3e**(百度百科),id=181 原 "8 GB"(误读了名字里 "8GPU模组" 的 8)已改 → 144 GB。**别再记成 64G。**
- **RTX 4090 = 24GB**,id=160 原 "48 GB" 已改 → 24 GB。
**进展(2026-08-02,CPU 分类 category 4,26 件):** 用户急用 TDP 影响电源(PSU)选型。打法优化:先 `/search`(1 credit/型号,snippet 直接给 TDP)而非 `/scrape`(5 credit)——AMD/Intel snippet 上 AMD 官网 + TechPowerUp + HPE 三方收敛即可定 TDP,**不必 scrape**。结果 **19/26 有 TDP**,7 件无(见下)。共插 97 条 spec(tdp + Cores/Base/Boost/Socket/L3/Architecture/Memory Support)+ 12 条 datasheet_url + 修 191 品牌错(NVIDIA→AMD,其实是 AMD 9335)。
- **CPU TDP 现状(SSOT 快查,PSU 选型用):** AMD EPYC: 9115=125, 9255=200, 9334=210, 9354=280, 9355=280, 9124=200, 9554=360, 9654=360, 9335=210, 9745=400, 9347F(实为9374F)=320。Intel Xeon: 6430=270, 4416+=165, 6530=270, 8468=350。**单路最高 400W(9745),双路×2。**
- **7 件无公开 TDP(国产 + 型号名疑误):** AMD `7A23`(106)、`9J14`(233,疑 9714 但搜不到确认)——型号名查无对应 EPYC,疑录入错/云定制件,留手填;兆芯 KH-50000(126/128/182/259)、KH-40000(225)——官网/新闻只给核心/频率/缓存/内存,**不公布 TDP**(同 [[kp-spec-coverage-sparse]]「国产件留手填」)。
- **坑:** Firecrawl `/search` 连发 ~10 次后 429 Too Many Requests;解法:串行 + sleep 6-10s + 3 次指数退避重试。
- **CPU 型号名疑误(待用户确认,别自动改名):** `9347F`→疑 `9374F`(数字转置,已按 9374F 填 320W);`9J14`→疑 `9714`(J/7 形似);`7A23`→查无。
