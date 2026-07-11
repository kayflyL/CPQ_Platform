<template>
  <div class="workspace-page">
    <!-- 1. 顶部：Sticky 财务看板 (随配置页切换动态变化) -->

    <div class="kpi-sticky">
      <div class="kpi-container glass">
        <div class="kpi-cell">
          <div class="kpi-label">{{ activeCfg }} 整机总成本</div>
          <div class="kpi-sublabel">L6 + KP + 质保</div>
          <div class="kpi-value">¥ {{ settingsStore.formatNumber(configTotals.totalCost) }}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-label">含税总价</div>
          <div class="kpi-sublabel">总销售价</div>
          <div class="kpi-value">¥ {{ settingsStore.formatNumber(configTotals.totalSales) }}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-label">总利润额</div>
          <div class="kpi-sublabel">销售 - 成本</div>
          <div class="kpi-value" :class="configTotals.profit >= 0 ? 'color-positive' : 'color-negative'">¥ {{ settingsStore.formatNumber(configTotals.profit) }}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-label">综合毛利率</div>
          <div class="kpi-sublabel">利润 / 销售</div>
          <div class="kpi-value" :class="configTotals.marginPct >= 0 ? 'color-positive' : 'color-negative'">{{ configTotals.marginPct.toFixed(settingsStore.numberPrecision) }}%</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell kpi-settings-cell">
          <a-popover trigger="click" placement="bottomRight" overlay-class-name="finance-settings-popover">
            <template #content>
              <div class="finance-settings">
                <div class="finance-setting-row">
                  <label>增值税率</label>
                  <a-input-number
                    :value="store.taxRate * 100"
                    @change="(v: number) => { store.taxRate = (v || 0) / 100; store.recalculateAll() }"
                    :min="0" :max="30" :step="1"
                    size="small"
                    style="width: 80px"
                    addon-after="%"
                  />
                </div>
                <div class="finance-setting-row">
                  <label>美元汇率</label>
                  <a-input-number
                    :value="store.exchangeRate"
                    @change="(v: number) => { store.exchangeRate = v || 7; store.recalculateAll() }"
                    :min="1" :max="20" :step="0.1"
                    size="small"
                    style="width: 80px"
                  />
                </div>
                <div class="finance-setting-hint">修改后实时重算所有配置</div>
              </div>
            </template>
            <div class="kpi-settings-btn" title="财务参数设置">
              <span>⚙️</span>
            </div>
          </a-popover>
        </div>
      </div>
    </div>

    <!-- 2. 主内容区 -->
    <div class="content-inner">
      
      <!-- 自定义配置 Tab 栏 -->
      <div class="config-tab-bar">
        <div class="config-tab-pills">
          <div 
            v-for="(cfg, name) in store.configs" 
            :key="name"
            class="config-tab-pill"
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
              <span class="pill-icon">📦</span>
              <span class="pill-label">{{ name }}</span>
              <span 
                class="pill-close" 
                @click.stop="deleteConfigWithConfirm(name as string)"
                title="删除配置"
              >×</span>
            </template>
          </div>
        </div>
        <a-button size="small" class="add-cfg-btn" @click="addConfig">+ 添加配置</a-button>
      </div>



      <!-- 配置 Tab 右键菜单 -->
      <Teleport to="body">
        <div
          v-if="contextMenu.visible"
          class="cfg-context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
          @click="closeContextMenu"
        >
          <div class="cfg-context-item" @click="startRename(contextMenu.cfgName)">✏️ 重命名</div>
          <div class="cfg-context-item cfg-context-danger" @click="deleteConfig(contextMenu.cfgName)">🗑️ 删除</div>
        </div>
      </Teleport>

      <!-- 当前配置页内容 -->
      <template v-for="(cfg, name) in store.configs" :key="name">
        <div v-if="activeCfg === name" class="config-content">
          
          <!-- 🔧 配置基本信息（服务器型号 + 数量） -->
          <div class="cfg-basic-info glass">
            <div class="cfg-basic-row">
              <div class="cfg-basic-field">
                <label class="cfg-basic-label">🔧 服务器型号</label>
                <a-input
                  :value="cfg.server_model || ''"
                  @change="(e: Event) => cfg.server_model = (e.target as HTMLInputElement).value"
                  placeholder="输入服务器型号，如：PowerEdge R760"
                  size="small"
                  style="flex: 1"
                  :maxlength="100"
                />
              </div>
              <div class="cfg-basic-field cfg-basic-qty">
                <label class="cfg-basic-label">📊 数量</label>
                <a-input-number
                  v-model:value="store.configQuantities[String(name)]"
                  :min="1"
                  :max="9999"
                  size="small"
                  style="width: 120px"
                  addon-after="台"
                />
              </div>
            </div>
          </div>

          <!-- 📝 配置描述（可折叠） -->
          <div class="desc-box glass" :class="{ expanded: descExpanded[name] }">
            <div class="desc-header" @click="descExpanded[name] = !descExpanded[name]">
              <span class="desc-icon">📝</span>
              <span class="desc-title">配置描述</span>
              <span class="desc-preview" v-if="!descExpanded[name]">
                {{ cfg.description ? cfg.description.slice(0, 40) + (cfg.description.length > 40 ? '...' : '') : '（未填写）' }}
              </span>
              <span class="desc-toggle">{{ descExpanded[name] ? '收起 ▲' : '展开 ▼' }}</span>
            </div>
            <div v-if="descExpanded[name]" class="desc-body">
              <a-textarea
                v-model:value="cfg.description"
                placeholder="描述此配置方案的用途、客户需求等..."
                :rows="3"
                :maxlength="500"
                show-count
              />
            </div>
          </div>

          <!-- 横向分栏导航 -->
          <div class="section-nav glass">
            <div 
              class="section-nav-item" 
              :class="{ active: sectionState[name] === 'hardware' }"
              @click="sectionState[name] = 'hardware'"
            >
              <span class="nav-icon">🖥️</span>
              <span class="nav-label">硬件选配</span>
            </div>
            <div class="nav-separator"></div>
            <div 
              class="section-nav-item" 
              :class="{ active: sectionState[name] === 'warranty' }"
              @click="sectionState[name] = 'warranty'"
            >
              <span class="nav-icon">🛡️</span>
              <span class="nav-label">维保/增值服务</span>
            </div>
            <div class="nav-separator"></div>
            <div 
              class="section-nav-item" 
              :class="{ active: sectionState[name] === 'software' }"
              @click="sectionState[name] = 'software'"
            >
              <span class="nav-icon">💿</span>
              <span class="nav-label">系统/软件</span>
            </div>
          </div>

          <!-- 硬件选配区域 -->
          <div v-if="sectionState[name] === 'hardware'" class="section-content">
            <!-- L6 整机卡片 -->
            <div class="l6-section">
              <div class="l6-card-box glass">
                <div class="l6-card-header">
                  <span class="card-title-text">🏭 L6 整机报价</span>
                  <a-tag v-if="cfg.l6_matched_record?.match_type === '精确匹配'" color="success" style="margin-left: 10px;">✅ 已匹配</a-tag>
                  <a-tag v-else-if="cfg.l6_matched_record?.match_type === '未匹配'" color="warning" style="margin-left: 10px;">⚠️ 部分匹配</a-tag>
                  <a-tag v-else-if="cfg.l6_matched_record" color="success" style="margin-left: 10px;">✅ 已匹配</a-tag>
                  <a-tag v-else color="default" style="margin-left: 10px;">未解析</a-tag>
                </div>
                
                <!-- L6 三栏对比视图 -->
                <div v-if="cfg.l6_matched_record" class="l6-compare-view">
                  <!-- 左栏：Excel 需求 -->
                  <div class="l6-col">
                    <div class="l6-col-title">EXCEL 需求</div>
                    <div class="l6-compare-row">
                      <span class="compare-label">机型</span>
                      <span class="compare-value">{{ cfg.l6_meta?.model_name || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">机箱</span>
                      <span class="compare-value">{{ cfg.l6_meta?.chassis_form || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">盘位</span>
                      <span class="compare-value">{{ cfg.l6_meta?.drive_bays || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">电源</span>
                      <span class="compare-value">{{ cfg.l6_meta?.psu || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">主板</span>
                      <span class="compare-value">{{ cfg.l6_meta?.motherboard || '-' }}</span>
                    </div>
                    <div class="l6-compare-divider"></div>
                    <div class="l6-compare-row">
                      <span class="compare-label">背板</span>
                      <span class="compare-value">{{ cfg.l6_meta?.backplane_desc || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">GPU</span>
                      <span class="compare-value">{{ cfg.l6_meta?.gpu_expansion || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">电源线</span>
                      <span class="compare-value">{{ cfg.l6_meta?.power_cord || '-' }}</span>
                    </div>
                    <div class="l6-compare-row">
                      <span class="compare-label">导轨</span>
                      <span class="compare-value">{{ cfg.l6_meta?.rail_kit || '-' }}</span>
                    </div>
                  </div>
                  
                  <!-- 中栏：L6 匹配结果（使用公共卡片组件） -->
                  <div class="l6-col">
                    <div class="l6-col-title">L6 匹配结果</div>
                    <L6RecordCard 
                      :record="cfg.l6_matched_record" 
                      :show-actions="false" 
                      :matched="true"
                    />
                  </div>
                  
                  <!-- 右栏：定价 -->
                  <div class="l6-col l6-col-pricing">
                    <div class="l6-col-title">定价</div>
                    <div class="l6-pricing-grid">
                      <div class="pricing-item">
                        <label>底价</label>
                        <a-input-number v-model:value="cfg.items[0].base_price" size="small" style="width:100%" @blur="store.recalculateAll()" />
                      </div>
                      <div class="pricing-item">
                        <label>数量</label>
                        <a-input-number v-model:value="cfg.items[0].qty" size="small" style="width:100%" :min="1" @blur="store.recalculateAll()" />
                      </div>
                      <div class="pricing-item">
                        <label>利润率(%)</label>
                        <a-input-number v-model:value="cfg.items[0].profit_margin" size="small" style="width:100%" :min="0" @blur="store.recalculateAll()" />
                      </div>
                      <div class="pricing-divider"></div>
                      <div class="pricing-item pricing-total">
                        <label>销售总价</label>
                        <span class="price-val-lg">¥{{ settingsStore.formatNumber(cfg.items[0].final_price) }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 🎯 候选列表（有候选时显示，允许用户手动选择） -->
                <div v-if="cfg.l6_matched_record?.candidates?.length" class="l6-candidates glass-light">
                  <div class="candidates-header">
                    <span class="candidates-icon">🎯</span>
                    <span class="candidates-title">其他候选</span>
                    <span class="candidates-hint">点击可切换为当前匹配</span>
                  </div>
                  <div class="candidates-list">
                    <div v-for="(cand, ci) in cfg.l6_matched_record.candidates" :key="ci" class="candidate-row" :class="{ active: cand === cfg.l6_matched_record }">
                      <div class="candidate-dims">
                        <span class="candidate-chip">{{ cand.chassis || '-' }}</span>
                        <span class="candidate-chip">{{ cand.model || '-' }}</span>
                        <span class="candidate-chip">盘位{{ cand.drive_bays || '-' }}</span>
                        <span class="candidate-chip">{{ cand.psu || '-' }}</span>
                        <span class="candidate-chip">{{ cand.motherboard || '-' }}</span>
                      </div>
                      <div class="candidate-meta">
                        <span class="candidate-score">匹配度 {{ cand.match_score }}% ({{ cand.matched_dims }}/{{ cand.total_dims }})</span>
                        <span class="candidate-price">💰 ¥{{ settingsStore.formatNumber(cand.price || 0) }}</span>
                        <a-button 
                          v-if="cand !== cfg.l6_matched_record"
                          size="small" 
                          type="primary" 
                          ghost
                          @click="selectL6Candidate(name, cand)"
                        >选择此机型</a-button>
                        <a-tag v-else color="success">当前</a-tag>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- KP 配件卡片群 -->
            <div class="kp-section glass">
              <div class="section-header">
                <h3 class="section-title">🔩 Key Parts 配件</h3>
              </div>
              
              <div class="kp-grid">
                <div v-for="(item, idx) in cfg.items.filter((i: any) => i.category === 'Key Parts')" :key="idx" class="kp-card glass-light">
                  <div class="kp-card-header">
                    <span class="kp-name">{{ item.part_name }}</span>
                    <span class="kp-spec" v-if="item.spec">({{ item.spec }})</span>
                  </div>
                  
                  <div class="kp-inputs">
                    <div class="input-group">
                      <label>数量</label>
                      <a-input-number v-model:value="item.qty" size="small" style="width:100%" :min="1" @blur="store.recalculateAll()" />
                    </div>
                    <div class="input-group">
                      <label>利润率%</label>
                      <a-input-number v-model:value="item.profit_margin" size="small" style="width:100%" :min="0" @blur="store.recalculateAll()" />
                    </div>
                    <div class="input-group">
                      <label>原始单价</label>
                      <a-input-number v-model:value="item.base_price" size="small" style="width:100%" :precision="2" @blur="store.recalculateAll()" />
                    </div>
                  </div>

                  <div class="kp-footer">
                    <div class="kp-price">
                      最终售价：<span class="price-val">¥ {{ settingsStore.formatNumber(item.final_price) }}</span>
                    </div>
                    <a-button 
                      size="small" 
                      type="primary" 
                      ghost 
                      class="sync-btn"
                      :disabled="!item.match_status?.includes('变动') && !item.match_status?.includes('缺失')"
                    >
                      📥 同步
                    </a-button>
                  </div>

                  <!-- KP 历史价格 (懒加载折叠面板) -->
                  <a-collapse class="kp-history-collapse" v-model:activeKey="item._histActiveKeys" @change="(keys: string[]) => onHistoryExpand(item, keys)">
                    <a-collapse-panel key="hist">
                      <template #header>
                        <span class="kp-hist-header">📈 历史价格 <span v-if="item._histLoaded">({{ item._history?.length || 0 }}条)</span><span v-else>…</span></span>
                      </template>
                      <div v-if="item._histLoading" class="kp-hist-loading"><a-spin size="small" /></div>
                      <div v-else-if="item._histLoaded && item._history?.length" class="kp-hist-list">
                        <div v-for="(h, hi) in item._history" :key="hi" class="kp-hist-item">
                          <div class="kp-hist-dot"></div>
                          <div class="kp-hist-content">
                            <div class="kp-hist-row">
                              <span class="kp-hist-date">{{ h.date }}</span>
                              <span class="kp-hist-price" :class="{ usd: h.currency === 'USD' }">
                                {{ h.currency === 'USD' ? '$' : '¥' }} {{ settingsStore.formatNumber(h.price || 0) }}
                              </span>
                            </div>
                            <div v-if="h.note" class="kp-hist-note">{{ h.note }}</div>
                          </div>
                        </div>
                      </div>
                      <div v-else class="kp-hist-empty">暂无历史价格</div>
                    </a-collapse-panel>
                  </a-collapse>
                </div>
              </div>
            </div>
          </div>

          <!-- 维保/增值服务区域 -->
          <div v-else-if="sectionState[name] === 'warranty'" class="section-content">
            <!-- L6/KP 质保服务费独立计算 -->
            <div class="warranty-bottom-row">
              <!-- L6 质保卡片 -->
              <div class="warranty-card-item glass-light">
                <div class="w-card-title">🏭 L6 质保服务费</div>
                <a-textarea 
                  class="w-description"
                  :value="getWarrantyDesc(cfg, 'l6')"
                  @change="(e: Event) => store.setWarrantyDescription(name, 'l6', (e.target as HTMLTextAreaElement).value)"
                  :auto-size="{ minRows: 2, maxRows: 4 }"
                  placeholder="质保描述..."
                />
                <div class="w-card-body">
                  <!-- 状态 -->
                  <div class="w-status" :class="{ detected: cfg.warranty_info?.l6?.detected }">
                    <span v-if="cfg.warranty_info?.l6?.detected">✅ 已识别（报价单包含）</span>
                    <span v-else>⚠️ 未检测到</span>
                  </div>
                  <!-- 年限 -->
                  <div class="w-row">
                    <span class="w-label">年限：</span>
                    <a-select 
                      :value="cfg.warranty_info?.l6?.years" 
                      size="small" 
                      style="width: 100px"
                      @change="(val: number) => store.setWarrantyYearsL6(name, val)"
                      :options="[
                        { value: 1, label: '1 年' },
                        { value: 2, label: '2 年' },
                        { value: 3, label: '3 年' },
                        { value: 5, label: '5 年' }
                      ]"
                      allowClear
                      placeholder="选择年限"
                    />
                  </div>
                  <!-- 费率 -->
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
                  <!-- 金额 -->
                  <div class="w-row">
                    <span class="w-label">金额：</span>
                    <span class="w-val">¥ {{ settingsStore.formatNumber(store.calcWarrantyFeeL6(name)) }}</span>
                  </div>
                  <!-- 清零按钮 -->
                  <div class="w-btns">
                    <a-button v-if="store.getWarrantyRateL6Pct(name) > 0" type="link" size="small" danger class="w-btn" @click="store.clearWarrantyL6(name)">✖ 清零</a-button>
                  </div>
                </div>
              </div>
              
              <!-- KP 质保卡片 -->
              <div class="warranty-card-item glass-light">
                <div class="w-card-title">🔩 KP 质保服务费</div>
                <a-textarea 
                  class="w-description"
                  :value="getWarrantyDesc(cfg, 'kp')"
                  @change="(e: Event) => store.setWarrantyDescription(name, 'kp', (e.target as HTMLTextAreaElement).value)"
                  :auto-size="{ minRows: 2, maxRows: 4 }"
                  placeholder="质保描述..."
                />
                <div class="w-card-body">
                  <!-- 状态 -->
                  <div class="w-status" :class="{ detected: cfg.warranty_info?.kp?.detected }">
                    <span v-if="cfg.warranty_info?.kp?.detected">✅ 已识别（报价单包含）</span>
                    <span v-else>⚠️ 未检测到</span>
                  </div>
                  <!-- 年限 -->
                  <div class="w-row">
                    <span class="w-label">年限：</span>
                    <a-select 
                      :value="cfg.warranty_info?.kp?.years" 
                      size="small" 
                      style="width: 100px"
                      @change="(val: number) => store.setWarrantyYearsKP(name, val)"
                      :options="[
                        { value: 1, label: '1 年' },
                        { value: 2, label: '2 年' },
                        { value: 3, label: '3 年' },
                        { value: 5, label: '5 年' }
                      ]"
                      allowClear
                      placeholder="选择年限"
                    />
                  </div>
                  <!-- 费率 -->
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
                  <!-- 金额 -->
                  <div class="w-row">
                    <span class="w-label">金额：</span>
                    <span class="w-val">¥ {{ settingsStore.formatNumber(store.calcWarrantyFeeKP(name)) }}</span>
                  </div>
                  <!-- 清零按钮 -->
                  <div class="w-btns">
                    <a-button v-if="store.getWarrantyRateKPPct(name) > 0" type="link" size="small" danger class="w-btn" @click="store.clearWarrantyKP(name)">✖ 清零</a-button>
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
      </template>
      
      <!-- 底部垫高 -->
      <div style="height: 80px;"></div>
    </div>

    <!-- 3. 底部悬浮操作栏 -->
    <div class="action-bar glass">
      <div class="action-bar-inner">
        <a-button @click="goBack" class="btn-secondary">{{ entryLabel || "🔙 返回上传" }}</a-button>
        
        <a-select
          v-model:value="selectedTemplateId"
          style="width: 200px"
          placeholder="选择导出模板"
        >
          <a-select-option v-for="t in templates" :key="t.id" :value="String(t.id)">
            {{ t.display_name }}{{ t.is_default ? ' (默认)' : '' }}
          </a-select-option>
        </a-select>
        
        <a-button @click="handlePreview" :loading="previewLoading" class="btn-secondary">👁 预览</a-button>
        <a-button @click="store.doExport(selectedTemplateId)" :loading="exportLoading" class="btn-secondary">📥 导出 Excel</a-button>
        <a-button type="primary" @click="handleSave()" :loading="saveLoading" class="btn-primary">💾 保存商机</a-button>
      </div>
    </div>

    <!-- 右侧抽屉：商机文件 + 评论 -->
    <OpportunitySidebar :opportunity-id="currentOpportunityId" />

    <!-- 预览弹窗 -->
    <PreviewModal v-model:open="previewVisible" :sheets="previewSheets" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQuoteStore, type ConfigData } from '@/store/quote'
import { useSettingsStore } from '@/store/settings'
import OpportunitySidebar from '@/components/quote/OpportunitySidebar.vue'
import PreviewModal from '@/components/quote/PreviewModal.vue'
import L6RecordCard from '@/components/L6RecordCard.vue'
import { message, Modal } from 'ant-design-vue'
import axios from 'axios'
import { exportTemplateApi, projectApi } from '@/api'

const store = useQuoteStore()
const settingsStore = useSettingsStore()
const route = useRoute()
const router = useRouter()
const activeCfg = ref('CFG1')

// 导出模板相关
const templates = ref<any[]>([])
const selectedTemplateId = ref<string>('')
const previewLoading = ref(false)
const previewVisible = ref(false)
const previewSheets = ref<any[]>([])

// 加载导出模板列表
const loadTemplates = async () => {
  try {
    const list = await exportTemplateApi.list()
    templates.value = list
    // 默认选中默认模板
    const defaultTemplate = list.find(t => t.is_default)
    if (defaultTemplate) {
      selectedTemplateId.value = String(defaultTemplate.id)
    }
  } catch (e) {
    console.error('加载模板列表失败', e)
  }
}

// 预览处理
const handlePreview = async () => {
  if (!selectedTemplateId.value) {
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
    
    const data = await projectApi.previewJson(opportunityId, selectedTemplateId.value)
    previewSheets.value = data.sheets || []
    previewVisible.value = true
  } catch (e) {
    console.error('预览失败', e)
    message.error('预览失败，请重试')
  } finally {
    previewLoading.value = false
  }
}

// 质保描述默认值
const WARRANTY_DESC_L6 = '质保3年，非人为及不可抗力引起的故障，软件FW问题支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。'
const WARRANTY_DESC_KP = '质保1年，非人为及不可抗力引起的故障，支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。'

const getWarrantyDesc = (cfg: any, type: 'l6' | 'kp'): string => {
  const desc = cfg.warranty_info?.[type]?.description
  if (desc) return desc
  return type === 'l6' ? WARRANTY_DESC_L6 : WARRANTY_DESC_KP
}
const saveLoading = ref(false)
const exportLoading = ref(false)

// 入口上下文（来自路由 query）: upload | opportunities
const entryFrom = computed(() => (route.query.from as string) || 'upload')
const entryProjectId = computed(() => (route.query.opportunityId as string) || '')
const entryLabel = computed(() => {
  if (entryFrom.value === 'opportunities') return '← 返回商机详情'
  if (entryFrom.value === 'upload') return '← 返回上传页'
  return ''
})
const goBack = () => {
  // Clean up sessionStorage to prevent stale data from being loaded next time
  sessionStorage.removeItem('quotation_data')
  if (entryFrom.value === 'opportunities' && entryProjectId.value) {
    router.push(`/opportunities/${entryProjectId.value}`)
  } else if (entryFrom.value === 'upload') {
    router.push('/upload')
  } else {
    router.push('/opportunities')
  }
}

// 当前商机 ID（用于评论关联）
// 优先用 opportunity_id，没有则用 opportunity_name，都没有则用 'default'
const currentOpportunityId = computed(() => {
  return store.opportunityInfo?.opportunity_id || store.opportunityInfo?.opportunity_name || 'default'
})

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
  
  // 更新质保费率
  if (store.warrantyRates[oldName]) {
    store.warrantyRates[newName] = store.warrantyRates[oldName]
    delete store.warrantyRates[oldName]
  }
  
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
  delete store.warrantyRates[cfgName]
  delete sectionState[cfgName]
  
  // 如果删除的是当前激活的配置，切换到第一个
  const remainingKeys = Object.keys(store.configs)
  if (activeCfg.value === cfgName) {
    activeCfg.value = remainingKeys[0] || ''
  }
  
  message.success(`已删除配置 "${cfgName}"`)
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
    items: [],
    summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
    l6_matched_record: null,
    l6_meta: {},
    warranty_info: {
      l6: { detected: false, years: null, rate: 0 },
      kp: { detected: false, years: null, rate: 0 }
    }
  }
  activeCfg.value = newName
  sectionState[newName] = 'hardware'
  message.success(`已添加配置页 ${newName}`)
}

// 选择 L6 候选机型
const selectL6Candidate = (cfgName: string, candidate: any) => {
  const cfg = store.configs[cfgName]
  if (!cfg) return
  // 将选中的候选设为当前匹配记录（移除 candidates 字段避免嵌套）
  const { candidates, ...rest } = candidate
  cfg.l6_matched_record = { ...rest, match_type: '手动选择' }
  store.recalculateAll()
  message.success(`已选择 ${candidate.model || candidate.chassis || '该机型'}`)
}

const handleSave = async () => {
  // Check for zero-price parts
  const zeroPriceParts = []
  for (const [cfgName, cfg] of Object.entries(store.configs)) {
    for (const item of cfg.items) {
      if (item.base_price === 0 || item.final_price === 0) {
        zeroPriceParts.push({ cfg: cfgName, part: item.part_name })
      }
    }
  }
  
  if (zeroPriceParts.length > 0) {
    const confirmed = await Modal.confirm({
      title: '⚠️ 存在价格为 0 的配件',
      content: `以下配件价格为 0，可能导致整机成本偏低：\n${zeroPriceParts.map(p => `• ${p.cfg}: ${p.part}`).join('\n')}\n\n确定要保存吗？`,
      okText: '继续保存',
      cancelText: '取消',
    })
    if (!confirmed) return
  }
  
  saveLoading.value = true
  try {
    await store.saveProject()
  } finally {
    saveLoading.value = false
  }
}

// 当前配置页的财务数据（随 tab 切换动态变化，计算逻辑已下沉到 store）
const configTotals = computed(() => store.calcConfigTotals(activeCfg.value))

// 对比逻辑：判断匹配状态
const getCompareStatus = (cfg: ConfigData, field: string): string => {
  const meta = cfg.l6_meta
  const matched = cfg.l6_matched_record
  if (!meta || !matched) return ''
  
  const metaValue = (meta as any)[field === 'model' ? 'model_name' : field]
  const matchedValue = (matched as any)[field]
  
  if (!metaValue || !matchedValue) return ''
  
  // 精确匹配
  if (metaValue === matchedValue) return 'status-match'
  
  // 模糊匹配（包含关系）
  if (String(matchedValue).includes(metaValue) || String(metaValue).includes(matchedValue)) {
    return 'status-fuzzy'
  }
  
  return 'status-mismatch'
}

const getCompareIcon = (cfg: ConfigData, field: string): string => {
  const status = getCompareStatus(cfg, field)
  if (status === 'status-match') return '✅'
  if (status === 'status-fuzzy') return '⚠️'
  if (status === 'status-mismatch') return '❌'
  return '-'
}

// KP 历史价格懒加载
const onHistoryExpand = async (item: any, keys: string[]) => {
  // Only load when expanded (keys contains 'hist')
  if (!keys.includes('hist')) return
  if (item._histLoaded) return  // Already loaded

  item._histLoading = true
  try {
    const model = item.spec || item.part_name
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

onMounted(async () => {
  // 加载导出模板列表
  await loadTemplates()
  
  // Check routing context
  const quotationId = route.query.quotationId as string
  const mode = route.query.mode as string
  const opportunityId = route.query.opportunityId as string

  if (mode === 'create') {
    // 新建报价单：清除残留数据，初始化空白工作台
    sessionStorage.removeItem('quotation_data')
    // 把路由里的 opportunityId 写入 store，预览/导出/保存都要用
    if (opportunityId) {
      store.opportunityInfo.opportunity_id = opportunityId
    }
    // 初始化一个空白配置页
    store.configs['CFG1'] = {
      name: 'CFG1',
      items: [],
      summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
      l6_matched_record: null,
      l6_meta: {},
      warranty_info: {
        l6: { detected: false, years: null, rate: 0 },
        kp: { detected: false, years: null, rate: 0 }
      }
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
      for (const item of items) {
        const cfgName = item.config_name || 'CFG1'
        if (!configs[cfgName]) {
          configs[cfgName] = {
            name: cfgName,
            description: configDescriptions[cfgName] || '',
            server_model: configServerModels[cfgName] || '',
            items: [],
            summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
            l6_matched_record: null,
            l6_meta: {},
            warranty_info: {
              l6: { detected: false, years: null, rate: 0 },
              kp: { detected: false, years: null, rate: 0 }
            }
          }
        }
        configs[cfgName].items.push(item)
      }
      
      // 🎯 Apply per-config L6 matching results from API
      const perCfgL6 = quotation.per_cfg_l6 || {}
      for (const [cfgName, l6Data] of Object.entries(perCfgL6)) {
        if (configs[cfgName]) {
          configs[cfgName].l6_matched_record = (l6Data as any).l6_matched_record || null
          configs[cfgName].l6_meta = (l6Data as any).l6_meta || {}
        }
      }
      
      // Fallback: if no per-config data, apply top-level to first config
      if (Object.keys(perCfgL6).length === 0 && quotation.l6_matched_record) {
        const cfgName = Object.keys(configs)[0] || 'CFG1'
        if (configs[cfgName]) {
          configs[cfgName].l6_matched_record = quotation.l6_matched_record
          configs[cfgName].l6_meta = quotation.l6_meta || {}
        }
      }
      
      // Ensure at least one config even if no items
      if (Object.keys(configs).length === 0) {
        configs['CFG1'] = {
          name: 'CFG1',
          items: [],
          summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
          l6_matched_record: quotation.l6_matched_record || null,
          l6_meta: quotation.l6_meta || {},
          warranty_info: {
            l6: { detected: false, years: null, rate: 0 },
            kp: { detected: false, years: null, rate: 0 }
          }
        }
      }
      
      const opportunityInfo = {
        opportunity_id: quotation.opportunity_id || opportunityId,
        opportunity_name: quotation.opportunity_name || '',
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
      }
      
      // 传递 config_quantities 到 store
      const configQuantities = quotation.config_quantities || {}
      
      store.loadData({ configs, project_info: opportunityInfo, config_quantities: configQuantities })
      message.success("已加载报价单数据")
    } catch (err) {
      console.error("加载报价单失败", err)
      message.error("加载报价单失败")
    }
  } else {
    // 从 sessionStorage 加载（上传后跳转场景，保留向后兼容）
    const dataStr = sessionStorage.getItem('quotation_data')
    if (dataStr) {
      try {
        store.loadData(JSON.parse(dataStr))
      } catch (e) {
        console.error("解析上传数据失败", e)
      }
    } else {
      console.log("📝 空工作台")
    }
  }
  initSectionState()
  store.recalculateAll()
})
</script>

<style scoped>
.workspace-page {
  position: relative;
  min-height: 100vh;
  background: var(--cpq-bg-primary);
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

/* ============================================
   1. Sticky KPI Dashboard
   ============================================ */
.kpi-sticky {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--cpq-overlay-b85);
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  border-bottom: 1px solid var(--cpq-border-secondary);
  padding: 16px 24px;
}

.kpi-container {
  max-width: 1600px;
  margin: 0 auto;
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 0;
}

.kpi-cell {
  flex: 1;
  position: relative;
  padding: 12px 20px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.kpi-cell::before {
  content: '';
  position: absolute;
  left: 0;
  top: 20%;
  bottom: 20%;
  width: 3px;
  background: var(--cpq-accent-primary);
  border-radius: 2px;
}

.kpi-cell:first-child::before {
  display: none;
}

.kpi-divider {
  width: 1px;
  background: var(--cpq-overlay-w6);
  margin: 8px 0;
}

.kpi-label {
  font-size: 11px;
  text-transform: uppercase;
  color: var(--cpq-text-muted);
  letter-spacing: 0.5px;
  margin-bottom: 2px;
}

.kpi-sublabel {
  font-size: 10px;
  color: var(--cpq-text-disabled);
  margin-bottom: 4px;
}

.kpi-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.5px;
}

.color-positive {
  color: var(--cpq-accent-success) !important;
}

.color-negative {
  color: var(--cpq-accent-danger) !important;
}

/* ============================================
   2. Content Flow
   ============================================ */
.content-inner {
  max-width: 1600px;
  margin: 0 auto;
  padding: 24px;
}

/* ============================================
   3. Config Tab Bar (Glass Pill)
   ============================================ */
.config-tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  gap: 16px;
}

.config-tab-pills {
  display: flex;
  gap: 8px;
  background: var(--cpq-overlay-b20);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 12px;
  padding: 6px;
}

.config-tab-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  color: var(--cpq-text-muted);
  font-size: 13px;
  font-weight: 500;
}

.config-tab-pill:hover {
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w4);
}

.config-tab-pill:hover .pill-close {
  opacity: 1;
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

.pill-close:hover {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.config-tab-pill.active {
  background: var(--cpq-accent-primary);
  color: var(--cpq-text-primary);
  font-weight: 600;
}

.pill-icon {
  font-size: 14px;
}

.pill-label {
  font-weight: 600;
}

.add-cfg-btn {
  border: 1px dashed var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: transparent !important;
  font-size: 12px;
}

.add-cfg-btn:hover {
  background: var(--cpq-overlay-a10) !important;
}

/* ============================================
   4. Section Nav (Underline Style)
   ============================================ */
.section-nav {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
  border-bottom: none;
}

.section-nav-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 20px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: var(--cpq-text-secondary);
  transition: all var(--cpq-transition-fast);
  position: relative;
}

.section-nav-item:hover {
  color: var(--cpq-text-primary);
}

.section-nav-item.active {
  color: var(--cpq-text-primary);
  font-weight: 600;
}

.section-nav-item.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 20%;
  right: 20%;
  height: 2px;
  background: var(--cpq-accent-primary);
  border-radius: 2px 2px 0 0;
}

.nav-separator {
  width: 1px;
  height: 20px;
  background: var(--cpq-overlay-w6);
}

.nav-icon {
  font-size: 16px;
}

.nav-label {
  font-size: 13px;
}

/* ============================================
   5. Section Content
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
   6. L6 Section (Three-Column Glass)
   ============================================ */
.l6-section {
  margin-bottom: 24px;
}

/* L6 与 KP 之间的分隔线 */
.l6-section + .kp-section {
  border-top: 1px solid var(--cpq-overlay-a8);
  padding-top: 24px;
}

.l6-card-box {
  border-radius: 12px;
  overflow: hidden;
}

.l6-card-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--cpq-border-secondary);
  display: flex;
  align-items: center;
}

.card-title-text {
  color: var(--cpq-text-primary);
  font-weight: 600;
  font-size: 15px;
}

.l6-compare-view {
  display: flex;
  background: var(--cpq-overlay-b15);
}

.l6-col {
  flex: 1;
  padding: 20px;
  border-right: 1px solid var(--cpq-overlay-w6);
}

.l6-col:last-child {
  border-right: none;
}

.l6-col-pricing {
  flex: 0 0 280px;
}

.l6-col-title {
  font-size: 11px;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--cpq-text-muted);
  text-align: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--cpq-border-secondary);
  letter-spacing: 1px;
}

.l6-compare-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}

.compare-label {
  flex: 0 0 56px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.compare-value {
  flex: 1;
  color: var(--cpq-text-primary);
  font-weight: 500;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compare-dot {
  flex: 0 0 10px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--cpq-text-disabled);
}

.compare-dot.status-match {
  background: var(--cpq-accent-success);
  box-shadow: 0 0 6px var(--cpq-overlay-a40);
}

.compare-dot.status-fuzzy {
  background: var(--cpq-accent-warning);
  box-shadow: 0 0 6px var(--cpq-overlay-warn30);
}

.compare-dot.status-mismatch {
  background: var(--cpq-accent-danger);
  box-shadow: 0 0 6px var(--cpq-overlay-danger15);
}

.l6-compare-divider {
  height: 1px;
  background: var(--cpq-border-secondary);
  margin: 12px 0;
}

.l6-match-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.l6-summary-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.summary-label {
  color: var(--cpq-text-secondary);
}

.summary-value {
  color: var(--cpq-text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.price-accent {
  color: var(--cpq-accent-primary) !important;
  font-size: 16px;
}

.l6-pricing-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pricing-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pricing-item label {
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.pricing-divider {
  height: 1px;
  background: var(--cpq-border-secondary);
  margin: 8px 0;
}

.pricing-total .price-val-lg {
  font-size: 22px;
  color: var(--cpq-accent-primary) !important;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* ============================================
   7. KP Section (Glass Cards Grid)
   ============================================ */
.kp-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  font-size: 16px;
  color: var(--cpq-text-primary) !important;
  font-weight: 600;
}

.kp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.kp-card {
  border-radius: 12px;
  padding: 16px;
  transition: all var(--cpq-transition-fast);
  background: var(--cpq-overlay-b20) !important;
  border: 1px solid var(--cpq-overlay-w6) !important;
}

.kp-card:hover {
  border-color: var(--cpq-accent-primary) !important;
  transform: translateY(-2px);
  box-shadow: 0 8px 24px var(--cpq-overlay-a10);
}

.kp-card-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.kp-name {
  color: var(--cpq-text-primary);
  font-weight: 600;
  font-size: 14px;
}

.kp-spec {
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-weight: normal;
}

.kp-inputs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.input-group label {
  font-size: 10px;
  color: var(--cpq-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.kp-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px dashed var(--cpq-border-secondary);
}

.kp-price {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.price-val {
  color: var(--cpq-accent-primary) !important;
  font-weight: 700;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.sync-btn {
  font-size: 11px;
  padding: 0 8px;
}

/* KP 历史价格折叠面板 */
.kp-history-collapse {
  margin-top: 12px;
}

.kp-history-collapse :deep(.ant-collapse) {
  background: transparent;
  border: none;
}

.kp-history-collapse :deep(.ant-collapse-header) {
  padding: 6px 0 !important;
  font-size: 11px;
  color: var(--cpq-text-muted) !important;
}

.kp-history-collapse :deep(.ant-collapse-content-box) {
  padding: 8px 0 !important;
  background: var(--cpq-overlay-b15);
  border-radius: 6px;
  margin-top: 4px;
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
  background: var(--cpq-accent-success);
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
  color: var(--cpq-accent-success);
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

.kp-hist-empty {
  font-size: 11px;
  color: var(--cpq-text-muted);
  text-align: center;
  padding: 12px 0;
}

/* ============================================
   8. Warranty Section (Glass Cards)
   ============================================ */
.warranty-bottom-row {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
}

.warranty-card-item {
  flex: 1;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.warranty-card-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--cpq-accent-primary);
}

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

.w-status {
  font-size: 12px;
  color: var(--cpq-text-muted);
  padding: 6px 12px;
  background: var(--cpq-overlay-w4);
  border-radius: 6px;
  margin-bottom: 6px;
}

.w-status.detected {
  color: var(--cpq-accent-success);
  background: var(--cpq-overlay-a10);
}

.w-row {
  display: flex;
  justify-content: center;
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
  color: var(--cpq-accent-warning) !important;
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.w-btn {
  align-self: center;
  margin-top: 6px;
}

.w-btns {
  display: flex;
  justify-content: center;
  margin-top: 6px;
  min-height: 28px;
}

/* ============================================
   9. Action Bar (Sticky Bottom)
   ============================================ */
.action-bar {
  position: sticky;
  bottom: 0;
  padding: 16px 24px;
  border-top: none;
  z-index: 99;
}

.action-bar-inner {
  max-width: 1600px;
  margin: 0 auto;
  display: flex;
  justify-content: center;
  gap: 16px;
}

.btn-secondary {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
  font-size: 13px;
  padding: 8px 20px;
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.btn-secondary:hover {
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: var(--cpq-overlay-a5) !important;
}

.btn-primary {
  background: var(--cpq-accent-primary) !important;
  border: 1px solid var(--cpq-accent-primary) !important;
  color: var(--cpq-bg-primary) !important;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 24px;
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.btn-primary:hover {
  background: var(--cpq-accent-primary-light) !important;
  box-shadow: 0 0 20px var(--cpq-overlay-a40);
}

/* ============================================
   10. Inputs (Dark Theme)
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

/* ============================================
   11. 配置基本信息（服务器型号 + 数量）
   ============================================ */
.cfg-basic-info {
  margin-bottom: 16px;
  border-radius: 12px;
  padding: 16px;
}

.cfg-basic-row {
  display: flex;
  gap: 24px;
  align-items: flex-end;
}

.cfg-basic-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cfg-basic-field:first-child {
  flex: 1;
}

.cfg-basic-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ============================================
   12. 配置描述框
   ============================================ */
.desc-box {
  margin-bottom: 16px;
  border-radius: 12px;
  overflow: hidden;
  transition: all var(--cpq-transition-fast);
}

.desc-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  gap: 8px;
}

.desc-icon {
  font-size: 16px;
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
  padding: 0 16px 16px;
}

.desc-box.expanded {
  box-shadow: 0 4px 12px var(--cpq-overlay-b20);
}

/* ============================================
   12. L6 候选列表
   ============================================ */
.l6-candidates {
  margin-top: 16px;
  padding: 16px;
  border-radius: 8px;
  background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w8);
}

.candidates-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
}

.candidates-icon {
  font-size: 16px;
}

.candidates-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-size: 14px;
}

.candidates-hint {
  color: var(--cpq-text-secondary);
  font-size: 12px;
  margin-left: auto;
}

.candidates-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.candidate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-radius: 6px;
  background: var(--cpq-overlay-b20);
  border: 1px solid var(--cpq-overlay-w6);
  transition: all 0.2s;
}

.candidate-row:hover {
  background: var(--cpq-overlay-b30);
  border-color: var(--cpq-accent-primary);
}

.candidate-row.active {
  background: var(--cpq-overlay-a5);
  border-color: var(--cpq-accent-primary);
}

.candidate-dims {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.candidate-chip {
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.candidate-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.candidate-score {
  color: var(--cpq-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.candidate-price {
  color: var(--cpq-accent-primary);
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
}

/* ============================================
   13. Finance Settings Popover
   ============================================ */
.kpi-settings-cell {
  flex: 0 0 auto !important;
  padding: 12px 16px !important;
  display: flex;
  align-items: center;
  justify-content: center;
}

.kpi-settings-cell::before {
  display: none !important;
}

.kpi-settings-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
}

.kpi-settings-btn:hover {
  background: var(--cpq-overlay-a10);
  border-color: var(--cpq-accent-primary);
}

.kpi-settings-btn span {
  font-size: 16px;
}

.finance-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 200px;
  padding: 4px 0;
}

.finance-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.finance-setting-row label {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
}

.finance-setting-hint {
  font-size: 11px;
  color: var(--cpq-text-disabled);
  text-align: center;
  padding-top: 4px;
  border-top: 1px solid var(--cpq-overlay-w6);
}

/* ============================================
   14. Config Tab Edit & Context Menu
   ============================================ */
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

.cfg-context-menu {
  position: fixed;
  z-index: 9999;
  background: rgba(20, 22, 26, 0.95);
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 8px;
  padding: 4px;
  min-width: 140px;
  box-shadow: 0 8px 24px var(--cpq-overlay-b40);
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

/* ============================================
   15. Config Quantity Box
   ============================================ */
.qty-box {
  padding: 12px 16px;
  margin-bottom: 16px;
}

.qty-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.qty-icon {
  font-size: 14px;
}

.qty-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.qty-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.qty-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.qty-label {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  font-weight: 500;
  min-width: 40px;
}
</style>
