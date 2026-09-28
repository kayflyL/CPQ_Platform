<template>
  <div class="workspace-page">
    <!-- 主内容区：三栏布局 -->
    <div class="content-inner">

      <!-- 配置 Tab 栏 -->
      <div class="cfg-bar">
        <button v-if="isMobile" class="ws-back-m" type="button" @click="goBack">‹</button>
        <div class="cfg-pills">
          <div
            v-for="name in Object.keys(store.configs)"
            :key="name"
            class="cfg-pill"
            :class="{ active: activeCfg === name }"
            @click="activeCfg = name"
            @dblclick="startRename(name as string)"
            @contextmenu="handleTabContextMenu($event, name as string)"
          >
            <template v-if="editingCfg === name">
              <input
                v-model="editingName"
                class="pill-edit-input"
                @keyup.enter="confirmRename"
                @keyup.escape="cancelRename"
                @blur="confirmRename"
                @click.stop
                ref="pillEditInput"
              />
            </template>
            <template v-else>
              <span class="pill-label">{{ name }}</span>
              <span
                class="pill-close"
                @click.stop="deleteConfigWithConfirm(name as string)"
                title="删除配置"
              >×</span>
            </template>
          </div>
        </div>
        <a-button size="small" class="cfg-add-btn" @click="addConfig">+ 添加配置</a-button>
        <div class="cfg-relation">
          <span class="cfg-relation-label">配置关系</span>
          <a-radio-group :value="configRelation" size="small" @change="(e: any) => onConfigRelationChange(e.target.value)">
            <a-radio-button value="compose">组合拆分</a-radio-button>
            <a-radio-button value="alternative">方案备选</a-radio-button>
          </a-radio-group>
        </div>
      </div>

      <!-- 配置 Tab 右键菜单 -->
      <Teleport to="body">
        <div
          v-if="contextMenu.visible"
          class="cfg-context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
          @click="closeContextMenu"
        >
          <div class="cfg-context-item" @click="startRename(contextMenu.cfgName)">重命名</div>
          <div class="cfg-context-item cfg-context-danger" @click="deleteConfig(contextMenu.cfgName)">删除</div>
        </div>
      </Teleport>

      <!-- 三栏布局 -->
      <template v-for="(cfg, name) in store.configs" :key="name">
        <div v-if="activeCfg === name" class="three-col-layout">

          <!-- 左栏：BOM 表格 (≈22%)，可折叠收窄（手机端移入左抽屉） -->
          <div v-if="!isMobile" class="col-left" :class="{ collapsed: leftCollapsed }">
            <div class="col-left-scroll">
              <template v-if="!leftCollapsed">
                <BomTable :cfg="cfg" />
              </template>
            </div>
            <!-- 右边缘垂直居中把手 -->
            <button class="left-collapse-btn" :title="leftCollapsed ? '展开左栏' : '收起左栏'" @click="leftCollapsed = !leftCollapsed">
              <span class="lc-icon">
                <RightOutlined v-if="leftCollapsed" />
                <LeftOutlined v-else />
              </span>
            </button>
          </div>

          <!-- 中栏：服务器配置 (≈50%) -->
          <div class="col-middle">
            <!-- 配置基本信息：服务器型号 + 数量 + 配置描述（同一张卡）-->
            <div class="glass card-section">
              <div class="basic-row">
                <div class="basic-field basic-field-grow">
                  <label class="basic-label">服务器型号</label>
                  <a-auto-complete
                    v-model:value="cfg.server_model"
                    :options="serverModelOptions"
                    @select="(v: string) => onServerModelSelect(v)"
                    placeholder="选择或输入服务器型号，如：ZS220 V2"
                    :filter-option="(input: string, option: any) => (option.value || '').toLowerCase().includes((input || '').toLowerCase())"
                    style="flex: 1"
                  />
                </div>
                <div class="basic-field">
                  <label class="basic-label">{{ isAlternative ? '该方案台数' : '数量' }}</label>
                  <a-input-number
                    v-model:value="store.configQuantities[String(name)]"
                    :min="1"
                    :max="9999"
                    size="small"
                    style="width: 120px"
                    addon-after="台"
                  />
                </div>
                <button
                  v-if="isAlternative"
                  class="primary-btn"
                  :class="{ active: primaryConfig === name }"
                  @click="markPrimary(name)"
                  :title="primaryConfig === name ? '当前主推方案' : '点击设为主推方案'"
                >{{ primaryConfig === name ? '☆ 主推' : '设为主推' }}</button>
              </div>

              <div class="desc-header" @click="descExpanded[name] = !descExpanded[name]">
                <span class="desc-title">配置描述</span>
                <span class="desc-preview" v-if="!descExpanded[name]">
                  {{ cfg.description ? cfg.description.slice(0, 40) + (cfg.description.length > 40 ? '...' : '') : '（未填写）' }}
                </span>
                <span class="desc-toggle">{{ descExpanded[name] ? '收起 ▲' : '展开 ▼' }}</span>
              </div>
              <div v-if="descExpanded[name]" class="desc-body">
                <a-textarea
                  v-model:value="cfg.description"
                  @blur="store.saveProject()"
                  placeholder="描述此配置方案的用途、客户需求等..."
                  :rows="3"
                  :maxlength="500"
                  show-count
                />
              </div>
            </div>

            <!-- 横向分栏导航 -->
            <div class="seg-nav">
              <div
                class="seg-item"
                :class="{ active: sectionState[name] === 'hardware' }"
                @click="sectionState[name] = 'hardware'"
              >
                <span class="seg-label">硬件选配</span>
              </div>
              <div
                class="seg-item"
                :class="{ active: sectionState[name] === 'warranty' }"
                @click="sectionState[name] = 'warranty'"
              >
                <span class="seg-label">维保 / 增值服务</span>
              </div>
              <div
                class="seg-item"
                :class="{ active: sectionState[name] === 'software' }"
                @click="sectionState[name] = 'software'"
              >
                <span class="seg-label">系统 / 软件</span>
              </div>
            </div>

            <!-- 硬件选配区域 -->
            <div v-if="sectionState[name] === 'hardware'" class="section-content">
              <!-- ① 机箱卡：ChassisCard 本体 + 卡尾价格三联（利润率/成本/售价进卡内）-->
              <div class="l6-section">
                <ChassisCard
                  flat
                  :model="chassisModel"
                  :series="chassisSeries"
                  :base-config-name="chassisBaseName"
                  :form="chassisForm"
                  :bays="chassisBays"
                  :l6-total="cfg.l6_custom_price || 0"
                  :hero-price="l6FinalPrice(cfg)"
                  @open="chassisModalOpen = true"
                >
                  <template #header-extra>
                    <PriceTriple
                      :cost="cfg.l6_custom_price || 0"
                      :margin="cfg.l6_profit_margin"
                      :final-price="l6FinalPrice(cfg)"
                      perm="field.quote.price"
                      cost-editable
                      :cost-disabled="!cfg.l6_price_manual"
                      @update:margin="(v: number) => store.setL6ProfitMargin(String(name), v || 0)"
                      @update:cost="(v: number) => store.setL6CustomPrice(String(name), v || 0)"
                    >
                      <template #cost-extra>
                        <a-switch
                          :checked="!!cfg.l6_price_manual"
                          checked-children="手动" un-checked-children="自动"
                          size="small"
                          @change="(ck: boolean) => ck ? store.setL6CustomPrice(String(name), cfg.l6_custom_price || 0) : store.setL6PriceAuto(String(name))"
                        />
                      </template>
                    </PriceTriple>
                  </template>
                  <template #foot-note>
                    <span class="l6-unmatched-hint" v-if="!chassisMatched">未关联目录机型，点「配置机箱」可在弹窗内手动挂基准配置</span>
                  </template>
                </ChassisCard>
              </div>

              <!-- ② Key Parts 配件大卡：结构性容器（弱底+边框，非玻璃避嵌套）+ 头部价格三联 + 扁平子卡 -->
              <div class="card-kp">
                <div class="kp-card-head">
                  <div class="kp-card-title">
                    <h3 class="sec-title">Key Parts 配件 <span class="count-badge">{{ cfg.items.filter((i: any) => i.category === 'Key Parts').length }}</span></h3>
                  </div>
                  <PriceTriple
                    :cost="kpCostTotal(cfg)"
                    :margin="kpMarginValue(cfg)"
                    :final-price="kpFinalPrice(cfg)"
                    perm="field.quote.price"
                    margin-placeholder="多种"
                    @update:margin="(v: number) => store.setKpProfitMargin(String(name), v || 0)"
                  />
                </div>

                <!-- KP 行：excel 模式 = 平铺卡片(比价/同步/历史)；新建模式 = 按类别分卡(料号库挑选+利润率) -->
                <!-- ① Excel 上传模式：保留平铺卡片 + match_status + 单条同步 + 历史 -->
                <div v-if="cfg.bom_source === 'excel'" class="kp-table-wrap">
                  <table v-if="kpExcelRows(cfg).length" class="kp-table">
                    <thead>
                      <tr>
                        <th>类别</th>
                        <th>型号 / 名称</th>
                        <th class="num">数量</th>
                        <th class="num">原始单价</th>
                        <th class="num">利润率%</th>
                        <th class="num">含税售价</th>
                        <th class="ops">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <template v-for="(item, idx) in kpExcelRows(cfg)" :key="item.item_id ?? idx">
                        <tr class="kp-tr">
                          <td>
                            <span class="kp-name">{{ item.part_category }}</span>
                          </td>
                          <td class="cat break">{{ item.catalogue || '—' }}</td>
                          <td class="num"><a-input-number v-model:value="item.qty" size="small" class="inp-num" :min="1" :controls="false" @blur="store.recalculateAll()" /></td>
                          <td class="num"><span class="kp-raw-price">¥ {{ settingsStore.formatNumber(calcUnitCost(Number(item.base_price) || 0, item.currency, store.exchangeRate, store.taxRate)) }}</span></td>
                          <td class="num"><a-input-number v-model:value="item.profit_margin" size="small" class="inp-num" :min="0" :controls="false" :disabled="!priceVisible" @blur="store.recalculateAll()" /></td>
                          <td class="num price">
                            <template v-if="priceVisible">¥ {{ settingsStore.formatNumber(item.final_price) }}</template>
                            <span v-else class="price-hidden">***</span>
                          </td>
                          <td class="ops">
                            <div class="ops-inner">
                              <span v-if="item.match_status" class="kp-match" :class="matchClass(item.match_status)">
                                {{ item.match_status }}
                              </span>
                              <div class="ops-btns">
                                <a-button v-if="kpSyncable(item)" size="small" type="primary" ghost @click="openSyncModal(item)">
                                  {{ isNewPart(item) ? '入库新配件' : '同步价格' }}
                                </a-button>
                                <a-button size="small" type="link" class="hist-btn" @click="openKpHistory(item)">
                                  历史价格 <span v-if="item._histLoaded">({{ item._history?.length || 0 }})</span>
                                </a-button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      </template>
                    </tbody>
                  </table>
                  <div v-else class="panel-empty">暂无 Key Parts 配件</div>
                </div>

                <!-- ② 新建模式：按类别分卡（复用 server-config KpCategoryCard，启用 quoteMode 带利润率）-->
                <div v-else class="kp-new-grid">
                  <KpCategoryCard
                    v-for="(cat, i) in kpCardCatsFor(cfg)"
                    :key="cat"
                    :cat="cat"
                    :step-num="i + 2"
                    :lines="kpLinesForCat(cfg, cat)"
                    :picker-items="pickerCatalog[cat] || []"
                    :price-of="priceOf"
                    :removable="!CORE_KP_CATS.includes(cat)"
                    :is-gpu="cat === 'GPU'"
                    :gpu-cable-pn="cfg.l6_bom_picks?.overrides?.gpuCablePn || ''"
                    :gpu-cable-qty="cfg.l6_bom_picks?.overrides?.gpuCableQty || 0"
                    :gpu-cable-items="gpuCableItems"
                    :exchange-rate="store.exchangeRate"
                    :tax-rate="store.taxRate"
                    quote-mode
                    flat
                    @set-line="(idx: number, patch: any) => onKpSetLine(cfg, cat, idx, patch)"
                    @del-line="(idx: number) => onKpDelLine(cfg, cat, idx)"
                    @add-line="onKpAddLine(cfg, cat)"
                    @remove-card="onKpRemoveCard(cfg, cat)"
                    @update:gpuCablePn="(pn: string) => setGpuCable(cfg, 'pn', pn)"
                    @update:gpuCableQty="(q: number) => setGpuCable(cfg, 'qty', q)"
                  />
                  <div class="kp-add-card-wrap" v-if="availableKpCats.length">
                    <select class="kp-add-card-sel" v-model="pendingNewKpCat" @change="onAddKpCard">
                      <option value="">+ 新增配置卡片…</option>
                      <option v-for="c in availableKpCats" :key="c.id" :value="c.name">{{ c.name }}</option>
                    </select>
                  </div>
                </div>

              </div>
            </div>

            <!-- 维保/增值服务区域 -->
            <div v-else-if="sectionState[name] === 'warranty'" class="section-content">
              <!-- L6/KP 质保服务费独立计算 -->
              <div class="warranty-row">
                <!-- L6 质保卡片 -->
                <div class="w-card">
                  <div class="w-card-title">L6 质保服务费</div>
                  <a-textarea
                    class="w-description"
                    :value="getWarrantyDesc(cfg, 'l6')"
                    @change="(e: Event) => store.setWarrantyDescription(name, 'l6', (e.target as HTMLTextAreaElement).value)"
                    :auto-size="{ minRows: 2, maxRows: 4 }"
                    placeholder="质保描述..."
                  />
                  <div class="w-card-body">
                    <div class="w-row">
                      <span class="w-label">年限：</span>
                      <a-select
                        :value="cfg.warranty_info?.l6?.years"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => onWarrantyYearsChange(name, 'l6', val)"
                        :options="[
                          { value: 1, label: '1 年' },
                          { value: 3, label: '3 年' },
                          { value: 5, label: '5 年' }
                        ]"
                        allowClear
                        placeholder="选择年限"
                      />
                    </div>
                    <div class="w-row">
                      <span class="w-label">费率：</span>
                      <a-input-number
                        :value="store.getWarrantyRateL6Pct(name)"
                        :min="0"
                        :max="100"
                        :precision="2"
                        :step="0.5"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => store.setWarrantyRateL6(name, val || 0)"
                      />
                      <span class="w-unit">%</span>
                    </div>
                    <div class="w-row">
                      <span class="w-label">金额：</span>
                      <span class="w-val">¥ {{ settingsStore.formatNumber(store.calcWarrantyFeeL6(name)) }}</span>
                    </div>
                    <div class="w-btns">
                      <a-button v-if="store.getWarrantyRateL6Pct(name) > 0" type="link" size="small" danger class="w-btn" @click="store.clearWarrantyL6(name)">清零</a-button>
                    </div>
                  </div>
                </div>

                <!-- KP 质保卡片 -->
                <div class="w-card">
                  <div class="w-card-title">KP 质保服务费</div>
                  <a-textarea
                    class="w-description"
                    :value="getWarrantyDesc(cfg, 'kp')"
                    @change="(e: Event) => store.setWarrantyDescription(name, 'kp', (e.target as HTMLTextAreaElement).value)"
                    :auto-size="{ minRows: 2, maxRows: 4 }"
                    placeholder="质保描述..."
                  />
                  <div class="w-card-body">
                    <div class="w-row">
                      <span class="w-label">年限：</span>
                      <a-select
                        :value="cfg.warranty_info?.kp?.years"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => onWarrantyYearsChange(name, 'kp', val)"
                        :options="[
                          { value: 1, label: '1 年' },
                          { value: 3, label: '3 年' },
                          { value: 5, label: '5 年' }
                        ]"
                        allowClear
                        placeholder="选择年限"
                      />
                    </div>
                    <div class="w-row">
                      <span class="w-label">费率：</span>
                      <a-input-number
                        :value="store.getWarrantyRateKPPct(name)"
                        :min="0"
                        :max="100"
                        :precision="2"
                        :step="0.5"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => store.setWarrantyRateKP(name, val || 0)"
                      />
                      <span class="w-unit">%</span>
                    </div>
                    <div class="w-row">
                      <span class="w-label">金额：</span>
                      <span class="w-val">¥ {{ settingsStore.formatNumber(store.calcWarrantyFeeKP(name)) }}</span>
                    </div>
                    <div class="w-btns">
                      <a-button v-if="store.getWarrantyRateKPPct(name) > 0" type="link" size="small" danger class="w-btn" @click="store.clearWarrantyKP(name)">清零</a-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 系统/软件区域 -->
            <div v-else class="section-content">
              <div class="empty-placeholder glass">暂无配置内容，后续扩展</div>
            </div>
          </div>

          <!-- 右栏：配置概要 (≈28%) -->
          <!-- 右栏：定价与利润（手机端移入右抽屉） -->
          <div v-if="!isMobile" class="col-right">
            <div class="glass fin-card cpq-stream-edge">
              <!-- 配置名称 -->
              <div class="fin-name">{{ name }}</div>

              <!-- 含税总价（主指标） -->
              <div class="fin-hero">
                <div class="hero-label">{{ isAlternative && primaryConfig !== name ? '主推方案含税总价' : '含税总价' }}</div>
                <div class="hero-val">
                  <template v-if="priceVisible">¥<CountNumber :value="heroTotalSales" /></template>
                  <span v-else class="price-hidden">***</span>
                </div>
              </div>

              <!-- 指标行 -->
              <div class="fin-rows">
                <div class="fin-row">
                  <span class="fin-label">整机总成本</span>
                  <span class="fin-val"><template v-if="priceVisible">¥<CountNumber :value="heroTotalCost" /></template><span v-else class="price-hidden">***</span></span>
                </div>
                <div class="fin-row">
                  <span class="fin-label">总利润额</span>
                  <span class="fin-val" :class="heroProfit >= 0 ? 'pos' : 'neg'"><template v-if="priceVisible">¥<CountNumber :value="heroProfit" /></template><span v-else class="price-hidden">***</span></span>
                </div>
                <div class="fin-row">
                  <span class="fin-label">综合毛利率</span>
                  <span class="fin-val" :class="heroMarginPct >= 0 ? 'pos' : 'neg'"><template v-if="priceVisible">{{ heroMarginPct.toFixed(settingsStore.numberPrecision) }}%</template><span v-else class="price-hidden">***</span></span>
                </div>
              </div>

              <!-- 方案备选对比：列出各方案型号/单台价/主推标记（仅 alternative 模式） -->
              <div v-if="isAlternative" class="alt-panel">
                <div class="fin-settings-title">方案对比</div>
                <div
                  v-for="altName in cfgNames"
                  :key="altName"
                  class="alt-row"
                  :class="{ primary: primaryConfig === altName }"
                  @click="markPrimary(altName)"
                >
                  <span class="alt-radio">{{ primaryConfig === altName ? '●' : '○' }}</span>
                  <span class="alt-name">{{ altName }}</span>
                  <span class="alt-model">{{ store.configs[altName]?.server_model || '—' }}</span>
                  <span class="alt-price"><template v-if="priceVisible">¥<CountNumber :value="store.getConfigTotals(altName)?.totalSales || 0" /></template><span v-else class="price-hidden">***</span></span>
                  <span class="alt-primary-tag">{{ primaryConfig === altName ? '主推' : '' }}</span>
                </div>
              </div>

              <!-- 税率/汇率 设置（独立分离） -->
              <div class="fin-settings">
                <div class="fin-settings-title">税率 / 汇率</div>
                <div class="fin-setting-row">
                  <label>增值税率</label>
                  <a-input-number
                    :value="store.taxRate * 100"
                    @change="(v: number) => { store.taxRate = (v || 0) / 100; store.recalculateAll(); persistTaxRate() }"
                    :min="0" :max="30" :step="1"
                    size="small"
                    style="width: 90px"
                    addon-after="%"
                  />
                </div>
                <div class="fin-setting-row">
                  <label>美元汇率</label>
                  <a-input-number
                    :value="store.exchangeRate"
                    @change="(v: number) => { store.exchangeRate = v || 7; store.recalculateAll(); persistExchangeRate() }"
                    :min="1" :max="20" :step="0.1"
                    size="small"
                    style="width: 90px"
                  />
                </div>
              </div>
            </div>

            <!-- 选型建议：规则命中的 require/exclude/derive/recommend 提醒，统一收纳到右栏 -->
            <div class="glass fin-card selection-advice-card">
              <div class="selection-advice-head">
                <span class="selection-advice-title">选型建议</span>
                <span v-if="selectionAlerts.length" class="selection-advice-count">{{ selectionAlerts.length }}</span>
              </div>
              <div v-if="selectionAlerts.length" class="selection-alerts">
                <div v-for="a in selectionAlerts" :key="a.ruleId + '-' + a.action" class="selection-alert" :class="a.severity">
                  <span class="sa-icon">{{ alertIcon(a.severity) }}</span>
                  <span class="sa-text">{{ a.desc }}<span v-if="a.offenders?.length" class="sa-off">（{{ a.offenders.join(' / ') }}）</span></span>
                </div>
              </div>
              <div v-else class="selection-advice-empty">当前配置规则校验通过</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 底部垫高 -->
      <div style="height: 80px;"></div>
    </div>

    <!-- 底部悬浮操作栏（手机端动作移入摘要条与右抽屉） -->
    <div v-if="!isMobile" class="action-bar glass">
      <div class="action-bar-inner">
        <a-button @click="goBack" class="btn-ghost">{{ entryLabel || "返回" }}</a-button>

        <a-select
          v-model:value="selectedTemplateValue"
          style="width: 220px"
          placeholder="选择导出模板"
          :disabled="!priceVisible"
        >
          <a-select-opt-group v-if="templates.length" label="Excel 模板">
            <a-select-option v-for="t in templates" :key="'excel-' + t.id" :value="'excel:' + t.id">
              {{ t.display_name }}{{ t.is_default ? ' (默认)' : '' }}
            </a-select-option>
          </a-select-opt-group>
          <a-select-opt-group v-if="specTemplates.length" label="规格书模板">
            <a-select-option v-for="t in specTemplates" :key="'spec-' + t.id" :value="'spec:' + t.id">
              {{ t.display_name }}{{ t.is_default ? ' (默认)' : '' }}
            </a-select-option>
          </a-select-opt-group>
        </a-select>

        <a-button @click="handlePreview" :loading="previewLoading" :disabled="!priceVisible" class="btn-ghost">预览</a-button>
        <a-button type="primary" @click="handleSave()" :loading="saveLoading" class="btn-pri">保存商机</a-button>
      </div>
    </div>

    <!-- 手机端左抽屉：BOM 对照快照（只读，随开随核） -->
    <a-drawer
      v-model:open="bomDrawerOpen"
      placement="left"
      width="90%"
      root-class-name="opp-quote-drawer"
      :closable="false"
      :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    >
      <div class="pd-head-row">
        <h3>BOM 对照</h3><span class="pd-chip">固化快照 · 只读</span><span class="pd-sp"></span>
        <button class="pd-x" type="button" @click="bomDrawerOpen = false">✕</button>
      </div>
      <div class="pd-scroll pd-scroll-bom">
        <BomTable v-if="isMobile && activeConfig" :cfg="activeConfig" />
      </div>
    </a-drawer>

    <!-- 手机端右抽屉：定价与利润（含预览导出；内容与桌面 col-right 同步维护） -->
    <a-drawer
      v-model:open="finDrawerOpen"
      placement="right"
      width="88%"
      root-class-name="opp-quote-drawer"
      :closable="false"
      :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    >
      <div class="pd-head-row">
        <h3>定价与利润</h3><span class="pd-chip">{{ activeCfg }}</span><span class="pd-sp"></span>
        <button class="pd-x" type="button" @click="finDrawerOpen = false">✕</button>
      </div>
      <div class="pd-scroll">
        <div class="glass fin-card cpq-stream-edge">
          <div class="fin-name">{{ activeCfg }}</div>

          <div class="fin-hero">
            <div class="hero-label">{{ isAlternative && primaryConfig !== activeCfg ? '主推方案含税总价' : '含税总价' }}</div>
            <div class="hero-val">
              <template v-if="priceVisible">¥<CountNumber :value="heroTotalSales" /></template>
              <span v-else class="price-hidden">***</span>
            </div>
          </div>

          <div class="fin-rows">
            <div class="fin-row">
              <span class="fin-label">整机总成本</span>
              <span class="fin-val"><template v-if="priceVisible">¥<CountNumber :value="heroTotalCost" /></template><span v-else class="price-hidden">***</span></span>
            </div>
            <div class="fin-row">
              <span class="fin-label">总利润额</span>
              <span class="fin-val" :class="heroProfit >= 0 ? 'pos' : 'neg'"><template v-if="priceVisible">¥<CountNumber :value="heroProfit" /></template><span v-else class="price-hidden">***</span></span>
            </div>
            <div class="fin-row">
              <span class="fin-label">综合毛利率</span>
              <span class="fin-val" :class="heroMarginPct >= 0 ? 'pos' : 'neg'"><template v-if="priceVisible">{{ heroMarginPct.toFixed(settingsStore.numberPrecision) }}%</template><span v-else class="price-hidden">***</span></span>
            </div>
          </div>

          <div v-if="isAlternative" class="alt-panel">
            <div class="fin-settings-title">方案对比</div>
            <div
              v-for="altName in cfgNames"
              :key="altName"
              class="alt-row"
              :class="{ primary: primaryConfig === altName }"
              @click="markPrimary(altName)"
            >
              <span class="alt-radio">{{ primaryConfig === altName ? '●' : '○' }}</span>
              <span class="alt-name">{{ altName }}</span>
              <span class="alt-model">{{ store.configs[altName]?.server_model || '—' }}</span>
              <span class="alt-price"><template v-if="priceVisible">¥<CountNumber :value="store.getConfigTotals(altName)?.totalSales || 0" /></template><span v-else class="price-hidden">***</span></span>
              <span class="alt-primary-tag">{{ primaryConfig === altName ? '主推' : '' }}</span>
            </div>
          </div>

          <div class="fin-settings">
            <div class="fin-settings-title">税率 / 汇率</div>
            <div class="fin-setting-row">
              <label>增值税率</label>
              <a-input-number
                :value="store.taxRate * 100"
                @change="(v: number) => { store.taxRate = (v || 0) / 100; store.recalculateAll(); persistTaxRate() }"
                :min="0" :max="30" :step="1"
                size="small"
                style="width: 90px"
                addon-after="%"
              />
            </div>
            <div class="fin-setting-row">
              <label>美元汇率</label>
              <a-input-number
                :value="store.exchangeRate"
                @change="(v: number) => { store.exchangeRate = v || 7; store.recalculateAll(); persistExchangeRate() }"
                :min="1" :max="20" :step="0.1"
                size="small"
                style="width: 90px"
              />
            </div>
          </div>
        </div>

        <div class="glass fin-card selection-advice-card">
          <div class="selection-advice-head">
            <span class="selection-advice-title">选型建议</span>
            <span v-if="selectionAlerts.length" class="selection-advice-count">{{ selectionAlerts.length }}</span>
          </div>
          <div v-if="selectionAlerts.length" class="selection-alerts">
            <div v-for="a in selectionAlerts" :key="a.ruleId + '-' + a.action" class="selection-alert" :class="a.severity">
              <span class="sa-icon">{{ alertIcon(a.severity) }}</span>
              <span class="sa-text">{{ a.desc }}<span v-if="a.offenders?.length" class="sa-off">（{{ a.offenders.join(' / ') }}）</span></span>
            </div>
          </div>
          <div v-else class="selection-advice-empty">当前配置规则校验通过</div>
        </div>

        <div class="exp-card-m">
          <div class="exp-title-m">预览与导出</div>
          <a-select
            v-model:value="selectedTemplateValue"
            style="width: 100%"
            placeholder="选择导出模板"
            :disabled="!priceVisible"
          >
            <a-select-opt-group v-if="templates.length" label="Excel 模板">
              <a-select-option v-for="t in templates" :key="'m-excel-' + t.id" :value="'excel:' + t.id">
                {{ t.display_name }}{{ t.is_default ? ' (默认)' : '' }}
              </a-select-option>
            </a-select-opt-group>
            <a-select-opt-group v-if="specTemplates.length" label="规格书模板">
              <a-select-option v-for="t in specTemplates" :key="'m-spec-' + t.id" :value="'spec:' + t.id">
                {{ t.display_name }}{{ t.is_default ? ' (默认)' : '' }}
              </a-select-option>
            </a-select-opt-group>
          </a-select>
          <a-button block style="margin-top: 8px" :disabled="!priceVisible" :loading="previewLoading" @click="handlePreview">预览</a-button>
        </div>
      </div>
    </a-drawer>

    <!-- 手机端底部 sticky 摘要条：BOM 入口 / 含税总价+毛利 / 保存 -->
    <div v-if="isMobile" class="sumbar">
      <button class="sum-ic" type="button" title="BOM 对照" @click="bomDrawerOpen = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 3h8l4 4v14H7V3zM13 3v6h6M9 13h6M9 17h4"/></svg>
      </button>
      <div class="sum-metric" @click="finDrawerOpen = true">
        <span class="v">
          <template v-if="priceVisible">¥<CountNumber :value="heroTotalSales" /></template>
          <span v-else class="price-hidden">***</span>
        </span>
        <span v-if="priceVisible" class="l">毛利 <b :class="heroMarginPct >= 0 ? 'pos' : 'neg'">{{ heroMarginPct.toFixed(settingsStore.numberPrecision) }}%</b> · 点看完整定价</span>
        <span v-else class="l">价格权限受限 · 联系管理员</span>
      </div>
      <button class="sum-cta" type="button" :disabled="saveLoading" @click="handleSave()">{{ saveLoading ? '保存中…' : '保存商机' }}</button>
    </div>

    <!-- 预览弹窗（使用 Univer 渲染） -->
    <a-modal
      v-model:open="previewVisible"
      :title="previewType === 'spec' ? '规格书预览' : '报价单预览'"
      :width="'95vw'"
      :ok-text="previewType === 'spec' ? '打印为 PDF' : '下载 Excel'"
      cancel-text="关闭"
      :confirm-loading="previewType === 'spec' ? false : exportDownloading"
      @ok="handleModalOk"
      :destroyOnClose="true"
      style="top: 20px"
    >
      <div v-if="previewType === 'excel'" class="preview-split">
        <div class="preview-opts">
          <div class="po-title">导出选项</div>
          <div class="po-group">
            <label class="po-row" :class="{ locked: !internalExportPerm }">
              <a-checkbox v-model:checked="revealSell" :disabled="revealRefreshing" @change="onRevealChange" />
              <span class="po-name">明细销售价</span>
            </label>
            <div class="po-desc">配置明细行的售价列</div>
          </div>
          <div class="po-group">
            <label class="po-row" :class="{ locked: !internalExportPerm }">
              <a-checkbox
                v-model:checked="revealCost"
                :disabled="!internalExportPerm || revealRefreshing"
                @change="onRevealChange"
              />
              <span class="po-name">成本价<span class="po-lock" v-if="!internalExportPerm">🔒</span></span>
              <span class="po-tag" v-if="internalExportPerm">对内</span>
            </label>
            <div class="po-desc">配置明细行的成本列</div>
          </div>
          <div class="po-group">
            <label class="po-row" :class="{ locked: !internalExportPerm }">
              <a-checkbox
                v-model:checked="revealMargin"
                :disabled="!internalExportPerm || revealRefreshing"
                @change="onRevealChange"
              />
              <span class="po-name">利润率<span class="po-lock" v-if="!internalExportPerm">🔒</span></span>
              <span class="po-tag" v-if="internalExportPerm">对内</span>
            </label>
            <div class="po-desc">逐行利润率 + 配置综合利润率</div>
          </div>
          <div class="po-version">
            <div class="po-version-label">当前版本</div>
            <span class="po-version-tag" :class="previewVersion.cls">{{ previewVersion.label }}</span>
            <div class="po-version-hint">{{ previewVersion.hint }}</div>
          </div>
          <div class="po-note" v-if="!internalExportPerm">成本价 / 利润率为对内数据，需管理员授予「导出对内版」权限</div>
          <div class="po-note">价格列由导出模板绑定决定，模板未绑定的分组勾选后无变化</div>
          <div class="po-refresh" v-if="revealRefreshing">正在刷新预览…</div>
        </div>
        <div class="preview-canvas">
          <UniverSheet
            v-if="previewSnapshot"
            ref="previewSheetRef"
            :workbookData="previewSnapshot"
            :editable="false"
          />
        </div>
      </div>
      <div v-else-if="previewType === 'spec'" class="spec-preview-wrap">
        <SpecSheet
          :configs="specPreviewConfigs"
          :config-relation="specConfigRelation"
          :primary-config="specPrimaryConfig"
          :branding="previewSpecBranding"
          :business-person="specBusinessPerson"
          :display-options="previewSpecDisplayOptions"
        />
      </div>
    </a-modal>

    <!-- 规格书打印 overlay：Teleport 到 body，复用 SpecSheet 的 @media print 规则 -->
    <Teleport to="body">
      <div v-if="printMode" class="spec-sheet-overlay">
        <div class="spec-sheet-scroll">
          <SpecSheet
            class="spec-sheet-root"
            :configs="specPreviewConfigs"
            :config-relation="specConfigRelation"
            :primary-config="specPrimaryConfig"
            :branding="previewSpecBranding"
            :business-person="specBusinessPerson"
            :display-options="previewSpecDisplayOptions"
          />
        </div>
      </div>
    </Teleport>
    <!-- 机箱配置弹窗：L6 四步（基准 / 前 / 后面板 / 电源）— active config 的 base_config_id 驱动 -->
    <a-modal
      v-model:open="chassisModalOpen"
      :title="`${activeConfig?.server_model || '机型'} · 机箱配置`"
      :footer="null"
      width="1120px"
      wrap-class-name="chassis-modal-quote"
      :force-render="true"
    >
      <L6ChassisConfig
        :key="activeCfg"
        stepper
        :price-visible="priceVisible"
        :show-gpu-cable="activeConfig?.bom_source === 'excel'"
        :base-config-id="activeConfig?.base_config_id ?? null"
        :server-model-id="activeConfig?.server_model_id ?? null"
        :kp-summary="kpSummaryFor(activeConfig)"
        :initial-picks="activeConfig?.l6_bom_picks"
        @apply="(p: any) => store.setL6ChassisPicks(activeCfg, p)"
      />
    </a-modal>

    <!-- KP 同步价格弹窗 -->
    <a-modal
      v-model:open="syncVisible"
      title="同步到 KP 配件库"
      :confirm-loading="syncLoading"
      :width="460"
      ok-text="确认同步"
      cancel-text="取消"
      @ok="confirmSync"
    >
      <div v-if="syncTarget" class="sync-modal">
        <div class="sync-row">
          <span class="sync-label">类别</span>
          <span class="sync-val">{{ syncTarget.part_category || 'Key Parts' }}</span>
        </div>
        <div v-if="syncTargetCategory && syncTargetCategory !== (syncTarget.part_category || 'Key Parts')" class="sync-row">
          <span class="sync-label">实际入库分类</span>
          <span class="sync-val">{{ syncTargetCategory }}</span>
        </div>
        <div class="sync-row">
          <span class="sync-label">型号</span>
          <span class="sync-val">{{ syncTarget.catalogue || syncTarget.part_category }}</span>
        </div>
        <div class="sync-row">
          <span class="sync-label">价格</span>
          <span class="sync-val sync-price-edit">
            <template v-if="priceVisible">
              <a-input-number v-model:value="syncPrice" size="small" class="sync-price-inp" :min="0" :precision="2" :controls="false" placeholder="入库价格" />
              <a-select v-model:value="syncCurrency" size="small" class="sync-cur-sel" :options="SYNC_CURRENCIES" />
            </template>
            <span v-else class="price-hidden">***</span>
          </span>
        </div>
        <div class="sync-row sync-note">
          <span class="sync-label">备注</span>
          <a-textarea
            v-model:value="syncNote"
            :rows="2"
            :maxlength="200"
            show-count
            placeholder="可选：如客户、项目、调价原因"
          />
        </div>
        <div class="sync-hint" v-if="syncTarget && isNewPart(syncTarget)">
          配件库无此型号，确认后将<strong>创建一条新配件记录</strong>并写入其首条价格历史。如需补全 brand / 规格，可在管理面「配件管理」编辑该新件。
        </div>
        <div class="sync-hint" v-else>确认后将把以上价格与备注写入配件库该型号的价格历史。</div>
      </div>
    </a-modal>

    <!-- KP 历史价格弹窗 -->
    <a-modal
      v-model:open="kpHistoryVisible"
      :title="`历史价格 — ${kpHistoryItem?.catalogue || kpHistoryItem?.part_category || ''}`"
      :width="520"
      :footer="null"
    >
      <div class="kp-history-modal" v-if="kpHistoryItem">
        <div class="kp-hist-meta">
          <span class="kp-hist-meta-cat">{{ kpHistoryItem.part_category }}</span>
          <span class="kp-hist-meta-name">{{ kpHistoryItem.catalogue }}</span>
        </div>
        <div v-if="kpHistoryItem._histLoading" class="kp-hist-loading"><a-spin size="small" /></div>
        <div v-else-if="kpHistoryItem._history?.length" class="kp-hist-list">
          <div v-for="(h, hi) in kpHistoryItem._history" :key="h.id ?? hi" class="kp-hist-item">
            <div class="kp-hist-dot"></div>
            <div class="kp-hist-content">
              <!-- 最新一条：可原地修改（录错价就近修正，免跑去配件库） -->
              <template v-if="hi === 0 && priceVisible && histEditingId !== h.id">
                <div class="kp-hist-row">
                  <span class="kp-hist-date">{{ h.date }} <span class="kp-hist-latest">最新</span></span>
                  <span class="kp-hist-head">
                    <span class="kp-hist-price" :class="{ usd: h.currency === 'USD' }">
                      {{ h.currency === 'USD' ? '$' : '¥' }} {{ settingsStore.formatNumber(h.price || 0) }}
                    </span>
                    <a-button size="small" type="link" class="kp-hist-edit-btn" @click="startHistEdit(h)">修改</a-button>
                  </span>
                </div>
                <div v-if="h.note" class="kp-hist-note">{{ h.note }}</div>
              </template>
              <!-- 最新一条编辑态 -->
              <div v-else-if="histEditingId === h.id" class="kp-hist-edit">
                <div class="kp-hist-edit-row">
                  <a-input-number v-model:value="histEditPrice" size="small" class="kp-hist-edit-price" :min="0" :precision="2" :controls="false" placeholder="价格" />
                  <a-select v-model:value="histEditCurrency" size="small" class="kp-hist-edit-cur" :options="SYNC_CURRENCIES" />
                </div>
                <a-input v-model:value="histEditNote" size="small" placeholder="备注（如：价格录错，已更正）" :maxlength="200" />
                <div class="kp-hist-edit-actions">
                  <a-button size="small" @click="cancelHistEdit">取消</a-button>
                  <a-button size="small" type="primary" :loading="histEditSaving" @click="saveHistEdit">保存</a-button>
                </div>
              </div>
              <!-- 历史条目：只读 -->
              <template v-else>
                <div class="kp-hist-row">
                  <span class="kp-hist-date">{{ h.date }}</span>
                  <span class="kp-hist-price" :class="{ usd: h.currency === 'USD' }">
                    {{ h.currency === 'USD' ? '$' : '¥' }} {{ settingsStore.formatNumber(h.price || 0) }}
                  </span>
                </div>
                <div v-if="h.note" class="kp-hist-note">{{ h.note }}</div>
              </template>
            </div>
          </div>
        </div>
        <div v-else class="kp-hist-empty">暂无历史价格</div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed, h, nextTick, defineAsyncComponent } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQuoteStore, type ConfigData, type Item } from '@/store/quote'
import { usePricingRulesStore } from '@/stores/pricingRules'
import { useSelectionRulesStore } from '@/stores/selectionRules'
import { normalizeDriveKind } from '@/stores/selectionEngine'
import { alertIcon } from '@/constants/ruleMeta'
import { useSettingsStore } from '@/store/settings'
import { useAuthStore } from '@/store/auth'
import ChassisCard from '@/components/server-config/ChassisCard.vue'
import PriceTriple from '@/components/common/PriceTriple.vue'
import BomTable from '@/components/BomTable.vue'
import CountNumber from '@/components/common/CountNumber.vue'
import { message, Modal } from 'ant-design-vue'
import { LeftOutlined, RightOutlined } from '@ant-design/icons-vue'
import axios from 'axios'
import { univerTemplateApi } from '@/api/univerTemplate'
import { specTemplateApi } from '@/api/specTemplate'
import type { SpecTemplate, PreviewConfig } from '@/types/specTemplate'
import { DEFAULT_BRANDING } from '@/utils/defaultTemplateConfig'
import { partsApi } from '@/api/serverConfig'
import { syncKpPrice, getKpHistory, updateKpPriceHistory, normalizeKpCategory } from '@/api/quote'
import { quotationApi } from '@/api'
import { downloadBlob } from '@/utils/download'
import { calcUnitCost, computeKpMatch, isNewPart, kpSyncable, matchClass, safeServerModelFilename } from '@/utils/quoteCommon'
import { feedApi } from '@/api/feed'
import { fromPartMaster } from '@/composables/usePartAdapter'
import type { PickerItem } from '@/types/picker'
import type { GpuArch } from '@/composables/useServerConfig'
import { useQuoteServerModels } from '@/composables/useQuoteServerModels'
import { CORE_KP_CATS, useQuoteKpCatalog } from '@/composables/useQuoteKpCatalog'

const UniverSheet = defineAsyncComponent(() => import('@/components/UniverSheet.vue'))
const L6ChassisConfig = defineAsyncComponent(() => import('@/components/quote/L6ChassisConfig.vue'))
const KpCategoryCard = defineAsyncComponent(() => import('@/components/server-config/KpCategoryCard.vue'))
const SpecSheet = defineAsyncComponent(() => import('@/components/server-config/SpecSheet.vue'))

const store = useQuoteStore()
const pricingRulesStore = usePricingRulesStore()
const selectionRulesStore = useSelectionRulesStore()
const settingsStore = useSettingsStore()
const auth = useAuthStore()
/** 报价工作台价格可见性（字段级权限，配置驱动） */
const priceVisible = computed(() => auth.can('field.quote.price'))
const route = useRoute()
const router = useRouter()
const activeCfg = ref('CFG1')
const leftCollapsed = ref(false)

// 导出模板相关（Excel + 规格书两套，选择器合并；value 编码 'excel:5' / 'spec:3' 消歧 id 重叠）
const templates = ref<any[]>([])
const specTemplates = ref<SpecTemplate[]>([])
const selectedTemplateValue = ref<string>('')
const selectedTemplate = computed<{ type: 'excel' | 'spec'; id: number } | null>(() => {
  const v = selectedTemplateValue.value
  if (!v) return null
  const [type, idStr] = v.split(':')
  if (type !== 'excel' && type !== 'spec') return null
  const id = Number(idStr)
  return Number.isFinite(id) ? { type, id } : null
})
const previewLoading = ref(false)
const previewVisible = ref(false)
const previewSnapshot = ref<Record<string, any> | null>(null)
// 规格书预览：后端 preview-data 喂 configs + 选中模板的 branding/display_options 驱动 SpecSheet
const previewType = ref<'excel' | 'spec'>('excel')
const specPreviewConfigs = ref<PreviewConfig[]>([])
const specConfigRelation = ref<'compose' | 'alternative'>('compose')
const specPrimaryConfig = ref<string>('')
const specPreviewTemplate = ref<SpecTemplate | null>(null)
const specBusinessPerson = ref('')
const previewSpecBranding = computed(() => specPreviewTemplate.value?.branding || DEFAULT_BRANDING)
const previewSpecDisplayOptions = computed(() => specPreviewTemplate.value?.display_options)

// 导出选项：敏感分组揭示（服务端按 reveal + 权限二次过滤，前端开关只是交互层）
const internalExportPerm = computed(() => auth.can('field.quote.export_internal'))
const revealSell = ref(false)
const revealCost = ref(false)
const revealMargin = ref(false)
const revealRefreshing = ref(false)
const revealGroups = computed(() => {
  const g: string[] = []
  if (revealSell.value) g.push('sell')
  if (internalExportPerm.value && revealCost.value) g.push('cost')
  if (internalExportPerm.value && revealMargin.value) g.push('margin')
  return g
})
const isInternalVersion = computed(() => revealGroups.value.includes('cost') || revealGroups.value.includes('margin'))
const previewVersion = computed(() => {
  if (isInternalVersion.value) {
    return { label: '对内版', cls: 'pv-internal', hint: '含成本/利润率，仅供内部使用；导出不冻结报价单' }
  }
  if (revealSell.value) {
    return { label: '客户版 · 含明细价', cls: 'pv-sell', hint: '含明细行售价；导出后冻结报价单' }
  }
  return { label: '客户版', cls: 'pv-customer', hint: '不含敏感列；导出后冻结报价单' }
})

// 按当前导出选项重新拉取 Excel 预览快照（勾选变化 / 首次预览共用）
async function fetchPreviewSnapshot() {
  const sel = selectedTemplate.value
  if (!sel || sel.type === 'spec') return
  const opportunityId = store.opportunityInfo.opportunity_id
  const quotationId = store.opportunityInfo.quotation_id || (route.query.quotationId as string)
  const result = await univerTemplateApi.preview(sel.id, opportunityId, quotationId, undefined, revealGroups.value)
  previewSnapshot.value = result.workbook_snapshot
}

async function onRevealChange() {
  if (previewType.value !== 'excel' || revealRefreshing.value) return
  revealRefreshing.value = true
  try {
    await fetchPreviewSnapshot()
  } catch (e) {
    console.error('刷新预览失败', e)
    message.error('刷新预览失败，请重试')
  } finally {
    revealRefreshing.value = false
  }
}
const printMode = ref(false)

// KP 同步价格弹窗
const syncVisible = ref(false)
const syncTarget = ref<any>(null)
const syncTargetCategory = ref('')
const syncNote = ref('')
const syncLoading = ref(false)
// 弹窗内可改的入库价格/币种（默认取行上的值，改完写回行再入库）
const syncPrice = ref(0)
const syncCurrency = ref('RMB')
const SYNC_CURRENCIES = [
  { value: 'RMB', label: '¥ RMB' },
  { value: 'USD', label: '$ USD' },
]

// KP 历史价格弹窗
const kpHistoryVisible = ref(false)
const kpHistoryItem = ref<Item | null>(null)

// 历史弹窗内原地修改「最新一条」（后端乐观锁：仅最新条可改）
const histEditingId = ref<number | null>(null)
const histEditPrice = ref(0)
const histEditCurrency = ref('RMB')
const histEditNote = ref('')
const histEditSaving = ref(false)

function startHistEdit(h: any) {
  histEditingId.value = h.id
  histEditPrice.value = Number(h.price) || 0
  histEditCurrency.value = String(h.currency || 'RMB').toUpperCase() === 'USD' ? 'USD' : 'RMB'
  histEditNote.value = h.note || ''
}

function cancelHistEdit() {
  histEditingId.value = null
}

// 保存改历史：刷新弹窗列表 + 全配置页同型号的库参考价（db_price/db_currency/match_status）
async function saveHistEdit() {
  const item = kpHistoryItem.value
  const id = histEditingId.value
  if (!item || id == null) return
  const price = Number(histEditPrice.value)
  if (!(price > 0)) { message.warning('请输入大于 0 的价格'); return }
  histEditSaving.value = true
  try {
    await updateKpPriceHistory(id, {
      price,
      currency: histEditCurrency.value,
      note: histEditNote.value.trim(),
    })
    item._history = await getKpHistory(item.catalogue, item.part_category)
    item._histLoaded = true
    // 行的 db 快照与所有配置页同型号行一并刷新（库里最新价已变；只动库参考价，不动各行报价）
    const model = item.catalogue
    const latest = item._history?.[0] || null
    for (const cfg of Object.values(store.configs)) {
      for (const it of cfg.items) {
        if (it.category !== 'Key Parts') continue
        if ((it.catalogue || '') !== model) continue
        it.db_price = latest ? Number(latest.price) : null
        it.db_currency = latest ? (latest.currency || 'RMB') : null
        computeKpMatch(it)
      }
    }
    histEditingId.value = null
    message.success('已修改最新价')
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : '修改失败：' + (e?.message || e))
  } finally {
    histEditSaving.value = false
  }
}

// 当前激活配置（机箱卡 + 弹窗引用；v-for 内只有 active config 渲染，故单一 modal 即可）
const activeConfig = computed(() => store.configs[activeCfg.value])

// ── 手机端（≤768）：三栏 → 双抽屉。左抽屉=BOM 对照快照，右抽屉=定价与利润（含预览导出），
//     主屏=中栏编辑区；底部 sticky 摘要条常驻含税总价/毛利/保存（桌面三栏不受影响） ──
const isMobile = ref(false)
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null
const openDrawer = ref<null | 'bom' | 'fin'>(null)
const bomDrawerOpen = computed({
  get: () => openDrawer.value === 'bom',
  set: (v: boolean) => { openDrawer.value = v ? 'bom' : null },
})
const finDrawerOpen = computed({
  get: () => openDrawer.value === 'fin',
  set: (v: boolean) => { openDrawer.value = v ? 'fin' : null },
})
onMounted(() => {
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
  const mq = window.matchMedia('(max-width: 768px)')
  _mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', _mqListener)
})
onBeforeUnmount(() => {
  if (_mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', _mqListener)
})
const {
  serverModels,
  chassisModalOpen,
  loadServerModels,
  loadBaseInfo,
  backfillServerModelId,
  baseInfoCache,
  chassisModel,
  chassisSeries,
  chassisBaseName,
  chassisForm,
  chassisBays,
  chassisMatched,
  serverModelOptions,
  onServerModelSelect,
} = useQuoteServerModels(activeConfig)

const {
  kpCatalog,
  pickerCatalog,
  kpPartByPn,
  priceOf,
  kpCardCatsFor,
  kpLinesForCat,
  newKpItem,
  onKpSetLine,
  onKpDelLine,
  onKpAddLine,
  onKpRemoveCard,
  availableKpCats,
  pendingNewKpCat,
  onAddKpCard,
  loadKpCatalog,
} = useQuoteKpCatalog(store, activeConfig)
function persistTaxRate() {
  axios.put('/api/system-config/tax_rate', { value: store.taxRate }).catch(() => {})
}
function persistExchangeRate() {
  axios.put('/api/system-config/usd_to_rmb', { value: store.exchangeRate }).catch(() => {})
}

// GPU 架构（per-config，存 cfg.gpu_arch；kpSummary 优先用它驱动 GPU 线缆推导）
// GPU 供电线（quoteMode GPU 卡）：料号库列表 + 状态写回 cfg.l6_bom_picks.overrides，
// 由常驻 L6ChassisConfig 的 watch 同步进内部 overrides → 重算 GPU 线成本 → apply 进 l6_custom_price
const gpuCableItems = ref<PickerItem[]>([])
async function loadGpuCableItems() {
  try {
    // GPU 供电线归入「电源分配线缆·后面板」，按 PN/name 含 GPU 筛选
    const res = await partsApi.list({ category: '电源分配线缆', major_category: '后面板' })
    gpuCableItems.value = (res.parts || []).filter((p: any) => /gpu/i.test(p.pn) || /gpu/i.test(p.name || '')).map(fromPartMaster)
  } catch { /* 料号库暂无，GPU 卡显示空态 */ }
}
function setGpuCable(cfg: ConfigData, field: 'pn' | 'qty', value: string | number) {
  if (!cfg.l6_bom_picks) cfg.l6_bom_picks = { overrides: {} }
  if (!cfg.l6_bom_picks.overrides) cfg.l6_bom_picks.overrides = {}
  ;(cfg.l6_bom_picks.overrides as any)[field === 'pn' ? 'gpuCablePn' : 'gpuCableQty'] = value
}

// 加载导出模板列表
const loadTemplates = async () => {
  try {
    const [list, specList] = await Promise.all([
      univerTemplateApi.list(),
      specTemplateApi.list().catch(() => [] as SpecTemplate[]),
    ])
    templates.value = list
    specTemplates.value = specList
    // 默认选 Excel 默认模板；无 Excel 才回落规格书默认/首条
    const defaultExcel = list.find((t: any) => t.is_default)
    if (defaultExcel) {
      selectedTemplateValue.value = 'excel:' + defaultExcel.id
    } else if (list.length) {
      selectedTemplateValue.value = 'excel:' + list[0].id
    } else if (specList.length) {
      const defaultSpec = specList.find((t) => t.is_default) || specList[0]
      selectedTemplateValue.value = 'spec:' + defaultSpec.id
    }
  } catch (e) {
    console.error('加载模板列表失败', e)
  }
}

// 预览处理：按选中模板类型分流——Excel 走 Univer 快照，规格书走 SpecSheet（后端 preview-data）
const handlePreview = async () => {
  const sel = selectedTemplate.value
  if (!sel) {
    message.warning('请先选择导出模板')
    return
  }

  previewLoading.value = true
  try {
    const opportunityId = store.opportunityInfo.opportunity_id
    if (!opportunityId) {
      message.error('商机信息不完整')
      return
    }
    const quotationId = store.opportunityInfo.quotation_id || (route.query.quotationId as string)

    if (sel.type === 'spec') {
      // getById 拿详情（含 display_options/branding）；list 只返回精简元数据，缺这俩会让模板的显示开关失效
      const [data, tpl] = await Promise.all([
        specTemplateApi.getPreviewData(opportunityId, quotationId),
        specTemplateApi.getById(sel.id),
      ])
      specPreviewConfigs.value = data.configs || []
      specConfigRelation.value = (data.config_relation || 'compose') as 'compose' | 'alternative'
      specPrimaryConfig.value = data.primary_config || ''
      specBusinessPerson.value = data.business_person || ''
      specPreviewTemplate.value = tpl
      if (!specPreviewConfigs.value.length) {
        message.info('该商机/报价单暂无配置数据，请先在报价单中添加配置')
        return
      }
      previewType.value = 'spec'
      previewVisible.value = true
    } else {
      await fetchPreviewSnapshot()
      previewType.value = 'excel'
      previewVisible.value = true
    }
  } catch (e) {
    console.error('预览失败', e)
    message.error('预览失败，请重试')
  } finally {
    previewLoading.value = false
  }
}

// 模态框确认按钮：Excel → 下载 xlsx，规格书 → 打印为 PDF
function handleModalOk() {
  if (previewType.value === 'spec') handlePrintSpec()
  else handleDownloadExport()
}

// 规格书打印：Teleport overlay + window.print，复用 SpecSheet 的 @media print 规则（同 SpecTemplateEditor）
async function handlePrintSpec() {
  if (!specPreviewConfigs.value.length) {
    message.warning('暂无可打印的配置数据')
    return
  }
  printMode.value = true
  await nextTick()
  fitPagesForPrint()
  const prevTitle = document.title
  document.title = buildPrintTitle()
  window.addEventListener('afterprint', () => {
    document.title = prevTitle
    printMode.value = false
  }, { once: true })
  window.print()
}

function buildPrintTitle() {
  const b = specPreviewTemplate.value?.branding
  const date = new Date().toLocaleDateString('zh-CN')
  return [b?.doc_title || '规格书', b?.company_name, date].filter((s) => s && s.trim()).join('-')
}

// 打印前按 A4 可打印区缩放每个配置页，保证「一配置一页」、末尾不溢出
function fitPagesForPrint() {
  const PRINT_W = ((210 - 28) * 96) / 25.4
  const PRINT_H = ((297 - 28) * 96) / 25.4
  document.querySelectorAll<HTMLElement>('.spec-sheet-overlay .ss-page').forEach((page) => {
    const clone = page.cloneNode(true) as HTMLElement
    clone.style.minHeight = 'auto'
    clone.style.height = 'auto'
    clone.style.padding = '0'
    clone.style.width = '100%'
    clone.style.transform = ''
    const meter = document.createElement('div')
    meter.style.cssText = `position:absolute;left:-99999px;top:0;width:${PRINT_W}px;visibility:hidden;`
    meter.appendChild(clone)
    document.body.appendChild(meter)
    const naturalH = clone.scrollHeight
    document.body.removeChild(meter)
    const scale = naturalH > 0 ? Math.min(1, PRINT_H / naturalH) : 1
    page.style.setProperty('--print-scale', String(scale))
    page.style.setProperty('--print-h', scale < 1 ? `${Math.round(naturalH * scale)}px` : 'auto')
  })
}

// 预览弹窗内「下载 Excel」：从 live Univer 实例读已解析样式 → exceljs 写出（WYSIWYG）
const previewSheetRef = ref<any>(null)
const exportDownloading = ref(false)
async function handleDownloadExport() {
  const wb = previewSheetRef.value?.getResolvedWorkbook?.()
  if (!wb || !wb.sheets.length) {
    message.warning('工作簿尚未就绪，请稍候重试')
    return
  }
  exportDownloading.value = true
  try {
    const { resolvedWorkbookToXlsx } = await import('@/utils/xlsx-exporter')
    const blob = await resolvedWorkbookToXlsx(wb)
    const oid = store.opportunityInfo?.opportunity_id || '报价单'
    const serverModel = safeServerModelFilename(activeConfig.value?.server_model)
    const fname = `CloudPrime-${serverModel}-${oid}_报价单${isInternalVersion.value ? '_对内版' : ''}.xlsx`
    downloadBlob(blob, fname)
    if (isInternalVersion.value) {
      // 对内版（含成本/利润率）：只归档到内部附件，不冻结报价单、不落策略快照
      message.success('已导出对内版 Excel（未冻结报价单）')
      void archiveSentQuote(blob, oid, fname, 'internal_quote')
    } else {
      message.success('已导出 Excel')
      // 归档一份到商机存档区(sent_quote),失败不阻断导出
      void archiveSentQuote(blob, oid, fname)
      // 冻结草稿为「已导出」+ 落成本快照：失败只警告，不阻断已下载的文件
      await freezeExportedQuotation()
    }
  } catch (e: any) {
    console.error('[handleDownloadExport]', e)
    message.error('导出失败：' + (e?.message || e))
  } finally {
    exportDownloading.value = false
  }
}

// 机型信息解析（与机箱卡同源）：机型目录按 server_model_id / 型号名命中 → 取基准配置；
// 都没命中时用已加载的基准配置信息（base_config_id）。拿不到的字段留空，抽屉显示 —。
function modelInfoOf(cfg: ConfigData) {
  const model = serverModels.value.find((m) => m.id === cfg.server_model_id)
    || serverModels.value.find((m) => m.name === cfg.server_model)
  const bc = (model as any)?.base_config
  const cached = cfg.base_config_id ? baseInfoCache.value[cfg.base_config_id] : undefined
  return {
    server_model: cfg.server_model || '',
    server_model_id: cfg.server_model_id ?? null,
    base_config_id: cfg.base_config_id ?? null,
    description: cfg.description || '',
    series: bc?.series || cached?.series || '',
    form: bc?.form || cached?.form || '',
    bays: bc?.bays ?? cached?.bays ?? null,
    base_config_name: bc?.name || cached?.name || '',
  }
}

// 组装成本快照：逐配置 getConfigTotals + 机箱分段 + 财务常量，跨配置汇总
function buildCostSnapshot(): Record<string, any> {
  const cfgNames = Object.keys(store.configs)
  const cfgSnap: Record<string, any> = {}
  // 项目总计：compose 按各配置台数加权（Σ 单台 × qty）；alternative 只取主推方案 × 需求台数（不求和）
  const projSum = { totalCost: 0, totalSales: 0, profit: 0 }
  for (const name of cfgNames) {
    const cfg: ConfigData = store.configs[name]
    const t = store.getConfigTotals(name)
    const qty = store.configQuantities[name] ?? 0
    const rate = store.exchangeRate
    const tax = store.taxRate
    // KP 逐项明细（分类/名称/数量/成本/售价/利润率），口径与 calcConfigTotals 一致：
    //   USD 项 base × 汇率 × (1+税)；RMB 项 base。L6/整机/Warranty 不计入 KP。
    const kpItems: { cat: string; name: string; qty: number; cost: number; sales: number; margin: number }[] = []
    for (const it of (cfg.items || [])) {
      if (it.category === 'L6' || it.category === '整机' || it.category === 'Warranty') continue
      const base = Number(it.base_price || 0)
      const itemQty = Number(it.qty || 1)
      const marginRaw = Number(it.profit_margin || 0)
      // 售价口径与 calcConfigTotals 对齐：缺省利润率按 10
      const mForSales = Number(it.profit_margin) || 10
      const isUsd = it.currency === 'USD'
      const unitCost = isUsd ? base * rate * (1 + tax) : base
      const unitSales = isUsd
        ? base * rate * (1 + tax) * (1 + mForSales / 100)
        : base * (1 + (mForSales > 1 ? mForSales / 100 : mForSales))
      kpItems.push({
        cat: it.part_category || '其他',
        name: it.catalogue || '',
        qty: itemQty,
        cost: unitCost * itemQty,
        sales: unitSales * itemQty,
        margin: marginRaw,
      })
    }
    // 机型信息一并冻结：抽屉只读复核不依赖机型目录（目录后改不影响已冻结单）
    cfgSnap[name] = { qty, totals: t, kp_items: kpItems, ...modelInfoOf(cfg) }
    if (isAlternative.value) {
      if (name === primaryConfig.value) {
        projSum.totalCost += (t.totalCost || 0) * demandQty.value
        projSum.totalSales += (t.totalSales || 0) * demandQty.value
        projSum.profit += (t.profit || 0) * demandQty.value
      }
    } else {
      projSum.totalCost += (t.totalCost || 0) * qty
      projSum.totalSales += (t.totalSales || 0) * qty
      projSum.profit += (t.profit || 0) * qty
    }
  }
  const marginPct = projSum.totalCost > 0 ? (projSum.profit / projSum.totalCost) * 100 : 0
  return {
    captured_at: new Date().toISOString(),
    rates: { usd_to_rmb: store.exchangeRate, tax_rate: store.taxRate },
    config_relation: store.opportunityInfo.config_relation || 'compose',
    primary_config: store.opportunityInfo.primary_config || '',
    totals: { ...projSum, marginPct: Math.round(marginPct * 100) / 100 },
    configs: cfgSnap,
  }
}

// 导出后冻结：POST 快照 → 后端盖 exported_at。失败提示但不影响已下载文件。
async function freezeExportedQuotation() {
  const quotationId = store.opportunityInfo?.quotation_id || (route.query.quotationId as string)
  if (!quotationId) return
  try {
    await quotationApi.export(quotationId, buildCostSnapshot())
    // L3 策略溯源快照：记录加法引擎对该 deal 的定价依据（失败不阻断导出）
    const oi = store.opportunityInfo
    const oia = oi as any
    const snap = pricingRulesStore.getStrategySnapshot({
      platform: oi?.platform_type,
      industry: oia?.industry,
      region: oia?.delivery_region ?? oia?.extra_fields?.delivery_region,
      // 订单维度用 customer_type 枚举(BusinessField 存 extra_fields,与 order_mult 系数表同域);order_type 自由文本仅兜底
      customerType: oia?.extra_fields?.customer_type ?? oi?.order_type,
      form: oia?.chassis_form ?? null,
      cost: configTotals.value?.totalCost ?? null,
      qty: oia?.purchase_qty ?? null,
    })
    quotationApi.update(quotationId, { strategy_snapshot: snap }).catch(() => {})
  } catch (e: any) {
    console.warn('[freezeExportedQuotation] 状态未更新', e)
    message.warning('报价单状态未更新为已导出，请重新导出')
  }
}

// 把导出的报价单 xlsx 归档到商机存档区(sent_quote 类),并自动写一条系统活动。
// 对内版走 internal_quote 类（含成本/利润率的内部留底）。纯属留底,任何失败都静默 —— 不能影响导出主流程。
async function archiveSentQuote(blob: Blob, opportunityId: string, fname: string, category: string = 'sent_quote') {
  try {
    const quotationId = store.opportunityInfo?.quotation_id || (route.query.quotationId as string)
    const file = new File([blob], fname, { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    await feedApi.attachments.upload(opportunityId, file, { category, quotation_id: quotationId, kind: 'export' })
  } catch (e) {
    console.warn('归档已发报价失败(不影响导出)', e)
  }
}

// 质保描述默认值（从系统配置获取）
const warrantyDescDefaults = ref<{ l6: string; kp: string }>({
  l6: '',
  kp: ''
})

// 加载系统配置中的质保描述默认值
const loadWarrantyDefaults = async () => {
  try {
    const [l6Res, kpRes] = await Promise.all([
      axios.get('/api/system-config/warranty_desc_l6'),
      axios.get('/api/system-config/warranty_desc_kp')
    ])
    warrantyDescDefaults.value.l6 = l6Res.data?.value || ''
    warrantyDescDefaults.value.kp = kpRes.data?.value || ''
  } catch (e) {
    console.warn('Failed to load warranty defaults:', e)
  }
}

const getWarrantyDesc = (cfg: ConfigData, type: 'l6' | 'kp'): string => {
  const desc = cfg.warranty_info?.[type]?.description
  if (desc) return desc
  return warrantyDescDefaults.value[type] || ''
}
// 维保年限 → 费率映射（%），L6 与 KP 统一：1 年 0%、3 年 3%、5 年 5%。
// 切年限即按映射重置该类型费率。
const WARRANTY_RATE_BY_YEARS: Record<'l6' | 'kp', Record<number, number>> = {
  l6: { 1: 0, 3: 3, 5: 5 },
  kp: { 1: 0, 3: 3, 5: 5 },
}
function onWarrantyYearsChange(cfgName: string, type: 'l6' | 'kp', years: number | null) {
  // allowClear 清空时 years 为 undefined/null：置空年限，不设费率、不动描述
  const yrs = years ?? null
  if (type === 'l6') store.setWarrantyYearsL6(cfgName, yrs)
  else store.setWarrantyYearsKP(cfgName, yrs)
  if (yrs == null) return
  const rate = WARRANTY_RATE_BY_YEARS[type][yrs]
  if (rate !== undefined) {
    if (type === 'l6') store.setWarrantyRateL6(cfgName, rate)
    else store.setWarrantyRateKP(cfgName, rate)
  }
  // 描述联动：把「质保X年」的 X 换成新年限。宽松匹配（[^，,。；;] 兼容历史"质保undefined年"等异常值）；
  // 文本可自由编辑，仅在匹配该模式时替换、其余不动。
  const cfg = store.configs[cfgName]
  const cur = cfg?.warranty_info?.[type]?.description || warrantyDescDefaults.value[type] || ''
  if (/质保[^，,。；;]*年/.test(cur)) {
    store.setWarrantyDescription(cfgName, type, cur.replace(/质保[^，,。；;]*年/, `质保${yrs}年`))
  }
}
const saveLoading = ref(false)

// 入口上下文（来自路由 query）: upload | opportunities
const entryFrom = computed(() => (route.query.from as string) || 'upload')
const entryProjectId = computed(() => (route.query.opportunityId as string) || '')
const entryLabel = computed(() => {
  if (entryFrom.value === 'opportunities') return '← 返回商机详情'
  if (entryFrom.value === 'upload') return '← 返回上传页'
  return ''
})
const goBack = () => {
  if (entryFrom.value === 'opportunities' && entryProjectId.value) {
    router.push(`/opportunities/${entryProjectId.value}`)
  } else if (entryFrom.value === 'upload') {
    router.push('/upload')
  } else {
    router.push('/opportunities')
  }
}

// 每个配置页的栏目状态（独立维护）
const sectionState = reactive<Record<string, string>>({})

// 每个配置页的描述框展开状态
const descExpanded = reactive<Record<string, boolean>>({})

// 配置 Tab 编辑状态（双击重命名）
const editingCfg = ref<string | null>(null)
const editingName = ref('')

// 配置 Tab 右键菜单
const contextMenu = reactive<{ visible: boolean; x: number; y: number; cfgName: string }>({
  visible: false, x: 0, y: 0, cfgName: ''
})

// 开始重命名
const startRename = (cfgName: string) => {
  editingCfg.value = cfgName
  editingName.value = cfgName
}

// 确认重命名
const confirmRename = () => {
  if (!editingCfg.value || !editingName.value.trim()) {
    editingCfg.value = null
    return
  }
  const oldName = editingCfg.value
  const newName = editingName.value.trim()

  if (oldName === newName) {
    editingCfg.value = null
    return
  }

  // 检查是否已存在
  if (store.configs[newName]) {
    message.error(`配置 "${newName}" 已存在`)
    return
  }

  // 重命名：复制数据，删除旧 key
  const oldCfg = store.configs[oldName]
  store.configs[newName] = { ...oldCfg, name: newName }
  delete store.configs[oldName]

  // 更新栏目状态
  if (sectionState[oldName]) {
    sectionState[newName] = sectionState[oldName]
    delete sectionState[oldName]
  }

  // 更新当前激活的配置
  if (activeCfg.value === oldName) {
    activeCfg.value = newName
  }

  editingCfg.value = null
  message.success(`已重命名为 "${newName}"`)

  // 自动保存，将重命名持久化到数据库
  if (store.opportunityInfo.quotation_id) {
    store.saveProject()
  }
}

// 取消重命名
const cancelRename = () => {
  editingCfg.value = null
}

// 右键菜单处理
const handleTabContextMenu = (e: MouseEvent, cfgName: string) => {
  e.preventDefault()
  contextMenu.visible = true
  contextMenu.x = e.clientX
  contextMenu.y = e.clientY
  contextMenu.cfgName = cfgName
}

// 关闭右键菜单
const closeContextMenu = () => {
  contextMenu.visible = false
}

// 删除配置
const deleteConfig = (cfgName: string) => {
  delete store.configs[cfgName]
  delete store.configQuantities[cfgName]  // 同步删除配置数量
  delete sectionState[cfgName]

  // 方案备选：删除主推配置时回退到首个剩余配置
  if (isAlternative.value && store.opportunityInfo.primary_config === cfgName) {
    store.opportunityInfo.primary_config = Object.keys(store.configs)[0] || ''
  }

  // 如果删除的是当前激活的配置，切换到第一个
  const remainingKeys = Object.keys(store.configs)
  if (activeCfg.value === cfgName) {
    activeCfg.value = remainingKeys[0] || ''
  }

  message.success(`已删除配置 "${cfgName}"`)

  // 自动保存，将删除持久化到数据库
  if (store.opportunityInfo.quotation_id) {
    store.saveProject()
  }
}

const deleteConfigWithConfirm = (cfgName: string) => {
  Modal.confirm({
    title: '删除配置',
    content: `确定删除配置 "${cfgName}" 吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk() {
      deleteConfig(cfgName)
    },
  })
}

// 初始化栏目状态
const initSectionState = () => {
  Object.keys(store.configs).forEach(name => {
    if (!sectionState[name]) {
      sectionState[name] = 'hardware'  // 默认显示硬件选配
    }
  })
}

// 添加配置页
const addConfig = () => {
  const existingKeys = Object.keys(store.configs)
  const nextNum = existingKeys.length + 1
  const newName = `CFG${nextNum}`
  store.configs[newName] = {
    name: newName,
    description: '',
    items: CORE_KP_CATS.filter(c => (kpCatalog.value[c] || []).length).map(c => newKpItem(c)),
    summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
    l6_matched_record: null,
    l6_custom_price: 0,
    l6_profit_margin: 10,
    bom_source: 'live',
    server_model: serverModels.value[0]?.name || '',
    server_model_id: serverModels.value[0]?.id,
    base_config_id: serverModels.value[0]?.base_config_id,
    gpu_arch: 'none',
    warranty_info: {
      l6: { detected: false, years: null as number | null, rate: 0 },
      kp: { detected: false, years: null as number | null, rate: 0 }
    } as any
  }
  if (serverModels.value[0]?.base_config_id) loadBaseInfo(serverModels.value[0].base_config_id)
  activeCfg.value = newName
  sectionState[newName] = 'hardware'
  if (isAlternative.value) {
    if (!store.opportunityInfo.primary_config) store.opportunityInfo.primary_config = newName
    const eq = Number(store.configQuantities[newName])
    if (!eq || eq <= 0) store.configQuantities[newName] = demandQty.value
  }
  message.success(`已添加配置页 ${newName}`)
}

// KP 成本合计：Σ(原币单价 × qty)，USD 项按汇率+税折算人民币，与 store.calcKpCost / summary 同口径
function kpCostTotal(cfg: ConfigData): number {
  return (cfg.items || [])
    .filter((i: any) => i.category === 'Key Parts')
    .reduce((s: number, i: any) =>
      s + calcUnitCost(Number(i.base_price) || 0, i.currency, store.exchangeRate, store.taxRate) * (Number(i.qty) || 1), 0)
}

// KP 整体利润率框的显示值：所有 KP 一致 → 该值；不一致/无 KP → undefined（框显示 placeholder「多种」）
function kpMarginValue(cfg: ConfigData): number | undefined {
  const kps = (cfg.items || []).filter((i: any) => i.category === 'Key Parts')
  if (kps.length === 0) return undefined
  const first = Number(kps[0].profit_margin) || 0
  return kps.every((i: any) => (Number(i.profit_margin) || 0) === first) ? first : undefined
}

// L6 最终售价 = 底价 × (1 + 利润率/100)；卡头 heroPrice 与三联售价槽共用，口径统一
function l6FinalPrice(cfg: ConfigData): number {
  return (Number(cfg.l6_custom_price) || 0) * (1 + (Number(cfg.l6_profit_margin) || 0) / 100)
}

// KP 最终售价合计：取 store 已算好的 summary.kp_total
function kpFinalPrice(cfg: ConfigData): number {
  return Number(cfg.summary?.kp_total) || 0
}

// 由当前配置的 KP 行合成 kpSummary，喂给 L6ChassisConfig 做 derive（best-effort）
// excel 解析的 KP spec 是模型串，未必匹配 kp_parts pn → derive 失败回落手选（[[derive-must-have-manual-fallback]]）
function kpSummaryFor(cfg: ConfigData) {
  const items = cfg?.items || []
  let cpuPn: string | undefined, cpuQty = 0
  let gpuPn: string | undefined, gpuQty = 0
  let hasGpu = false, highBwNic = false
  let raidModel = ''
  const drivesByKind: Record<string, number> = {}
  for (const it of items) {
    if (it.category !== 'Key Parts') continue
    // 类别（CPU/GPU/HDD…）现在存 part_category；型号/PN 存 catalogue
    const cat = (it.part_category || '').toLowerCase()
    const model = it.catalogue || ''
    if (cat.includes('cpu') || cat.includes('processor')) {
      cpuPn = model; cpuQty += (it.qty || 0)
    } else if (cat.includes('gpu')) {
      gpuPn = model; gpuQty += (it.qty || 0); hasGpu = true
    } else if (/raid|阵列|hba/.test(cat)) {
      // RAID 卡型号（"LSI 9560-8i 4G" → "9560"，Cable 行 SATA/SAS 文案前缀）
      const m = /(\d{3,4})[-\s]?(\d{1,2})\s*[iI]/.exec(`${it.description || ''} ${model}`)
      if (m) raidModel = m[1]
    } else if (/nic|网卡|网络/.test(cat) && /(100|200|400)\s*g/i.test(`${it.description || ''} ${it.catalogue || ''}`)) {
      highBwNic = true  // R26：100G+ 高带宽网卡（x16 卡）→ IO1 riser 升级 x16
    } else {
      // 盘类型：优先 KP 件结构化 specs（interface/kind/type，pn 查库）；缺失（无 pn / excel 新件）回退型号名嗅探（大小写无关）
      const spec = (it.pn ? kpPartByPn(it.pn)?.specs : null) as Record<string, any> | null
      const k = normalizeDriveKind(spec?.interface || spec?.kind || spec?.type)
        || normalizeDriveKind((it.part_category || '') + ' ' + (it.catalogue || ''))
      if (k) drivesByKind[k] = (drivesByKind[k] || 0) + (it.qty || 0)
    }
  }
  return { cpuPn, cpuQty, gpuPn, gpuQty, gpuArch: (cfg?.gpu_arch as GpuArch) || (hasGpu ? 'pt' : 'none'), drivesByKind, highBwNic, raidModel }
}

const handleSave = async () => {
  // 机箱按 4 部段（基准/前面板/后面板/电源）判 0；KP 等非机箱配件仍逐条列。
  // 机箱成本真实来源是 4 步选配的 l6_custom_price，cfg.items 里的 L6/整机 行（Excel 原版）不作为逐条判据。
  const blocks: { cfg: string; zeroSections: string[]; l6Coarse: number; kpParts: string[] }[] = []
  for (const [cfgName, cfg] of Object.entries(store.configs)) {
    const zeroSections: string[] = []
    let l6Coarse = 0
    const t = cfg.l6_section_totals
    if (t && typeof t === 'object') {
      const rearSum = (Number(t.rear) || 0) + (Number(t.ocp) || 0) + (Number(t.gpuCable) || 0)
      if (!(Number(t.base) > 0)) zeroSections.push('基准')
      if (!(Number(t.front) > 0)) zeroSections.push('前面板')
      if (!(rearSum > 0)) zeroSections.push('后面板')
      if (!(Number(t.psu) > 0)) zeroSections.push('电源')
    } else {
      // 未做 4 步选配（如纯 Excel）：粗粒度统计机箱行
      l6Coarse = (cfg.items || []).filter(i => (i.category === 'L6' || i.category === '整机') && (i.base_price === 0 || i.final_price === 0)).length
    }
    const kpParts = (cfg.items || []).filter(i => i.category !== 'L6' && i.category !== '整机' && (i.base_price === 0 || i.final_price === 0)).map(i => i.part_category || i.catalogue)
    if (zeroSections.length || l6Coarse > 0 || kpParts.length) {
      blocks.push({ cfg: cfgName, zeroSections, l6Coarse, kpParts })
    }
  }

  if (blocks.length > 0) {
    const chip = (text: string) => h('span', {
      style: 'display:inline-flex;align-items:center;padding:1px 9px;border-radius:10px;font-size:12px;background:var(--cpq-overlay-danger10);color:var(--cpq-accent-danger);border:1px solid var(--cpq-overlay-danger15);',
    }, text)
    const label = (text: string) => h('span', { style: 'color:var(--cpq-text-muted);font-size:12.5px;' }, text)

    const blockNodes = blocks.map(b => h('div', {
      style: 'margin-bottom:10px;padding:8px 12px;border-left:3px solid var(--cpq-accent-danger);background:var(--cpq-overlay-a4);border-radius:0 6px 6px 0;',
    }, [
      h('div', { style: 'font-weight:600;margin-bottom:5px;color:var(--cpq-text-primary);' }, b.cfg),
      h('div', { style: 'display:flex;flex-wrap:wrap;align-items:center;gap:6px;' }, [
        ...(b.zeroSections.length ? [label('机箱'), ...b.zeroSections.map(chip)] : []),
        ...(b.l6Coarse > 0 ? [h('span', { style: 'color:var(--cpq-text-secondary);font-size:12.5px;' }, `机箱 ${b.l6Coarse} 个部件价格为 0（未做 4 步选配）`)] : []),
        ...(b.kpParts.length ? [label('配件'), ...b.kpParts.map(chip)] : []),
      ]),
    ]))

    const confirmed = await Modal.confirm({
      title: '存在价格为 0 的项目',
      icon: () => h('span', { style: 'color:var(--cpq-accent-danger);font-size:18px;' }, '⚠️'),
      content: h('div', { style: 'font-size:13px;line-height:1.7;color:var(--cpq-text-primary);' }, [
        h('div', { style: 'color:var(--cpq-text-secondary);margin-bottom:12px;' }, '以下配置存在价格为 0 的项目，可能导致整机成本偏低：'),
        ...blockNodes,
      ]),
      okText: '继续保存',
      cancelText: '取消',
      okType: 'danger',
    })
    if (!confirmed) return
  }

  warnLowMarginIfNeeded()

  saveLoading.value = true
  try {
    await store.saveProject()
  } finally {
    saveLoading.value = false
  }
}

// 当前配置页的财务数据（随 tab 切换动态变化，使用 computed 确保响应式）
const configTotals = computed(() => store.getConfigTotals(activeCfg.value))

// ---- 方案备选对比模式（config_relation） ----
// compose=组合/并行（存量默认，多配置数量求和）；alternative=方案备选对比（不求和，主推方案总价×需求台数）
const configRelation = computed(() => store.opportunityInfo.config_relation || 'compose')
const isAlternative = computed(() => configRelation.value === 'alternative')
const cfgNames = computed(() => Object.keys(store.configs))
// 需求台数：alternative 下每个方案覆盖同批需求，单台方案价 × 需求台数 = 总价
const demandQty = computed(() => {
  const t = Number(store.opportunityInfo.total_qty)
  return Number.isFinite(t) && t > 0 ? t : 1
})
// 主推配置：优先用户指定；否则默认第一个配置
const primaryConfig = computed(() => {
  const prefer = store.opportunityInfo.primary_config
  if (prefer && store.configs[prefer]) return prefer
  return cfgNames.value[0] || ''
})
const primaryConfigTotals = computed(() => {
  return primaryConfig.value ? store.getConfigTotals(primaryConfig.value) : null
})
// 右侧主指标：alternative 显示主推方案单台金额；compose 仍显示当前配置总价
const heroTotalSales = computed(() => {
  if (isAlternative.value && primaryConfigTotals.value) {
    return Math.round((primaryConfigTotals.value.totalSales || 0) * 100) / 100
  }
  return configTotals.value.totalSales || 0
})
const heroTotalCost = computed(() => {
  if (isAlternative.value && primaryConfigTotals.value) {
    return Math.round((primaryConfigTotals.value.totalCost || 0) * 100) / 100
  }
  return configTotals.value.totalCost || 0
})
const heroProfit = computed(() => {
  if (isAlternative.value && primaryConfigTotals.value) {
    return Math.round((primaryConfigTotals.value.profit || 0) * 100) / 100
  }
  return configTotals.value.profit || 0
})
const heroMarginPct = computed(() => {
  if (isAlternative.value && primaryConfigTotals.value) return primaryConfigTotals.value.marginPct || 0
  return configTotals.value.marginPct || 0
})
// 切换配置关系：alternative 时把每个方案台数兜底成需求台数、主推默认第一个配置
function onConfigRelationChange(mode: 'compose' | 'alternative') {
  store.opportunityInfo.config_relation = mode
  if (mode === 'alternative') {
    const first = cfgNames.value[0]
    if (first && !store.opportunityInfo.primary_config) store.opportunityInfo.primary_config = first
    const qtys = cfgNames.value.map(n => Number(store.configQuantities[n]) || 0)
    const firstQty = qtys[0] || 0
    // 方案备选：需求台数 = 每方案台数（各配置一致时）；total_qty 不再等于 Σ 配置台数
    if (firstQty > 0 && qtys.every(q => q === firstQty)) store.opportunityInfo.total_qty = firstQty
    for (const name of cfgNames.value) {
      const q = Number(store.configQuantities[name])
      if (!q || q <= 0) store.configQuantities[name] = demandQty.value
    }
  }
  store.saveProject()
}
// 设为主推方案
function markPrimary(name: string) {
  store.opportunityInfo.primary_config = name
  store.saveProject()
}

// 兼容性规则引擎：构建当前配置 context（KP 按 category 聚合 + kpPartByPn enrich specs + 平台/系列/SATA 数），跑 WHEN→THEN
function buildRuleContext(cfg: ConfigData) {
  const kpItems = (cfg.items || []).filter((i: Item) => i.category === 'Key Parts')
  const kp: Record<string, { qty: number; items: Array<Item & { spec?: Record<string, any>; name?: string }>; spec: Record<string, any> }> = {}
  const driveQty: Record<string, number> = { SATA: 0, SAS: 0, NVMe: 0 }
  for (const it of kpItems) {
    const cat = it.part_category
    if (!cat) continue
    const spec = (it.pn ? kpPartByPn(it.pn)?.specs : null) || {}
    if (!kp[cat]) kp[cat] = { qty: 0, items: [], spec: {} }
    kp[cat].qty += Number(it.qty) || 0
    kp[cat].items.push({ ...it, spec })
    if (!Object.keys(kp[cat].spec).length && Object.keys(spec).length) kp[cat].spec = spec
    const kind = normalizeDriveKind(spec.interface || spec.kind || spec.Type)
      || normalizeDriveKind(it.pn || it.catalogue || '')
    if (kind && driveQty[kind] != null) driveQty[kind] += Number(it.qty) || 0
  }
  const drive_kinds = (Object.keys(driveQty) as string[]).filter(k => driveQty[k] > 0)
  return {
    kp,
    config: {
      series: chassisSeries.value,
      model: cfg.server_model,
      sata_qty: driveQty.SATA,
      sas_qty: driveQty.SAS,
      nvme_qty: driveQty.NVMe,
      drive_kinds,
    },
    opportunity: {},
  }
}
const selectionActions = computed(() => {
  const cfg = activeConfig.value
  if (!cfg) return []
  return selectionRulesStore.evaluateRules(buildRuleContext(cfg))
})
// 提醒列表：选型规则的 require/exclude/derive/recommend 命中
const selectionAlerts = computed(() => selectionActions.value.filter(a => a.action !== 'filter'))

// 利润率告警：读策略中心 margin_alert 策略（开关 + 门槛 + 文案）；只在保存商机时检查全部配置，不锁、不自动改价。
function warnLowMarginIfNeeded() {
  const alert = pricingRulesStore.getMarginAlert()
  if (!alert.enabled) return
  const low = Object.keys(store.configs)
    .map((name) => ({ name, margin: store.getConfigTotals(name).marginPct }))
    .filter(({ margin }) => margin != null && isFinite(margin) && margin < alert.threshold)
  if (!low.length) return
  const minMargin = Math.min(...low.map(({ margin }) => margin))
  let content = alert.content
    .replace(/\$\{margin\}/g, minMargin.toFixed(2))
    .replace(/\$\{threshold\}/g, String(alert.threshold))
  if (low.length > 1) {
    content += `\n低毛利配置：${low.map(({ name, margin }) => `${name} ${margin.toFixed(2)}%`).join('、')}`
  }
  Modal.warning({
    title: alert.title,
    content,
    okText: '知道了',
  })
}

// KP 历史价格懒加载
const onHistoryExpand = async (item: Item, keys: string[]) => {
  // Only load when expanded (keys contains 'hist')
  if (!keys.includes('hist')) return
  if (item._histLoaded) return  // Already loaded

  item._histLoading = true
  try {
    const model = item.catalogue
    if (!model) return
    const resp = await axios.get('/api/quote/kp/history', { params: { model } })
    item._history = resp.data || []
    item._histLoaded = true
  } catch (e) {
    item._history = []
    item._histLoaded = true
  } finally {
    item._histLoading = false
  }
}

// 加载报价单后：并行刷新所有 KP 行的配件库最新价（db_price）。
// db_price 原本是上传 enrich 的冻结快照，配件库后续更新或持久化往返（丢成空串）都会让它失真；
// 实时按 spec 拉一次历史取首条最新价覆盖，同步按钮的显隐才与「配件库当前最新价」一致。
async function refreshKpDbPrices() {
  const tasks: Promise<void>[] = []
  for (const cfg of Object.values(store.configs)) {
    for (const item of cfg.items) {
      if (item.category !== 'Key Parts') continue
      const model = item.catalogue
      if (!model) continue
      tasks.push((async () => {
        try {
          const arr = await getKpHistory(model, item.part_category)
          const latest = Array.isArray(arr) && arr.length ? arr[0] : null
          const n = latest ? Number(latest.price) : null
          item.db_price = (n == null || !Number.isFinite(n)) ? null : n
          item.db_currency = latest ? (latest.currency || 'RMB') : null
          computeKpMatch(item)
        } catch { /* 单条失败保留原 db_price，不阻塞其他行 */ }
      })())
    }
  }
  await Promise.all(tasks)
}

// Excel 模式 KP 行（表格渲染源）
function kpExcelRows(cfg: any) {
  return (cfg.items || []).filter((i: any) => i.category === 'Key Parts')
}

// 打开某行历史价格弹窗（复用懒加载）
function openKpHistory(item: Item) {
  kpHistoryItem.value = item
  histEditingId.value = null // 换行重开时清残留编辑态
  kpHistoryVisible.value = true
  void onHistoryExpand(item, ['hist'])
}

// 打开同步弹窗：校验型号与价格后，载入当前 KP 行作为同步目标
function openSyncModal(item: Item) {
  const model = item.catalogue
  if (!model) { message.warning('无型号，无法同步'); return }
  if (!(Number(item.base_price) > 0)) { message.warning('价格为空，无法同步'); return }
  syncTarget.value = item
  syncNote.value = ''
  syncTargetCategory.value = ''
  syncPrice.value = Number(item.base_price) || 0
  syncCurrency.value = String(item.currency || 'RMB').toUpperCase() === 'USD' ? 'USD' : 'RMB'
  syncVisible.value = true
  void resolveSyncCategory(item)
}

async function resolveSyncCategory(item: Item) {
  const raw = item.part_category || 'Key Parts'
  try {
    const res = await normalizeKpCategory(raw)
    syncTargetCategory.value = res?.category || raw
  } catch {
    syncTargetCategory.value = raw
  }
}

// 确认同步：把价格 + 用户备注写入配件库历史，并就地刷新该行的 db_price / match_status / 历史
async function confirmSync() {
  const item = syncTarget.value
  if (!item) return
  const model = item.catalogue
  if (!model) { message.warning('无型号，无法同步'); return }
  // 弹窗内改价/改币种：先写回报价行，再走入库（改价即改行，行价 = 库价）
  const price = Number(syncPrice.value)
  if (!(price > 0)) { message.warning('请输入大于 0 的价格'); return }
  const currency = syncCurrency.value === 'USD' ? 'USD' : 'RMB'
  item.base_price = price
  item.currency = currency
  store.recalculateAll()
  syncLoading.value = true
  try {
    await syncKpPrice({
      category: item.part_category || 'Key Parts',
      model,
      price: Number(item.base_price),
      currency: item.currency || 'RMB',
      note: syncNote.value.trim() || '报价工作台手动同步',
    })
    const syncedPrice = Number(item.base_price)
    const syncedCurrency = item.currency || 'RMB'
    item.db_price = syncedPrice
    item.db_currency = syncedCurrency
    item.match_status = `✅ 已同步 [${item.base_price}]`
    // 同一型号在其它配置页/行的 db_price 仍是页面加载时的旧库价快照；
    // 同步后库里最新价已变，需一并刷新它们的「库参考价」（只改 db_price，不动其它行的报价，
    // 不是跨配置联动改价），否则 CFG2 同型号仍会按旧库价误提示"同步价格"。
    for (const cfg of Object.values(store.configs)) {
      for (const it of cfg.items) {
        if (it === item) continue
        if (it.category !== 'Key Parts') continue
        if ((it.catalogue || '') !== model) continue
        it.db_price = syncedPrice
        it.db_currency = syncedCurrency
        computeKpMatch(it)
      }
    }
    if (item._histLoaded) {
      try { item._history = await getKpHistory(model, item.part_category) } catch { /* 历史刷新失败不阻塞 */ }
    }
    message.success(`已同步 ${model} → 配件库历史`)
    syncVisible.value = false
  } catch (e: any) {
    message.error('同步失败：' + (e?.message || e))
  } finally {
    syncLoading.value = false
  }
}

onMounted(async () => {
  // 并行加载：导出模板 / 质保默认值 / 机型目录 / KP 料号目录（下拉 + create 默认 + 机箱卡 series + KP 新建模式都依赖）
  await Promise.all([loadTemplates(), loadWarrantyDefaults(), loadServerModels(), loadKpCatalog(), loadGpuCableItems(), pricingRulesStore.ensurePricingRules(), selectionRulesStore.ensureRules()])
  const firstModel = serverModels.value[0]

  // Check routing context
  const quotationId = route.query.quotationId as string
  const mode = route.query.mode as string
  const opportunityId = route.query.opportunityId as string

  if (mode === 'create') {
    // 新建报价单：完全重置 store，确保数据隔离
    store.configs = {}
    store.configQuantities = {}
    store.configSelectedParts = {}
    store.opportunityInfo = {
      opportunity_id: opportunityId || '',
      sales_person: '',
      fae: '',
      customer_name: '',
      date: '',
      model_name: '',
      total_qty: 0,
      platform_type: '',
      chassis_form: '',
      config_relation: 'compose',
      primary_config: '',
      order_type: ''
    }
    // 在已有商机下新建报价：回填该商机元数据，避免保存时把名字等覆盖成空（→ 显示"未命名"）
    if (opportunityId) {
      try {
        const { data: resp }: any = await axios.get(`/api/opportunities/${opportunityId}`)
        const opp = resp.meta || resp
        store.opportunityInfo = {
          opportunity_id: opp.opportunity_id || opportunityId,
          sales_person: opp.sales_person || '',
          fae: opp.fae || '',
          customer_name: opp.customer_name || '',
          date: opp.date || '',
          model_name: opp.model_name || '',
          total_qty: opp.purchase_qty ?? opp.total_qty ?? 0,
          platform_type: opp.platform_type || '',
          chassis_form: opp.chassis_form || '',
          config_relation: opp.config_relation || 'compose',
          primary_config: opp.primary_config || '',
          order_type: opp.order_type || ''
        }
      } catch { /* 读取失败回退空白，不阻塞新建 */ }
    }

    // 初始化空白配置（server_model 默认目录第一个机型，满足「恒有值」）
    // KP 核心类别预填首件（CPU/Memory/HDD-SSD/GPU/NIC 各一行，AI 机型才填 GPU），新建模式即可见
    const seedKpItems = (): Item[] => CORE_KP_CATS
      .filter(c => (kpCatalog.value[c] || []).length)
      .map(c => newKpItem(c))
    store.configs['CFG1'] = {
      name: 'CFG1',
      description: '',
      items: seedKpItems(),
      summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
      l6_matched_record: null,
      l6_custom_price: 0,
      l6_profit_margin: 10,
      bom_source: 'live',
      server_model: firstModel?.name || '',
      server_model_id: firstModel?.id,
      base_config_id: firstModel?.base_config_id,
      gpu_arch: 'none',
      warranty_info: {
        l6: { detected: false, years: null, rate: 0 },
        kp: { detected: false, years: null, rate: 0 }
      }
    }
    if (firstModel?.base_config_id) loadBaseInfo(firstModel.base_config_id)
    // 方案备选：从需求单带入模式时，主推默认第一个配置
    if (store.opportunityInfo.config_relation === 'alternative' && !store.opportunityInfo.primary_config) {
      store.opportunityInfo.primary_config = 'CFG1'
    }
    activeCfg.value = 'CFG1'
  } else if (quotationId) {
    // 从后端加载已有报价单
    try {
      const response = await axios.get(`/api/quotations/${quotationId}`)
      const quotation = response.data

      // Group items by config_name (supports multi-config quotations)
      const items = quotation.items || []
      const configs: Record<string, any> = {}
      const configDescriptions = quotation.config_descriptions || {}
      const configServerModels = quotation.config_server_models || {}
      const configQuantities = quotation.config_quantities || {}
      const configWarrantyInfo = quotation.config_warranty_info || {}

      // 🔧 修复：先从所有数据源收集配置名，确保没有 items 的配置也能被加载
      const allConfigNames = new Set<string>()
      Object.keys(configDescriptions).forEach(name => allConfigNames.add(name))
      Object.keys(configServerModels).forEach(name => allConfigNames.add(name))
      Object.keys(configQuantities).forEach(name => allConfigNames.add(name))
      items.forEach((item: any) => allConfigNames.add(item.config_name || 'CFG1'))

      // 为每个配置创建对象
      for (const cfgName of allConfigNames) {
        configs[cfgName] = {
          name: cfgName,
          description: configDescriptions[cfgName] || '',
          server_model: configServerModels[cfgName] || '',
          items: [],
          summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
          l6_matched_record: null,
          l6_custom_price: 0,
          l6_profit_margin: 10,
          warranty_info: configWarrantyInfo[cfgName] || {
            l6: { detected: false, years: null, rate: 0 },
            kp: { detected: false, years: null, rate: 0 }
          }
        }
      }

      // 填充 items
      for (const item of items) {
        const cfgName = item.config_name || 'CFG1'
        if (configs[cfgName]) {
          configs[cfgName].items.push(item)
        }
      }

      // 🎯 Apply per-config L6 matching results from API
      const perCfgL6 = quotation.per_cfg_l6 || {}
      for (const [cfgName, l6Data] of Object.entries(perCfgL6)) {
        if (configs[cfgName]) {
          configs[cfgName].l6_matched_record = (l6Data as any).l6_matched_record || null
          configs[cfgName].l6_custom_price = (l6Data as any).l6_custom_price || 0
          configs[cfgName].l6_profit_margin = (l6Data as any).l6_profit_margin || 10
        }
      }

      // Fallback: if no per-config data, apply top-level to first config
      if (Object.keys(perCfgL6).length === 0 && quotation.l6_matched_record) {
        const cfgName = Object.keys(configs)[0] || 'CFG1'
        if (configs[cfgName]) {
          configs[cfgName].l6_matched_record = quotation.l6_matched_record
        }
      }

      // Ensure at least one config even if no items
      if (Object.keys(configs).length === 0) {
        configs['CFG1'] = {
          name: 'CFG1',
          items: [],
          summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
          l6_matched_record: quotation.l6_matched_record || null,
          warranty_info: {
            l6: { detected: false, years: null, rate: 0 },
            kp: { detected: false, years: null, rate: 0 }
          }
        }
      }

      const opportunityInfo = {
        opportunity_id: quotation.opportunity_id || opportunityId,
        customer_name: quotation.customer_name || '',
        quotation_id: quotation.quotation_id,
        version: quotation.version,
        fae: quotation.fae || '',
        sales_person: quotation.sales_person || '',
        date: quotation.quotation_date || quotation.date || quotation.created_at?.slice(0, 10) || '',
        model_name: quotation.model_name || '',
        l6_spec: quotation.l6_spec || '',
        description: quotation.description || quotation.l6_spec || '',
        total_qty: quotation.total_qty || 0,
        platform_type: (quotation as any).platform_type || '',
        chassis_form: (quotation as any).chassis_form || '',
        config_relation: (quotation as any).config_relation || 'compose',
        primary_config: (quotation as any).primary_config || '',
      }

      // 传递 config_quantities 到 store
      // Excel 上传报价单判定:file_path 非空 或 从上传页进入 → 左栏快照模式
      const isExcelQuote = !!quotation.file_path || entryFrom.value === 'upload'
      store.loadData({ configs, project_info: opportunityInfo, config_quantities: configQuantities, config_l6_picks: quotation.config_l6_picks, is_excel_quote: isExcelQuote })
      store.quotationUpdatedAt = (quotation as any).updated_at || ''
      activeCfg.value = Object.keys(store.configs)[0] || 'CFG1'
      // edit 模式补拉商机 platform_type/chassis_form（兼容性 filter 规则依赖；报价单可能未存该字段）
      if (opportunityId && !store.opportunityInfo.platform_type) {
        try {
          const { data: resp }: any = await axios.get(`/api/opportunities/${opportunityId}`)
          const opp = resp.meta || resp
          if (opp.platform_type) store.opportunityInfo.platform_type = opp.platform_type
          if (opp.chassis_form) store.opportunityInfo.chassis_form = opp.chassis_form
          if (opp.config_relation) store.opportunityInfo.config_relation = opp.config_relation
          if (opp.primary_config) store.opportunityInfo.primary_config = opp.primary_config
        } catch { /* 不阻塞加载 */ }
      }
      message.success("已加载报价单数据")
    } catch (err) {
      console.error("加载报价单失败", err)
      message.error("加载报价单失败")
    }
  }
  initSectionState()
  store.recalculateAll()
  // 加载所有 config 的机箱卡 series/baseConfigName（按 base_config_id 批量；命中缓存，重复 id 只取一次）
  for (const cfg of Object.values(store.configs)) {
    if (cfg.base_config_id) {
      await loadBaseInfo(cfg.base_config_id)
      // 存量兼容：老推理报价单 server_model_id 缺失时回填（修机箱卡形态/用途为空）
      backfillServerModelId(cfg)
    }
  }
  // 后台并行刷新所有 KP 行的配件库最新价（基于当前配件库，而非上传快照），刷新后同步按钮显隐自动更新
  refreshKpDbPrices()
})
</script>

<style scoped>
/* 选型策略校验提醒（conflict=红 / require=黄；提醒为主，不阻断） */
.selection-alerts { display: flex; flex-direction: column; gap: 6px; margin: 8px 0 12px; }
.selection-alert { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: var(--cpq-radius-sm, 8px); font-size: 12px; border: 1px solid transparent; }
.selection-alert.conflict { color: var(--cpq-accent-danger, #FF6B6B); background: var(--cpq-overlay-danger10, rgba(255,107,107,0.10)); border-color: var(--cpq-overlay-danger15, rgba(255,107,107,0.20)); }
.selection-alert.require { color: #c8861a; background: var(--cpq-overlay-warn30, rgba(244,210,138,0.18)); border-color: var(--cpq-accent-warning, #F4D28A); }
.selection-alert.warning { color: var(--cpq-accent-warning, #F4D28A); background: rgba(244,210,138,0.14); border-color: rgba(244,210,138,0.32); }
.selection-advice-card { margin-top: 12px; }
.selection-advice-card .selection-alerts { margin: 0; padding: 0 14px 14px; }
.selection-advice-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px 10px; }
.selection-advice-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.selection-advice-count { min-width: 22px; height: 22px; padding: 0 6px; border-radius: 11px; background: var(--cpq-accent-primary); color: #fff; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.selection-advice-empty { padding: 0 16px 14px; font-size: 12px; color: var(--cpq-text-muted); }
.sa-icon { font-weight: 700; flex-shrink: 0; }
.sa-text { flex: 1; min-width: 0; }
.sa-off { color: var(--cpq-text-muted, #86909c); margin-left: 4px; }
.workspace-page {
  position: relative;
  min-height: calc(100vh - var(--cpq-header-clearance, 0px));
  /* 不设整页背景：透出布局网格层，玻璃卡片才有磨砂感 */
  color: var(--cpq-text-primary);
}

/* 顶部 accent 光条 */
.workspace-page::before {
  content: '';
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--cpq-accent-primary), transparent);
  z-index: 200;
  pointer-events: none;
}

.content-inner {
  width: 100%;
  margin: 0 auto;
  padding: 24px;
}

/* ============================================
   1. 配置 Tab 栏
   ============================================ */
.cfg-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 24px;
  gap: 16px;
  position: sticky;
  top: var(--cpq-sticky-top, 0px);
  z-index: 20;
  padding: 4px 0;
  background: linear-gradient(180deg, var(--cpq-bg-secondary, #101217) 78%, transparent);
  backdrop-filter: blur(8px);
}

.cfg-pills {
  display: flex;
  gap: 8px;
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 12px;
  padding: 6px;
}

.cfg-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  color: var(--cpq-text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.cfg-pill:hover {
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w4);
}

.cfg-pill:hover .pill-close {
  opacity: 1;
}

.cfg-pill.active {
  background: var(--cpq-accent-primary);
  color: var(--cpq-accent-on-primary);
  font-weight: 600;
}

.pill-label {
  font-weight: 600;
}

.pill-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: 12px;
  line-height: 1;
  color: var(--cpq-text-muted);
  opacity: 0;
  transition: all var(--cpq-transition-fast);
  margin-left: 4px;
}

.cfg-pill.active .pill-close {
  color: var(--cpq-accent-on-primary);
}

.pill-close:hover {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.cfg-add-btn {
  border: 1px dashed var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: transparent !important;
  font-size: 12px;
}

.cfg-add-btn:hover {
  background: var(--cpq-overlay-a10) !important;
}

.cfg-relation {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  white-space: nowrap;
  padding: 2px 0;
}

.cfg-relation-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
}

.cfg-relation .ant-radio-button-wrapper {
  font-size: 12px;
  padding: 0 12px;
}

/* ============================================
   2. 右键菜单
   ============================================ */
.cfg-context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--cpq-bg-elevated);
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 8px;
  padding: 4px;
  min-width: 140px;
  box-shadow: 0 8px 24px var(--cpq-shadow-color-strong);
}

.cfg-context-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--cpq-text-primary);
  cursor: pointer;
  border-radius: 4px;
  transition: background var(--cpq-transition-fast);
}

.cfg-context-item:hover {
  background: var(--cpq-overlay-w8);
}

.cfg-context-danger:hover {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.pill-edit-input {
  background: var(--cpq-overlay-b40);
  border: 1px solid var(--cpq-accent-primary);
  color: var(--cpq-text-primary);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 13px;
  font-weight: 600;
  width: 80px;
  outline: none;
}

/* ============================================
   3. 三栏布局
   ============================================ */
.three-col-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.col-left {
  flex: 25;
  min-width: 0;
  position: sticky;
  top: calc(var(--cpq-sticky-top, 0px) + 16px);
  height: calc(100vh - var(--cpq-sticky-top, 0px) - 32px);
  display: flex;
  flex-direction: column;
  overflow: visible;
  transition: flex .25s ease;
}

.col-left-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.col-left.collapsed {
  flex: 0 0 30px;
  overflow: visible;
}

.left-collapse-btn {
  position: absolute;
  top: calc(50% - 38px);
  right: -11px;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 76px;
  padding: 0;
  border: 1.5px solid var(--cpq-border-primary);
  border-radius: 10px 0 0 10px;
  background: var(--cpq-bg-elevated);
  box-shadow: 0 3px 12px var(--cpq-overlay-a20);
  color: var(--cpq-text-secondary);
  cursor: pointer;
  transition: all .2s;
}
.left-collapse-btn:hover {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
  box-shadow: 0 0 0 3px var(--cpq-accent-soft, var(--cpq-overlay-a20)), 0 4px 14px var(--cpq-overlay-a30);
}
.left-collapse-btn .lc-icon {
  display: inline-flex;
  font-size: 15px;
  font-weight: 600;
  color: inherit;
}

.col-left.collapsed .left-collapse-btn {
  width: 22px;
  border-radius: 0 10px 10px 0;
}

.col-middle {
  flex: 53;
  min-width: 0;
}

.col-right {
  flex: 22;
  min-width: 0;
  position: sticky;
  top: calc(var(--cpq-sticky-top, 0px) + 16px);
  max-height: calc(100vh - var(--cpq-sticky-top, 0px) - 32px);
  overflow-y: auto;
}

/* ============================================
   4. 中栏：配置基本信息
   ============================================ */
.card-section {
  padding: 16px;
  border-radius: 14px;
  margin-bottom: 16px;
}

.basic-row {
  display: flex;
  gap: 24px;
  align-items: flex-end;
}

.basic-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.basic-field-grow {
  flex: 1;
}

.basic-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.primary-btn {
  border: 1px dashed var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: transparent;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.primary-btn.active {
  background: var(--cpq-accent-primary);
  color: #fff;
  border-style: solid;
}

/* ============================================
   5. 配置描述（可折叠）
   ============================================ */
.desc-header {
  display: flex;
  align-items: center;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--cpq-overlay-w10);
  cursor: pointer;
  user-select: none;
  gap: 8px;
}

.desc-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-size: 14px;
}

.desc-preview {
  flex: 1;
  color: var(--cpq-text-secondary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desc-toggle {
  color: var(--cpq-accent-primary);
  font-size: 12px;
  font-weight: 500;
}

.desc-body {
  padding: 12px 0 0;
}

/* ============================================
   6. 区段导航（Segment）
   ============================================ */
.seg-nav {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
  padding: 4px;
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 10px;
  gap: 4px;
}

.seg-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-secondary);
  transition: all var(--cpq-transition-fast);
  border-radius: 6px;
}

.seg-item:hover {
  color: var(--cpq-text-primary);
}

.seg-item.active {
  color: var(--cpq-accent-primary);
  font-weight: 600;
  background: var(--cpq-overlay-a8);
}

.seg-label {
  font-size: 13px;
}

/* ============================================
   7. Section Content
   ============================================ */
.section-content {
  min-height: 200px;
}

.empty-placeholder {
  text-align: center;
  padding: 60px 20px;
  color: var(--cpq-text-secondary);
  font-size: 15px;
  border: 1px dashed var(--cpq-border-primary);
  border-radius: 12px;
}

/* ============================================
   8. L6 Section
   ============================================ */
.l6-section {
  margin-bottom: 24px;
}

.l6-unmatched-hint {
  font-size: 12px;
  color: var(--cpq-accent-warning, #fa8c16);
  white-space: nowrap;
}


/* ============================================
   9. KP Section
   ============================================ */
.card-kp {
  padding: 18px 20px 20px;
  border-radius: var(--cpq-radius-xl, 20px);
  margin-bottom: 24px;
  border: 1px solid var(--cpq-glass-border);
}
.kp-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--cpq-overlay-w10);
}
.kp-card-title { display: flex; flex-direction: column; gap: 3px; min-width: 0; }

.sec-title {
  margin: 0;
  font-size: 16px;
  color: var(--cpq-text-primary) !important;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6);
  padding: 2px 8px;
  border-radius: 10px;
}

/* KP Excel 模式：带框线表格（一行一配件，风格对齐 qw-detail-table / bom-detail-table）*/
.kp-table-wrap { width: 100%; overflow: hidden; }
.kp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  table-layout: auto;
}
.kp-table th {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-muted);
  font-weight: 600;
  text-align: left;
  padding: 8px 10px;
  border: 1px solid var(--cpq-glass-border);
  white-space: nowrap;
}
/* auto 布局：以下为建议比例，价格列 nowrap 撑住最小宽，文本列吸收窄屏挤压（不出滚动条） */
table.kp-table th:nth-child(1) { width: 11%; }
table.kp-table th:nth-child(2) { width: 26%; }
table.kp-table th:nth-child(3) { width: 7%; }
table.kp-table th:nth-child(4) { width: 14%; }
table.kp-table th:nth-child(5) { width: 8%; }
table.kp-table th:nth-child(6) { width: 14%; }
table.kp-table th:nth-child(7) { width: 20%; }
.kp-table td {
  padding: 7px 10px;
  border: 1px solid var(--cpq-glass-border);
  color: var(--cpq-text-primary);
  vertical-align: middle;
  overflow-wrap: anywhere;
}
/* 全表统一居左；等宽数字保证同位数纵向对齐，价格 nowrap 永不折行 */
.kp-table th.num, .kp-table td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.kp-table td.price { color: var(--cpq-accent-primary); font-weight: 700; }
.kp-table th.ops, .kp-table td.ops { text-align: left; }
.kp-table tbody tr.kp-tr:hover td { background: var(--cpq-overlay-w6); }
.kp-table .cat { min-width: 0; }
.kp-table .cat.break { word-break: break-word; }
.kp-table .hist-btn { font-size: 11px; padding: 0 4px; }
.kp-table .kp-name { font-weight: 600; font-size: 12px; margin-right: 8px; }
.kp-table .kp-raw-price { font-variant-numeric: tabular-nums; }
.kp-table :deep(.inp-num) { width: 100%; }
.kp-table :deep(.inp-cur) { width: 100%; }
.kp-table .ops-inner { display: flex; flex-direction: row; flex-wrap: wrap; align-items: center; justify-content: flex-start; gap: 6px; }
.kp-table .ops-btns { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-start; gap: 6px; }
.kp-table .kp-match { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; line-height: 1.4; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* KP 新建模式：按类别分卡纵向堆叠 */
.kp-new-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.kp-add-card-wrap {
  display: flex;
  justify-content: center;
}
.kp-add-card-sel {
  width: 100%;
  max-width: 320px;
  background: var(--cpq-overlay-b20);
  color: var(--cpq-text-secondary);
  border: 1px dashed var(--cpq-overlay-w20);
  border-radius: 12px;
  padding: 11px 14px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  appearance: none;
}
.kp-add-card-sel:hover {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}

.kp-name {
  color: var(--cpq-text-primary);
  font-weight: 600;
  font-size: 12px;
}

.kp-match {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kp-match.ok { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.kp-match.warn { color: #fa8c16; background: rgba(250,140,22,.14); }
.kp-match.new { color: var(--cpq-text-secondary); background: var(--cpq-overlay-w6); }

.price-val {
  color: var(--cpq-accent-primary) !important;
  font-weight: 700;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.price-hidden {
  color: var(--cpq-text-muted, #6e7582);
  letter-spacing: 1px;
}

.sync-btn {
  font-size: 11px;
  padding: 0 8px;
}

.kp-hist-header {
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.kp-hist-loading {
  text-align: center;
  padding: 12px 0;
}

.kp-hist-list {
  max-height: 160px;
  overflow-y: auto;
  padding: 0 8px;
}

.kp-hist-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.kp-hist-item:last-child {
  border-bottom: none;
}

.kp-hist-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cpq-accent-primary);
  margin-top: 5px;
  flex-shrink: 0;
}

.kp-hist-content {
  flex: 1;
  min-width: 0;
}

.kp-hist-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.kp-hist-date {
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.kp-hist-price {
  font-size: 13px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  font-variant-numeric: tabular-nums;
}

.kp-hist-price.usd {
  color: var(--cpq-accent-warning);
}

.kp-hist-note {
  font-size: 10px;
  color: var(--cpq-text-disabled);
  margin-top: 2px;
}

/* 最新一条：徽标 + 修改入口 */
.kp-hist-latest {
  display: inline-block;
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 10px;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.kp-hist-head {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.kp-hist-edit-btn {
  padding: 0 4px;
  height: auto;
  font-size: 11px;
}

/* 最新一条编辑态 */
.kp-hist-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  background: var(--cpq-overlay-w4);
}
.kp-hist-edit-row {
  display: flex;
  gap: 8px;
}
.kp-hist-edit-price { flex: 1; }
.kp-hist-edit-cur { width: 100px; }
.kp-hist-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.kp-hist-empty {
  font-size: 11px;
  color: var(--cpq-text-muted);
  text-align: center;
  padding: 12px 0;
}

/* KP 历史价格弹窗 */
.kp-history-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.kp-hist-meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
}
.kp-hist-meta-cat {
  font-size: 12px;
  color: var(--cpq-text-muted);
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--cpq-overlay-w6);
}
.kp-hist-meta-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

/* KP 同步价格弹窗 */
.sync-modal {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sync-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.sync-label {
  flex: 0 0 48px;
  font-size: 12px;
  color: var(--cpq-text-muted);
  line-height: 22px;
}

.sync-val {
  flex: 1;
  font-size: 14px;
  color: var(--cpq-text-primary);
  font-weight: 500;
  word-break: break-word;
  line-height: 22px;
}

.sync-price-edit { display: flex; align-items: center; gap: 8px; }
.sync-price-inp { width: 150px; }
.sync-cur-sel { width: 100px; }
.sync-price-edit :deep(.ant-input-number-input) {
  color: var(--cpq-accent-primary);
  font-weight: 600;
}

.sync-note :deep(.ant-input) {
  background: var(--cpq-overlay-b30) !important;
  border-color: var(--cpq-overlay-w10) !important;
  color: var(--cpq-text-primary) !important;
}

.sync-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
  border-radius: 8px;
  padding: 8px 10px;
  line-height: 1.5;
}

/* ============================================
   10. 维保 Section
   ============================================ */
.warranty-row {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
}

.w-card {
  flex: 1;
  padding: 14px 16px;
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-glass-border);
  border-radius: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.w-card:hover { border-color: var(--cpq-glass-border-strong); }

.w-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--cpq-border-secondary);
  width: 100%;
}

.w-description {
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin-bottom: 16px;
  line-height: 1.6;
  padding: 0 8px;
}

.w-card-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.w-row {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 10px;
}

.w-label {
  color: var(--cpq-text-muted);
  font-size: 12px;
  min-width: 50px;
  text-align: right;
}

.w-unit {
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.w-val {
  color: var(--cpq-accent-primary) !important;
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.w-btns {
  display: flex;
  justify-content: center;
  margin-top: 6px;
  min-height: 28px;
}

.w-btn {
  align-self: center;
  margin-top: 6px;
}

/* ============================================
   11. 右栏：财务面板
   ============================================ */
.fin-card {
  border-radius: 14px;
  overflow: hidden;
  padding: 0;
}

.fin-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  padding: 16px 20px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
}

.fin-hero {
  padding: 20px;
}

.hero-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.hero-val {
  font-size: 32px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  font-variant-numeric: tabular-nums lining-nums;
  letter-spacing: -0.02em;
  text-shadow: var(--cpq-reading-glow);
}

.fin-rows {
  padding: 0 20px 16px;
}

.fin-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--cpq-overlay-w3);
}

.fin-row:last-child {
  border-bottom: none;
}

.fin-label {
  width: 110px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--cpq-text-muted);
  text-align: right;
  padding-right: 16px;
}

.fin-val {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-variant-numeric: tabular-nums;
}

.fin-val.pos {
  color: var(--cpq-accent-primary);
}

.fin-val.neg {
  color: var(--cpq-accent-danger);
}

.fin-settings {
  padding: 16px 20px;
  border-top: 1px solid var(--cpq-overlay-w6);
}

.fin-settings-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  margin-bottom: 12px;
}

.alt-panel {
  padding: 16px 20px;
  border-top: 1px solid var(--cpq-overlay-w6);
}

.alt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.alt-row:hover {
  background: var(--cpq-overlay-a10);
}

.alt-row.primary {
  background: var(--cpq-overlay-a10);
  outline: 1px solid var(--cpq-accent-primary);
}

.alt-radio {
  color: var(--cpq-accent-primary);
  font-size: 12px;
}

.alt-name {
  font-weight: 600;
  font-size: 12px;
  min-width: 42px;
}

.alt-model {
  flex: 1;
  font-size: 12px;
  color: var(--cpq-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alt-price {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.alt-primary-tag {
  color: var(--cpq-accent-primary);
  font-size: 11px;
  font-weight: 600;
  min-width: 28px;
  text-align: right;
}

.fin-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.fin-setting-row:last-child {
  margin-bottom: 0;
}

.fin-setting-row label {
  font-size: 12px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
}

/* ============================================
   12. 底部操作栏
   ============================================ */
.action-bar {
  position: sticky;
  bottom: 0;
  padding: 16px 24px;
  z-index: 99;
}

.action-bar-inner {
  width: 100%;
  margin: 0 auto;
  display: flex;
  justify-content: center;
  gap: 16px;
}

.btn-ghost {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
  font-size: 13px;
  padding: 8px 20px;
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.btn-ghost:hover {
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: var(--cpq-overlay-a5) !important;
}

.btn-pri {
  background: var(--cpq-accent-primary) !important;
  border: 1px solid var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-on-primary) !important;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 24px;
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.btn-pri:hover {
  box-shadow: 0 0 20px var(--cpq-overlay-a40);
}

/* ============================================
   规格书预览：模态框内滚动容器 + 打印 overlay
   ============================================ */
.spec-preview-scroll,
.spec-preview-wrap {
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  background: var(--cpq-bg-tertiary);
}

/* 预览弹窗：左导出选项 / 右 Univer 画布（上下空间紧张，采用左右分栏）。
   模态已是玻璃层，内嵌面板走结构性容器配方（弱白底+发丝边+inset 高光），不叠 backdrop-filter 防玻璃嵌套发雾 */
.preview-split {
  display: flex;
  gap: 12px;
  height: 85vh;
}
.preview-opts {
  width: 248px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-overlay-w5);
  border: 1px solid var(--cpq-glass-border);
  box-shadow: 0 8px 24px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
  overflow-y: auto;
}
.preview-canvas {
  flex: 1;
  min-width: 0;
  border-radius: var(--cpq-radius-lg);
  overflow: hidden;
  border: 1px solid var(--cpq-glass-border);
  background: #fff;
}
.po-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.po-group .po-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  margin: 0 -6px;
  border-radius: var(--cpq-radius-sm);
  cursor: pointer;
  user-select: none;
  transition: background var(--cpq-transition-fast);
}
.po-group .po-row:hover {
  background: var(--cpq-overlay-w4);
}
.po-group .po-row.locked {
  cursor: not-allowed;
  opacity: 0.5;
}
.po-group .po-row.locked:hover {
  background: transparent;
}
.po-name {
  font-size: 13px;
  color: var(--cpq-text-primary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.po-lock { font-size: 11px; }
.po-tag {
  font-size: 10px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: var(--cpq-radius-sm);
  color: #ad6800;
  background: rgba(250, 173, 20, 0.16);
}
.po-desc {
  margin: 3px 0 0 24px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.po-version {
  border-top: 1px dashed var(--cpq-glass-border);
  padding-top: 10px;
}
.po-version-label {
  font-size: 11px;
  color: var(--cpq-text-muted);
  margin-bottom: 6px;
}
.po-version-tag {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
}
.po-version-tag.pv-internal {
  color: #ad6800;
  background: rgba(250, 173, 20, 0.18);
}
.po-version-tag.pv-sell {
  color: #1c5dd8;
  background: rgba(22, 119, 255, 0.12);
}
.po-version-tag.pv-customer {
  color: #0f7a5e;
  background: rgba(82, 201, 160, 0.20);
}
.po-version-hint {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--cpq-text-secondary);
}
.po-note {
  font-size: 11px;
  line-height: 1.5;
  color: var(--cpq-text-muted);
}
.po-refresh {
  font-size: 11px;
  color: var(--cpq-accent-primary);
}

/* 打印 overlay（Teleport 到 body 仍带本组件 scoped data-v，样式生效）：
   屏内表现交给这里，真正的 @media print 规则由 SpecSheet.vue 非 scoped 块接管。 */
.spec-sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--cpq-overlay-b85);
  backdrop-filter: blur(8px);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px;
  overflow-y: auto;
}
.spec-sheet-scroll {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 900px;
}

/* ============================================
   13. Ant Design 暗色输入覆盖
   ============================================ */
:deep(.ant-input-number),
:deep(.ant-input),
:deep(.ant-select-selector) {
  background: var(--cpq-overlay-b30) !important;
  border: 1px solid var(--cpq-overlay-w10) !important;
  color: var(--cpq-text-primary) !important;
  border-radius: 6px;
  transition: all var(--cpq-transition-fast);
}

:deep(.ant-input-number-input),
:deep(.ant-input) {
  color: var(--cpq-text-primary) !important;
  background: transparent !important;
}

:deep(.ant-input-number-focused),
:deep(.ant-input-focused),
:deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a15) !important;
}

:deep(.ant-input-number-handler-wrap) {
  background: var(--cpq-overlay-w4) !important;
  border-left: 1px solid var(--cpq-overlay-w6) !important;
}

:deep(.ant-input-number-handler-up-inner),
:deep(.ant-input-number-handler-down-inner) {
  color: var(--cpq-text-secondary) !important;
}
/* ── 手机端：cfg-bar 瘦身 + 抽屉头/滚动体 + 底部 sticky 摘要条 ── */
.ws-back-m { width: 30px; height: 30px; border-radius: 9px; border: 1px solid var(--cpq-border-secondary); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary); font-size: 15px; cursor: pointer; flex: none; display: inline-flex; align-items: center; justify-content: center; line-height: 1; padding-bottom: 2px; }

.pd-head-row { display: flex; align-items: center; gap: 8px; padding: 14px 15px 10px; flex: none; }
.pd-head-row h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--cpq-text-primary); }
.pd-chip { font-size: 10px; color: var(--cpq-text-secondary); background: var(--cpq-overlay-w6); border-radius: 999px; padding: 2px 9px; white-space: nowrap; max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.pd-sp { flex: 1; }
.pd-x { width: 29px; height: 29px; border-radius: 10px; border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary); cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; flex: none; }
.pd-scroll { flex: 1 1 0; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 0 14px 16px; display: flex; flex-direction: column; gap: 12px; }
.pd-scroll .fin-card { height: auto; }
.pd-scroll-bom { display: block; }

.exp-card-m { background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border); border-radius: 14px; padding: 12px; }
.exp-title-m { font-size: 12px; font-weight: 700; color: var(--cpq-text-secondary); margin-bottom: 8px; }

.sumbar { position: fixed; left: 0; right: 0; bottom: var(--cpq-tabbar-inset, 0px); z-index: 170;
  display: flex; align-items: center; gap: 8px; padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0px));
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, .9));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3, 16px)) saturate(1.3);
  backdrop-filter: blur(var(--cpq-glass-blur-3, 16px)) saturate(1.3);
  border-top: 1px solid var(--cpq-glass-border); }
.sum-ic { width: 38px; height: 38px; border-radius: 12px; flex: none; display: inline-flex; align-items: center; justify-content: center;
  background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-glass-border); color: var(--cpq-text-secondary); cursor: pointer; padding: 0; }
.sum-ic svg { width: 17px; height: 17px; }
.sum-metric { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; cursor: pointer; }
.sum-metric .v { font-size: 15px; font-weight: 800; color: var(--cpq-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }
.sum-metric .l { font-size: 9.5px; color: var(--cpq-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sum-metric .l b.pos { color: var(--cpq-accent-success); }
.sum-metric .l b.neg { color: var(--cpq-accent-danger); }
.sum-cta { flex: none; height: 38px; padding: 0 15px; border-radius: 12px; border: none; cursor: pointer;
  background: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-size: 12.5px; font-weight: 700; }
.sum-cta:disabled { opacity: .6; }

@media (max-width: 768px) {
  .workspace-page { padding-bottom: calc(76px + var(--cpq-tabbar-inset, 0px)); }
  .content-inner { padding: 12px 12px 8px; }
  .cfg-bar { flex-wrap: nowrap; overflow-x: auto; gap: 8px; }
  .cfg-pills { flex: 1; flex-wrap: nowrap; overflow-x: auto; min-width: 0; }
  .cfg-relation { flex: none; margin-left: 0; }
  .cfg-relation-label { display: none; }
  .three-col-layout { display: block; }
  .col-middle { max-width: none; width: 100%; }
}
</style>

<!-- 机箱配置弹窗渲染到 portal（scoped 之外），用全局样式撑满 L6ChassisConfig（同 ConfigWizard） -->
<style>
.chassis-modal-quote .ant-modal-body { padding: 18px 20px; max-height: 82vh; overflow-y: auto; }
.chassis-modal-quote .ant-modal { top: 30px; }
/* 报价工作台手机抽屉外壳：portal 到 body，scoped 够不到，走全局（配色走主题 token） */
.opp-quote-drawer .ant-drawer-content {
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3, 16px)) saturate(1.3);
  backdrop-filter: blur(var(--cpq-glass-blur-3, 16px)) saturate(1.3);
  overflow: hidden;
}
.opp-quote-drawer .ant-drawer-left .ant-drawer-content { border-radius: 0 18px 18px 0; }
.opp-quote-drawer .ant-drawer-right .ant-drawer-content { border-radius: 18px 0 0 18px; }
.opp-quote-drawer .ant-drawer-header { display: none; }
</style>
