---
name: no-patch-on-patch
description: "修 bug/加功能别在补丁上叠补丁——同步清理关联冗余/死码，拒绝\"留着备用\"的累积"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 99f80c0f-5994-42ea-bc2a-2118a8350f03
  modified: 2026-08-05T07:42:38.401Z
---

修 bug 或加功能时，别只往现有代码上叠补丁。每次改动同步审视：有没有引入双源/冗余？旧实现是否因此变死码？有就一并清掉，不要"留着以后可能用"——留着就是下一轮 bug 的温床。

**Why:** 用户反复强调（典型：维保 total_price 修了 N 轮，根因是 calculate_totals/warrantyRates/前端 calcConfigTotals 三套口径层层叠加，越缠越乱，最终谁也不敢动）。补丁累积让代码像毛线团，每次"先这样修能用"都在透支下次的可维护性。

**How to apply:** 改一个 bug 前，先梳理它涉及的完整链路（前后端 + 所有调用点），找单一源/根因，一次改到位；改动让某段旧代码变冗余时，同一次删掉（哪怕觉得"以后可能用"）。宁可多删十行，不要留一个"备用"分支。改完自问：这次改动后，有没有两段代码在做同一件事？有就合并/删一个。关联 [[systematic-cleanup-not-whackamole]]。
