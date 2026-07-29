<template>
  <div class="parts-page">
    <!-- =================== Page Header =================== -->
    <div class="page-header">
      <div class="page-title-group">
        <h1><DatabaseOutlined class="page-title-icon" />配件管理</h1>
        <p class="page-subtitle">共 <span class="num">{{ totalPartCount }}</span> 个配件 · <span class="num">{{ categories.length }}</span> 个分类</p>
      </div>
      <div class="header-actions">
        <div class="seg-nav">
          <button :class="['seg-item', { active: viewMode === 'card' }]" @click="viewMode = 'card'">
            <AppstoreOutlined />卡片
          </button>
          <button :class="['seg-item', { active: viewMode === 'table' }]" @click="viewMode = 'table'">
            <UnorderedListOutlined />表格
          </button>
        </div>
        <a-button size="small" @click="importModalVisible = true">
          <template #icon><UploadOutlined /></template>
          导入
        </a-button>
        <a-button size="small" @click="exportParts">
          <template #icon><DownloadOutlined /></template>
          导出
        </a-button>
        <a-button
          size="small"
          :disabled="!hasSelectedCategory"
          :title="!hasSelectedCategory ? '请先在左侧选择分类' : '同分类按规格分组的价格分布'"
          @click="openMatrixDrawer"
        >
          <template #icon><BarChartOutlined /></template>
          比价矩阵
        </a-button>
        <a-button size="small" title="最新价 vs N 天前涨跌幅 TOP" @click="openMoversDrawer">
          <template #icon><StockOutlined /></template>
          价格异动
        </a-button>
        <a-button type="primary" size="small" @click="openCreatePartModal">
          <template #icon><PlusOutlined /></template>
          新增配件
        </a-button>
      </div>
    </div>

    <div class="main-layout">
      <!-- =================== Left Sidebar: 分类导航 =================== -->
      <aside class="category-sidebar glass">
        <div class="sidebar-title">分类</div>
        <div :class="['sidebar-item', { active: !selectedCategoryId && !listAllMode }]" @click="selectCategory(null)">
          <UnorderedListOutlined class="sidebar-ico" />
          <span class="sidebar-item-name">全部</span>
          <span class="sidebar-item-count">{{ totalPartCount }}</span>
        </div>
        <div
          v-for="cat in categories"
          :key="cat.id"
          :class="['sidebar-item', { active: selectedCategoryId === cat.id }]"
          @click="selectCategory(cat.id)"
        >
          <span class="sidebar-dot"></span>
          <span class="sidebar-item-name">{{ cat.name }}</span>
          <span class="sidebar-item-count">{{ cat.count }}</span>
        </div>
        <div class="sidebar-footer">
          <button class="sidebar-manage-btn" @click="categoryManageVisible = true">
            <SettingOutlined /> 管理分类
          </button>
        </div>
      </aside>

      <!-- =================== Main Content =================== -->
      <div class="content-area">
        <!-- ====== 总览仪表盘（选中「全部」且非清单模式） ====== -->
        <template v-if="!selectedCategoryId && !listAllMode">
          <div class="stats-row">
            <div class="stat-card glass-light">
              <div class="stat-label">配件总数</div>
              <div class="stat-value">{{ stats.total ?? '—' }}</div>
              <div class="stat-foot">
                <span :class="['stat-delta', deltaClass]">相较上周 {{ delta >= 0 ? '+' : '' }}{{ delta }}</span>
              </div>
              <VChart v-if="sparkOption" :option="sparkOption" :init-options="{ renderer: 'canvas' }" :autoresize="true" class="stat-spark" />
            </div>
            <div class="stat-card glass-light">
              <div class="stat-label">本周新增</div>
              <div class="stat-value">{{ stats.this_week_new ?? '—' }}</div>
              <div class="stat-foot"><span class="stat-sub">最近 7 天新入库</span></div>
            </div>
            <div class="stat-card glass-light">
              <div class="stat-label">有效价格配件</div>
              <div class="stat-value">{{ stats.valid_price_count ?? '—' }}</div>
              <div class="stat-foot"><span class="stat-sub">最近两日内有报价</span></div>
            </div>
            <div class="stat-card glass-light clickable" @click="openDuplicates">
              <div class="stat-label">疑似重复</div>
              <div class="stat-value">{{ duplicatesData.total_groups }}<span class="stat-unit"> 组</span></div>
              <div class="stat-foot">
                <span class="stat-sub" v-if="duplicatesData.total_duplicate_parts">{{ duplicatesData.total_duplicate_parts }} 件待核实 →</span>
                <span class="stat-sub" v-else>库内无重复</span>
              </div>
            </div>
          </div>

          <!-- 价格异动已移至工具栏按钮 + 抽屉（openMoversDrawer），非常驻面板 -->

          <div class="recent-grid">
            <div class="recent-panel glass-light">
              <div class="recent-head"><h4>最近新入库</h4></div>
              <div v-if="stats.recent_parts && stats.recent_parts.length" class="recent-list">
                <div v-for="p in stats.recent_parts" :key="p.id" class="recent-row" @click="openPartDetail(p.id)">
                  <div class="rr-main">
                    <span class="rr-name">{{ p.name }}</span>
                    <span class="rr-cat" v-if="p.category_name">{{ p.category_name }}</span>
                  </div>
                  <span class="rr-meta">{{ formatDate(p.created_at) }}</span>
                </div>
              </div>
              <div v-else class="recent-empty">暂无新入库配件</div>
            </div>
            <div class="recent-panel glass-light">
              <div class="recent-head"><h4>最近更新价格</h4></div>
              <div v-if="stats.recent_price_updates && stats.recent_price_updates.length" class="recent-list">
                <div v-for="p in stats.recent_price_updates" :key="p.id" class="recent-row" @click="openPartDetail(p.id)">
                  <div class="rr-main">
                    <span class="rr-name">{{ p.name }}</span>
                    <span class="rr-cat" v-if="p.category_name">{{ p.category_name }}</span>
                  </div>
                  <span class="rr-price" v-if="p.latest_price != null">{{ currencySymbol(p.latest_currency) }} {{ formatPrice(p.latest_price) }}</span>
                  <span class="rr-meta" v-else>—</span>
                </div>
              </div>
              <div v-else class="recent-empty">暂无价格更新</div>
            </div>
          </div>

          <span class="all-list-link" @click="listAllMode = true">浏览全部配件清单 →</span>
        </template>

        <!-- ====== 列表视图（具体分类 或 全部清单模式） ====== -->
        <template v-else>
        <div v-if="listAllMode && !selectedCategoryId" class="list-mode-banner">
          <button class="back-overview" @click="listAllMode = false">← 返回总览</button>
        </div>
        <!-- Toolbar -->
        <div class="toolbar glass-light">
          <a-input-search
            v-model:value="searchText"
            placeholder="搜索配件名称、SKU、品牌..."
            class="toolbar-search"
            @search="loadParts"
            allow-clear
          >
            <template #prefix>
              <SearchOutlined style="color: var(--cpq-text-muted)" />
            </template>
          </a-input-search>
          <a-select v-model:value="sortBy" class="toolbar-sort" @change="loadParts">
            <a-select-option value="name-asc">名称 A→Z</a-select-option>
            <a-select-option value="name-desc">名称 Z→A</a-select-option>
            <a-select-option value="price-asc">价格 低→高</a-select-option>
            <a-select-option value="price-desc">价格 高→低</a-select-option>
          </a-select>
          <a-select
            v-model:value="selectedBrands"
            mode="multiple"
            :options="brandOptions"
            placeholder="品牌"
            class="toolbar-brand"
            allow-clear
            @change="applyFilters"
          />
          <a-radio-group v-model:value="priceFilter" button-style="solid" class="toolbar-price" @change="applyFilters">
            <a-radio-button value="">全部</a-radio-button>
            <a-radio-button value="has_price">有报价</a-radio-button>
            <a-radio-button value="multi">≥3条</a-radio-button>
            <a-radio-button value="no_price">暂无报价</a-radio-button>
          </a-radio-group>
          <span class="toolbar-count">共 <b>{{ partsTotal }}</b> 个配件</span>
        </div>

        <!-- 规格维度（随分类变化，第二行 chips，超过 3 个维度可展开） -->
        <div v-if="hasSelectedCategory && visibleSpecKeys.length" class="spec-bar glass-light">
          <span class="spec-bar-label">规格</span>
          <div class="spec-bar-chips">
            <template v-for="key in visibleSpecKeys" :key="key">
              <span
                v-for="fv in specFacets[key]"
                :key="key + '_' + fv.value"
                :class="['spec-chip', { active: (selectedSpecs[key] || []).includes(fv.value) }]"
                @click="toggleSpec(key, fv.value)"
              >{{ fv.value }}<span class="spec-chip-count">{{ fv.count }}</span></span>
            </template>
          </div>
          <button v-if="specKeys.length > 3" class="spec-more" @click="specExpanded = !specExpanded">
            {{ specExpanded ? '收起' : '更多 ▾' }}
          </button>
        </div>

        <!-- 比价矩阵已移至工具栏按钮 + 抽屉（openMatrixDrawer），非常驻面板 -->

        <!-- Card View -->
        <div v-if="viewMode === 'card'" class="card-grid">
          <div
            v-for="(part, idx) in parts"
            :key="part.id"
            :class="['model-card', 'glass-light', { 'no-price-card': part.latest_price == null }]"
            :style="{ animationDelay: (idx % 20) * 30 + 'ms' }"
            @click="openPartDetail(part.id)"
          >
            <div class="card-accent-bar"></div>
            <div class="card-header">
              <span class="card-category-tag">{{ part.category_name || '未分类' }}</span>
              <button class="card-edit-btn" @click.stop="openEditPartModal(part)"><EditOutlined /></button>
            </div>
            <div class="card-name" :title="part.name">{{ part.name }}</div>
            <div class="card-sku" v-if="part.oem_sku">
              <span class="sku-label">SKU</span>
              <span class="sku-value" @click.stop="copyText(part.oem_sku)">{{ part.oem_sku }}</span>
            </div>
            <div class="card-price">
              <span class="price-value" v-if="part.latest_price != null"><span class="price-sym">{{ currencySymbol(part.latest_currency) }}</span> {{ formatPrice(part.latest_price) }}</span>
              <span class="price-value no-price" v-else>暂无报价</span>
              <span class="price-date" v-if="part.latest_date">{{ part.latest_date }}</span>
            </div>
            <div class="card-meta" v-if="part.brand || part.condition">
              <a-tag size="small" v-if="part.brand">{{ part.brand }}</a-tag>
              <span v-if="part.condition" :class="['cpq-led', conditionClass(part.condition)]">{{ part.condition }}</span>
            </div>
          </div>
        </div>

        <!-- Card Pagination -->
        <div v-if="viewMode === 'card' && partsTotal > 0" class="card-pagination">
          <a-pagination
            v-model:current="pagination.current"
            :total="partsTotal"
            :page-size="pagination.pageSize"
            :page-size-options="['20', '40', '60']"
            show-size-changer
            size="small"
            @change="onCardPageChange"
          />
        </div>

        <!-- Table View -->
        <div v-if="viewMode === 'table'" class="glass-light table-wrap">
          <a-table
            :columns="tableColumns"
            :data-source="parts"
            :loading="partsLoading"
            :pagination="tablePagination"
            @change="handleTableChange"
            row-key="id"
            size="small"
            :scroll="{ x: 1200 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <a @click="openPartDetail(record.id)">{{ record.name }}</a>
              </template>
              <template v-if="column.key === 'latest_price'">
                <span class="table-price" v-if="record.latest_price != null">{{ currencySymbol(record.latest_currency) }} {{ formatPrice(record.latest_price) }}</span>
                <span v-else class="no-price">—</span>
              </template>
              <template v-if="column.key === 'action'">
                <a-button type="link" size="small" @click="openPartDetail(record.id)">详情</a-button>
                <a-button type="link" size="small" @click="openEditPartModal(record)">编辑</a-button>
              </template>
            </template>
          </a-table>
        </div>

        <!-- Loading / Empty -->
        <div v-if="partsLoading" class="loading-state">
          <a-spin tip="加载中..." />
        </div>
        <div v-if="!partsLoading && parts.length === 0" class="empty-state">
          <InboxOutlined class="empty-icon" v-if="!searchText" />
          <SearchOutlined class="empty-icon" v-else />
          <div class="empty-text">{{ searchText ? '未找到匹配的配件' : '暂无配件数据' }}</div>
          <a-button v-if="!searchText" type="primary" size="small" @click="openCreatePartModal">
            <template #icon><PlusOutlined /></template>新增第一个配件
          </a-button>
          <a-button v-else size="small" @click="clearSearch">清除搜索</a-button>
        </div>
      </template>
      </div>
    </div>

    <!-- =================== Part Detail Drawer =================== -->
    <a-drawer
      v-model:open="detailDrawerVisible"
      width="640"
      :destroyOnClose="true"
    >
      <template #title>
        <div class="drawer-title" v-if="detailPart">
          <span class="drawer-title-name">{{ detailPart.name }}</span>
          <a-tag size="small" v-if="detailPart.brand">{{ detailPart.brand }}</a-tag>
          <a-tag size="small" v-if="detailPart.category_name">{{ detailPart.category_name }}</a-tag>
        </div>
        <span v-else>配件详情</span>
      </template>
      <template v-if="detailPart">
        <!-- Basic Info -->
        <div class="detail-section">
          <h4>基础信息</h4>
          <div class="detail-grid">
            <div class="detail-field">
              <span class="field-label">分类</span>
              <span class="field-value">{{ detailPart.category_name || '未分类' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">OEM SKU</span>
              <span class="field-value" @click="copyText(detailPart.oem_sku)">{{ detailPart.oem_sku || '—' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">替代料号</span>
              <span class="field-value">{{ detailPart.alt_sku || '—' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">品牌</span>
              <span class="field-value">{{ detailPart.brand || '—' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">成色</span>
              <span class="field-value">{{ detailPart.condition || '全新' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">货期</span>
              <span class="field-value">{{ detailPart.lead_time || '—' }}</span>
            </div>
          </div>
          <div class="detail-field full" v-if="detailPart.short_desc">
            <span class="field-label">简述</span>
            <span class="field-value">{{ detailPart.short_desc }}</span>
          </div>
        </div>

        <!-- Specs -->
        <div class="detail-section">
          <h4>规格参数</h4>
          <div v-if="detailPart.specs && detailPart.specs.length" class="specs-table">
            <div v-for="spec in detailPart.specs" :key="spec.id" class="spec-row">
              <span class="spec-key">{{ spec.spec_key }}</span>
              <span class="spec-val">{{ spec.spec_value || '—' }}</span>
            </div>
          </div>
          <span v-else class="no-data">暂无规格参数</span>
        </div>

        <!-- Price History -->
        <div class="detail-section">
          <div class="section-header">
            <h4>价格历史</h4>
            <a-button type="link" size="small" @click="openAddPriceModal">+ 新增报价</a-button>
          </div>
          <!-- Chart -->
          <div class="chart-container" v-if="detailPart.price_history && detailPart.price_history.length > 1">
            <VChart :option="chartOption" :init-options="{ renderer: 'canvas' }" :autoresize="true" style="width: 100%; height: 280px;" />
          </div>
          <!-- List -->
          <div v-if="detailPart.price_history && detailPart.price_history.length" class="price-list">
            <div v-for="h in detailPart.price_history" :key="h.id" class="price-item">
              <span class="price-date">{{ h.price_date || '—' }}</span>
              <span class="price-amount">{{ currencySymbol(h.currency) }} {{ formatPrice(h.price) }}</span>
              <span class="price-note">{{ h.note || '—' }}</span>
              <span class="price-actions">
                <a-button type="text" size="small" @click="openEditPriceModal(h)"><EditOutlined /></a-button>
                <a-popconfirm title="确定删除该价格记录？" @confirm="deletePrice(h.id)">
                  <a-button type="text" size="small" danger><DeleteOutlined /></a-button>
                </a-popconfirm>
              </span>
            </div>
          </div>
          <span v-else class="no-data">暂无价格记录</span>
        </div>

        <!-- Compat Servers -->
        <div class="detail-section">
          <h4>兼容机型</h4>
          <div v-if="detailPart.compat_servers && detailPart.compat_servers.length" class="compat-tags">
            <a-tag
              v-for="c in detailPart.compat_servers"
              :key="c.id"
              class="compat-tag"
              @click="copyText(c.server_model)"
            >{{ c.server_model }}</a-tag>
          </div>
          <span v-else class="no-data">暂无兼容机型</span>
        </div>

        <!-- Actions -->
        <div class="detail-actions">
          <a-button @click="openEditPartModal(detailPart)">编辑配件</a-button>
          <a-popconfirm title="确定删除该配件？" @confirm="deletePart(detailPart.id)">
            <a-button danger>删除</a-button>
          </a-popconfirm>
        </div>
      </template>
      <div v-else class="loading-state">
        <a-spin tip="加载详情..." />
      </div>
    </a-drawer>

    <!-- =================== Create/Edit Part Modal =================== -->
    <a-modal
      v-model:open="partModalVisible"
      :title="partForm.id ? '编辑配件' : '新增配件'"
      @ok="savePart"
      :confirmLoading="partSaving"
      width="600px"
    >
      <div class="edit-form">
        <div class="form-row">
          <label>配件名称 <span class="required">*</span></label>
          <a-input v-model:value="partForm.name" placeholder="如: NVIDIA RTX4090 24G 涡轮卡" />
        </div>
        <div class="form-row-2col">
          <div class="form-row">
            <label>分类</label>
            <a-select v-model:value="partForm.category_id" placeholder="选择分类" allowClear>
              <a-select-option v-for="cat in categories" :key="cat.id" :value="cat.id">
                {{ cat.name }}
              </a-select-option>
            </a-select>
          </div>
          <div class="form-row">
            <label>品牌</label>
            <a-input v-model:value="partForm.brand" placeholder="如: NVIDIA" />
          </div>
        </div>
        <div class="form-row-2col">
          <div class="form-row">
            <label>OEM SKU (原厂料号)</label>
            <a-input v-model:value="partForm.oem_sku" placeholder="如: PG506-230" />
          </div>
          <div class="form-row">
            <label>替代料号</label>
            <a-input v-model:value="partForm.alt_sku" placeholder="兼容备件号" />
          </div>
        </div>
        <div class="form-row">
          <label>简述</label>
          <a-input v-model:value="partForm.short_desc" placeholder="一句话规格摘要" />
        </div>
        <div class="form-row-2col">
          <div class="form-row">
            <label>成色</label>
            <a-select v-model:value="partForm.condition">
              <a-select-option value="全新">全新</a-select-option>
              <a-select-option value="翻新">翻新</a-select-option>
              <a-select-option value="拆机">拆机</a-select-option>
            </a-select>
          </div>
          <div class="form-row">
            <label>货期</label>
            <a-input v-model:value="partForm.lead_time" placeholder="如: 2-4周" />
          </div>
        </div>
        <div class="form-row">
          <label>规格参数</label>
          <div class="specs-editor">
            <div v-for="(spec, idx) in partForm.specs" :key="idx" class="spec-editor-row">
              <a-auto-complete
                v-model:value="spec.key"
                :options="specKeyOptions"
                :filter-option="filterSpecKey"
                placeholder="参数名"
                style="width: 40%"
                allow-clear
              />
              <a-input v-model:value="spec.value" placeholder="参数值" style="width: 45%" />
              <a-button type="text" size="small" danger @click="removeSpec(Number(idx))">✕</a-button>
            </div>
            <a-button type="dashed" size="small" block @click="addSpec">+ 添加参数</a-button>
          </div>
        </div>
        <div class="form-row">
          <label>适用系列（不选=全系列通用）</label>
          <a-select v-model:value="partForm.applicable_series" mode="multiple" placeholder="不选=全通用" allowClear>
            <a-select-option value="Orion">Orion</a-select-option>
            <a-select-option value="Polaris">Polaris</a-select-option>
          </a-select>
        </div>
        <div class="form-row">
          <label>兼容机型（输入后按回车添加）</label>
          <a-select
            v-model:value="partForm.compat_servers"
            mode="tags"
            placeholder="输入机型后按回车，如: DL380 Gen11"
            style="width: 100%"
            :token-separators="[',']"
          />
        </div>
      </div>
    </a-modal>

    <!-- =================== 批量导入 Modal =================== -->
    <a-modal
      v-model:open="importModalVisible"
      title="批量导入配件"
      width="860px"
      :footer="null"
      @cancel="resetImport"
    >
      <div class="import-modal">
        <div v-if="!importPreview.length" class="import-step1">
          <a-upload
            :before-upload="onImportFileSelect"
            :max-count="1"
            accept=".xlsx,.xls"
            :file-list="[]"
          >
            <a-button>
              <template #icon><InboxOutlined /></template>
              选择 Excel 文件
            </a-button>
          </a-upload>
          <span v-if="importFile" class="import-filename">{{ importFile.name }}</span>

          <div class="import-actions">
            <a-button type="link" @click="downloadTemplate">下载导入模板</a-button>
            <a-button type="primary" :loading="importParsing" :disabled="!importFile" @click="previewImport">
              解析预览
            </a-button>
          </div>
          <p class="import-tip">先下载模板按格式填写;导入前会展示逐行预览(新增 / 更新 / 冲突),确认后才真正写入。冲突行会自动跳过。</p>
        </div>

        <div v-else class="import-step2">
          <div class="import-summary">
            <a-tag color="green">新增 {{ importSummary.new || 0 }}</a-tag>
            <a-tag color="blue">更新 {{ importSummary.update || 0 }}</a-tag>
            <a-tag color="red">冲突 {{ importSummary.conflict || 0 }}</a-tag>
            <a-tag v-if="importSummary.invalid" color="default">无效 {{ importSummary.invalid }}</a-tag>
            <span class="import-total">共 {{ importSummary.total }} 行</span>
          </div>
          <a-table
            :data-source="importPreview"
            :columns="importPreviewColumns"
            :pagination="{ pageSize: 50 }"
            size="small"
            :scroll="{ y: 340 }"
            row-key="_row_index"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'action'">
                <a-tag :color="actionColor(record.action)">{{ actionLabel(record.action) }}</a-tag>
              </template>
            </template>
          </a-table>
          <div class="import-actions">
            <a-button @click="resetImport">重新选择</a-button>
            <a-button
              type="primary"
              :loading="importCommitting"
              :disabled="!((importSummary.new || 0) + (importSummary.update || 0))"
              @click="confirmImport"
            >确认导入</a-button>
          </div>
        </div>
      </div>
    </a-modal>

    <!-- =================== Add/Edit Price Modal =================== -->
    <a-modal
      v-model:open="priceModalVisible"
      :title="priceForm.id ? '编辑报价' : '新增报价'"
      @ok="savePrice"
      :confirmLoading="priceSaving"
      width="400px"
    >
      <div class="edit-form">
        <div class="form-row">
          <label>价格 <span class="required">*</span></label>
          <div style="display: flex; gap: 8px;">
            <a-input-number v-model:value="priceForm.price" :min="0" :step="0.01" style="flex: 1" />
            <a-select v-model:value="priceForm.currency" style="width: 96px">
              <a-select-option value="RMB">¥ RMB</a-select-option>
              <a-select-option value="USD">$ USD</a-select-option>
              <a-select-option value="EUR">€ EUR</a-select-option>
            </a-select>
          </div>
        </div>
        <div class="form-row">
          <label>日期</label>
          <a-date-picker
            v-model:value="priceForm.price_date"
            value-format="YYYY-MM-DD"
            placeholder="留空为今天"
            style="width: 100%"
          />
        </div>
        <div class="form-row">
          <label>备注</label>
          <a-textarea v-model:value="priceForm.note" :rows="2" placeholder="供应商、来源等" />
        </div>
      </div>
    </a-modal>

    <!-- =================== Category Manage Modal =================== -->
    <a-modal
      v-model:open="categoryManageVisible"
      title="分类管理"
      :footer="null"
      width="500px"
    >
      <div class="category-manage">
        <div v-for="cat in categories" :key="cat.id" class="category-manage-item">
          <template v-if="editingCategory?.id === cat.id">
            <a-input v-model:value="editingCategoryName" placeholder="分类名称" style="width: 200px" @pressEnter="saveCategoryEdit" />
            <div class="category-edit-actions">
              <a-button type="primary" size="small" @click="saveCategoryEdit">保存</a-button>
              <a-button size="small" @click="cancelCategoryEdit">取消</a-button>
            </div>
          </template>
          <template v-else>
            <span>{{ cat.name }} ({{ cat.count }})</span>
            <div>
              <a-button type="link" size="small" @click="editCategory(cat)">编辑</a-button>
              <a-popconfirm
                v-if="!cat.count"
                title="确定删除该分类？"
                @confirm="deleteCategory(cat.id)"
              >
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
              <a-button
                v-else
                type="link"
                size="small"
                danger
                disabled
                :title="`分类下还有 ${cat.count} 个配件，需先清空才能删除`"
              >删除</a-button>
            </div>
          </template>
        </div>
        <a-divider />
        <div class="category-add-row">
          <a-input v-model:value="newCategoryName" placeholder="新分类名称" style="width: 200px" />
          <a-button type="primary" size="small" @click="createCategory">添加</a-button>
        </div>
      </div>
    </a-modal>

    <!-- =================== Duplicates Drawer =================== -->
    <a-drawer
      v-model:open="duplicatesDrawerVisible"
      title="疑似重复配件"
      width="720"
      :destroyOnClose="true"
    >
      <template v-if="duplicatesData.groups?.length">
        <div class="dup-tip">仅展示疑似重复（oem_sku/alt_sku 相同或名称高度相似），<b>不做自动合并</b>。请人工核实后编辑或删除冗余配件。</div>
        <div class="dup-summary">
          <a-tag color="orange">共 {{ duplicatesData.total_groups }} 组</a-tag>
          <a-tag>{{ duplicatesData.total_duplicate_parts }} 件配件待核实</a-tag>
        </div>
        <div class="dup-list">
          <div v-for="(g, gi) in duplicatesData.groups" :key="gi" class="dup-group">
            <div class="dup-group-head">
              <a-tag color="orange">{{ g.reason }}</a-tag>
              <span class="dup-sim">相似度 {{ (g.similarity * 100).toFixed(0) }}%</span>
              <span class="dup-count">{{ g.parts.length }} 件</span>
            </div>
            <div class="dup-cards">
              <div v-for="p in g.parts" :key="p.id" class="dup-card" @click="openPartDetail(p.id)">
                <div class="dup-card-name" :title="p.name">{{ p.name }}</div>
                <div class="dup-card-meta">
                  <span v-if="p.brand">{{ p.brand }}</span>
                  <span v-if="p.oem_sku" class="dup-sku">SKU: {{ p.oem_sku }}</span>
                  <span v-if="p.alt_sku" class="dup-sku">alt: {{ p.alt_sku }}</span>
                </div>
                <div class="dup-card-price" v-if="p.latest_price != null">¥{{ formatPrice(p.latest_price) }}</div>
                <div class="dup-card-price no-price" v-else>暂无报价</div>
              </div>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="dup-empty">
        <InboxOutlined class="dup-empty-ico" />
        <span>未检测到重复，库内整洁</span>
      </div>
    </a-drawer>
    <!-- =================== Price Movers Drawer =================== -->
    <a-drawer
      v-model:open="moversDrawerVisible"
      title="价格异动"
      placement="right"
      width="680"
    >
      <div class="movers-head">
        <a-radio-group :value="priceMoversDays" button-style="solid" size="small" @change="(e:any)=>onMoversDaysChange(e.target.value)">
          <a-radio-button :value="7">近 7 天</a-radio-button>
          <a-radio-button :value="30">近 30 天</a-radio-button>
        </a-radio-group>
      </div>
      <div class="movers-grid">
        <div class="movers-col">
          <div class="movers-col-title up">涨幅 TOP</div>
          <div v-if="priceMovers.gainers?.length" class="movers-list">
            <div v-for="g in priceMovers.gainers" :key="g.id" class="movers-row" @click="openPartDetail(g.id)">
              <span class="movers-name" :title="g.name">{{ g.name }}</span>
              <span class="movers-price">¥{{ formatPrice(g.latest_price) }}</span>
              <span class="movers-delta up">↑ {{ g.delta_pct }}%</span>
            </div>
          </div>
          <div v-else class="movers-empty">暂无涨幅数据</div>
        </div>
        <div class="movers-col">
          <div class="movers-col-title down">跌幅 TOP</div>
          <div v-if="priceMovers.losers?.length" class="movers-list">
            <div v-for="g in priceMovers.losers" :key="g.id" class="movers-row" @click="openPartDetail(g.id)">
              <span class="movers-name" :title="g.name">{{ g.name }}</span>
              <span class="movers-price">¥{{ formatPrice(g.latest_price) }}</span>
              <span class="movers-delta down">↓ {{ Math.abs(g.delta_pct) }}%</span>
            </div>
          </div>
          <div v-else class="movers-empty">暂无跌幅数据</div>
        </div>
      </div>
    </a-drawer>

    <!-- =================== Price Matrix Drawer =================== -->
    <a-drawer
      v-model:open="matrixDrawerVisible"
      title="比价矩阵"
      placement="right"
      width="720"
    >
      <div class="matrix-head">
        <a-select
          :value="matrixGroupKey || undefined"
          :options="matrixKeyOptions"
          placeholder="选择分组维度"
          size="small"
          style="width: 220px"
          allow-clear
          @change="onMatrixGroupKeyChange"
        />
        <a-radio-group v-model:value="matrixView" button-style="solid" size="small">
          <a-radio-button value="both">表格+图</a-radio-button>
          <a-radio-button value="table">仅表格</a-radio-button>
          <a-radio-button value="box">仅箱线图</a-radio-button>
        </a-radio-group>
      </div>
      <div v-if="!matrixGroupKey" class="matrix-empty">选择上方维度，按该规格分组查看价格分布</div>
      <div v-else-if="matrixLoading" class="matrix-loading"><a-spin /></div>
      <div v-else-if="!matrixData.groups?.length" class="matrix-empty">该维度下暂无带价配件</div>
      <template v-else>
        <div v-if="matrixView !== 'table'" class="matrix-box-wrap">
          <VChart :option="matrixBoxOption || undefined" :init-options="{ renderer: 'canvas' }" :autoresize="true" class="matrix-box" />
        </div>
        <div v-if="matrixView !== 'box'" class="matrix-table-wrap">
          <a-table
            :columns="matrixColumns"
            :data-source="matrixData.groups"
            :pagination="false"
            size="small"
            row-key="value"
          >
            <template #expandedRowRender="{ record }">
              <div class="matrix-detail">
                <span v-for="p in record.parts" :key="p.id" class="matrix-detail-chip" @click="openPartDetail(p.id)">
                  {{ p.name }} <b>¥{{ formatPrice(p.latest_price) }}</b>
                </span>
              </div>
            </template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'value'"><b>{{ record.value }}</b></template>
              <template v-if="column.key === 'prices'">¥{{ formatPrice(record.min) }} ~ ¥{{ formatPrice(record.max) }}</template>
              <template v-if="column.key === 'median'">¥{{ formatPrice(record.median) }}</template>
              <template v-if="column.key === 'avg'">¥{{ formatPrice(record.avg) }}</template>
            </template>
          </a-table>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import {
  AppstoreOutlined, UnorderedListOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  SearchOutlined, InboxOutlined, SettingOutlined, DatabaseOutlined,
  UploadOutlined, DownloadOutlined, BarChartOutlined, StockOutlined
} from '@ant-design/icons-vue'
import axios from 'axios'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, BoxplotChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartTheme } from '@/composables/useChartTheme'

use([GridComponent, TooltipComponent, DataZoomComponent, LineChart, BoxplotChart, CanvasRenderer])

const C = useChartTheme().chartColors

// =================== Dashboard 总览 ===================
const stats = ref<any>({})
const listAllMode = ref(false)
const loadStats = async () => {
  try {
    const res = await axios.get('/api/admin/kp/stats')
    stats.value = res.data || {}
  } catch { /* 静默失败：仪表盘异常不影响列表 */ }
}
const delta = computed(() => (stats.value.this_week_new || 0) - (stats.value.last_week_new || 0))
const deltaClass = computed(() => delta.value > 0 ? 'up' : (delta.value < 0 ? 'down' : 'flat'))
const sparkOption = computed(() => {
  const series = stats.value.new_series
  if (!series || !series.length) return null
  const colors = C.value
  return {
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', show: false, boundaryGap: false, data: series.map((s: any) => s.date) },
    yAxis: { type: 'value', show: false, scale: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      textStyle: { color: colors.tooltipText },
      formatter: (p: any) => `${p[0].axisValue}<br/>新增 ${p[0].value} 件`,
    },
    series: [{
      type: 'line',
      data: series.map((s: any) => s.count),
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: colors.accent },
      areaStyle: { color: colors.accentFill },
    }],
  }
})
const formatDate = (iso: string | null) => (iso ? String(iso).slice(0, 10) : '—')

// =================== 数据洞察：价格异动 / 疑似重复 / 比价矩阵 ===================
// 价格异动看板
const priceMovers = ref<{ days: number; gainers: any[]; losers: any[] }>({ days: 7, gainers: [], losers: [] })
const priceMoversDays = ref(7)
const loadPriceMovers = async () => {
  try {
    const res = await axios.get('/api/admin/kp/price-movers', { params: { days: priceMoversDays.value, limit: 8 } })
    priceMovers.value = res.data || { days: priceMoversDays.value, gainers: [], losers: [] }
  } catch { /* 静默 */ }
}
const onMoversDaysChange = (d: number) => {
  priceMoversDays.value = d
  loadPriceMovers()
}
const moversDrawerVisible = ref(false)
const openMoversDrawer = () => {
  moversDrawerVisible.value = true
  if (!priceMovers.value.gainers?.length && !priceMovers.value.losers?.length) {
    loadPriceMovers()
  }
}

// 疑似重复检测
const duplicatesData = ref<{ total_groups: number; total_duplicate_parts: number; groups: any[] }>({ total_groups: 0, total_duplicate_parts: 0, groups: [] })
const duplicatesDrawerVisible = ref(false)
const loadDuplicates = async () => {
  try {
    const res = await axios.get('/api/admin/kp/parts/duplicates')
    duplicatesData.value = res.data || { total_groups: 0, total_duplicate_parts: 0, groups: [] }
  } catch { /* 静默 */ }
}
const openDuplicates = () => { duplicatesDrawerVisible.value = true }

// 同类比价矩阵
const matrixData = ref<{ group_key: string; groups: any[] }>({ group_key: '', groups: [] })
const matrixGroupKey = ref<string>('')
const matrixView = ref<'both' | 'table' | 'box'>('both')
const matrixLoading = ref(false)
const matrixDrawerVisible = ref(false)
const openMatrixDrawer = () => { matrixDrawerVisible.value = true }
// 矩阵分组维度候选：取当前分类下 value 种类数 >=2 的 spec_key（按种类数降序）
const matrixKeyOptions = computed(() => Object.entries(specFacets.value)
  .map(([k, vs]: [string, any]) => ({ key: k, n: (vs || []).length }))
  .filter(x => x.n >= 2)
  .sort((a, b) => b.n - a.n)
  .map(x => ({ label: `${x.key} · ${x.n} 种`, value: x.key })))
const loadPriceMatrix = async () => {
  if (!selectedCategoryId.value || !matrixGroupKey.value) {
    matrixData.value = { group_key: matrixGroupKey.value, groups: [] }
    return
  }
  matrixLoading.value = true
  try {
    const res = await axios.get('/api/admin/kp/price-matrix', {
      params: { category_id: selectedCategoryId.value, group_key: matrixGroupKey.value },
    })
    matrixData.value = res.data || { group_key: matrixGroupKey.value, groups: [] }
  } catch {
    matrixData.value = { group_key: matrixGroupKey.value, groups: [] }
  } finally {
    matrixLoading.value = false
  }
}
const onMatrixGroupKeyChange = (k: any) => {
  matrixGroupKey.value = (k as string) || ''
  loadPriceMatrix()
}
const matrixBoxOption = computed(() => {
  const groups = matrixData.value.groups || []
  if (!groups.length) return null
  const colors = C.value
  return {
    grid: { left: 88, right: 28, top: 16, bottom: 32 },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: { color: colors.tick, fontSize: 10 },
      splitLine: { lineStyle: { color: colors.splitLine } },
    },
    yAxis: {
      type: 'category',
      data: groups.map((g: any) => g.value),
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: { color: colors.tick, fontSize: 11 },
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      textStyle: { color: colors.tooltipText },
      formatter: (p: any) => {
        const g: any = groups[p.dataIndex]
        if (!g) return ''
        return `<b>${g.value}</b> · ${g.count} 件<br/>最低 ¥${formatPrice(g.min)}<br/>Q1 ¥${formatPrice(g.q1)}<br/>中位 ¥${formatPrice(g.median)}<br/>Q3 ¥${formatPrice(g.q3)}<br/>最高 ¥${formatPrice(g.max)}`
      },
    },
    series: [{
      type: 'boxplot',
      data: groups.map((g: any) => [g.min, g.q1, g.median, g.q3, g.max]),
      itemStyle: { color: colors.accentFill, borderColor: colors.accent },
    }],
  }
})
const matrixColumns = [
  { title: '分组', dataIndex: 'value', key: 'value', width: 140 },
  { title: '数量', dataIndex: 'count', key: 'count', width: 70 },
  { title: '价格区间', key: 'prices', width: 220 },
  { title: '中位', dataIndex: 'median', key: 'median', width: 100 },
  { title: '均值', dataIndex: 'avg', key: 'avg', width: 100 },
]

// =================== View Mode ===================
const viewMode = ref<'card' | 'table'>('card')

// =================== Categories ===================
const categories = ref<any[]>([])
const selectedCategoryId = ref<number | null>(null)
const totalPartCount = computed(() => categories.value.reduce((sum, c) => sum + (c.count || 0), 0))

const loadCategories = async () => {
  try {
    const res = await axios.get('/api/admin/kp/categories')
    // 旧接口返回 { category, count }，需要映射到新接口获取 id
    const resAll = await axios.get('/api/admin/kp/categories/all')
    const fullCats = resAll.data.categories || []
    // 合并 count 信息
    categories.value = fullCats.map((fc: any) => {
      const old = res.data.categories.find((c: any) => c.category === fc.name)
      return { ...fc, count: old?.count || 0 }
    })
  } catch (e: any) {
    message.error('加载分类失败: ' + (e.response?.data?.detail || e.message))
  }
}

const selectCategory = (catId: number | null) => {
  selectedCategoryId.value = catId
  listAllMode.value = false
  pagination.value.current = 1
  // 切换分类时重置筛选并重新加载品牌 / 规格维度（随分类变化）
  selectedBrands.value = []
  priceFilter.value = ''
  selectedSpecs.value = {}
  matrixGroupKey.value = ''
  matrixData.value = { group_key: '', groups: [] }
  loadBrands()
  loadSpecFacets()
  loadParts()
}

// =================== Filters ===================
const brandsList = ref<any[]>([])
const specFacets = ref<Record<string, any[]>>({})
const selectedBrands = ref<string[]>([])
const priceFilter = ref('')
const selectedSpecs = ref<Record<string, string[]>>({})

const loadBrands = async () => {
  try {
    const res = await axios.get('/api/admin/kp/brands', { params: { category_id: selectedCategoryId.value } })
    brandsList.value = res.data.brands || []
  } catch (e: any) {
    brandsList.value = []
  }
}

const loadSpecFacets = async () => {
  try {
    const res = await axios.get('/api/admin/kp/spec-facets', { params: { category_id: selectedCategoryId.value } })
    specFacets.value = res.data.facets || {}
  } catch (e: any) {
    specFacets.value = {}
  }
}

const hasSelectedCategory = computed(() => selectedCategoryId.value != null)

// spec_key 录入候选：来自当前类别已聚合的维度名，允许自由输入兜底
const specKeyOptions = computed(() => Object.keys(specFacets.value).map(k => ({ value: k })))
const filterSpecKey = (input: string, option: any) => {
  const v = (option.value || '').toLowerCase()
  return v.includes((input || '').toLowerCase())
}

// 品牌多选下拉 options；规格维度超过 3 个时折叠
const brandOptions = computed(() => brandsList.value.map(b => ({ label: `${b.brand} (${b.count})`, value: b.brand })))
const specExpanded = ref(false)
const specKeys = computed(() => Object.keys(specFacets.value))
const visibleSpecKeys = computed(() => specExpanded.value ? specKeys.value : specKeys.value.slice(0, 3))

const applyFilters = () => {
  pagination.value.current = 1
  loadParts()
}

const toggleSpec = (key: string, value: string) => {
  const cur = selectedSpecs.value[key] ? [...selectedSpecs.value[key]] : []
  const idx = cur.indexOf(value)
  if (idx >= 0) cur.splice(idx, 1)
  else cur.push(value)
  if (cur.length) {
    selectedSpecs.value = { ...selectedSpecs.value, [key]: cur }
  } else {
    const next = { ...selectedSpecs.value }
    delete next[key]
    selectedSpecs.value = next
  }
  applyFilters()
}

// =================== Parts List ===================
const parts = ref<any[]>([])
const partsLoading = ref(false)
const partsTotal = ref(0)
const searchText = ref('')
const sortBy = ref('name-asc')
const pagination = ref({ current: 1, pageSize: 20 })

const loadParts = async () => {
  partsLoading.value = true
  try {
    // sortBy 形如 'name-asc' / 'price-desc'，拆成 sort_by / sort_order 两个字段传后端
    const [sb, so] = sortBy.value.split('-')
    const specsParam = Object.keys(selectedSpecs.value).length ? JSON.stringify(selectedSpecs.value) : null
    const res = await axios.get('/api/admin/kp/parts', {
      params: {
        category_id: selectedCategoryId.value,
        search: searchText.value,
        page: pagination.value.current,
        page_size: pagination.value.pageSize,
        sort_by: sb,
        sort_order: so,
        brands: selectedBrands.value.length ? selectedBrands.value.join(',') : null,
        price_filter: priceFilter.value || null,
        specs: specsParam,
      }
    })
    parts.value = res.data.items || []
    partsTotal.value = res.data.total || 0
  } catch (e: any) {
    message.error('加载配件失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    partsLoading.value = false
  }
}

const handleTableChange = (pag: any) => {
  pagination.value.current = pag.current
  pagination.value.pageSize = pag.pageSize
  loadParts()
}

const onCardPageChange = (page: number, pageSize: number) => {
  pagination.value.current = page
  pagination.value.pageSize = pageSize
  loadParts()
}

// =================== Table Columns ===================
const tablePagination = computed(() => ({
  current: pagination.value.current,
  pageSize: pagination.value.pageSize,
  total: partsTotal.value,
  showSizeChanger: true,
  pageSizeOptions: ['20', '40', '60'],
}))

const tableColumns = [
  { title: '配件名称', dataIndex: 'name', key: 'name', width: 300, ellipsis: true },
  { title: '分类', dataIndex: 'category_name', key: 'category_name', width: 100 },
  { title: 'OEM SKU', dataIndex: 'oem_sku', key: 'oem_sku', width: 150, ellipsis: true },
  { title: '品牌', dataIndex: 'brand', key: 'brand', width: 100 },
  { title: '最新价格', dataIndex: 'latest_price', key: 'latest_price', width: 120 },
  { title: '更新日期', dataIndex: 'latest_date', key: 'latest_date', width: 100 },
  { title: '操作', key: 'action', width: 120, fixed: 'right' as const },
]

// =================== Part Detail Drawer ===================
const detailDrawerVisible = ref(false)
const detailPart = ref<any>(null)

const openPartDetail = async (partId: number) => {
  detailDrawerVisible.value = true
  detailPart.value = null
  try {
    const res = await axios.get(`/api/admin/kp/parts/${partId}`)
    detailPart.value = res.data
  } catch (e: any) {
    message.error('加载详情失败')
    detailDrawerVisible.value = false
  }
}

const chartOption = computed(() => {
  if (!detailPart.value?.price_history || detailPart.value.price_history.length < 2) return undefined
  const sorted = [...detailPart.value.price_history].reverse()
  const colors = C.value
  return {
    grid: { left: 48, right: 24, top: 20, bottom: 32 },
    xAxis: {
      type: 'category',
      data: sorted.map(h => h.price_date),
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: { color: colors.tick, fontSize: 10 },
      splitLine: { lineStyle: { color: colors.splitLine } },
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: { color: colors.tick },
      splitLine: { lineStyle: { color: colors.splitLine } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      textStyle: { color: colors.tooltipText },
      formatter: (p: any) => {
        const d = p[0]
        return `${d.axisValue}<br/>¥ ${d.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      },
    },
    dataZoom: [{ type: 'inside' }],
    series: [{
      type: 'line',
      name: '价格趋势',
      data: sorted.map(h => h.price),
      smooth: 0.3,
      symbolSize: 6,
      itemStyle: { color: colors.accent },
      lineStyle: { width: 2 },
      areaStyle: { color: colors.accentFill },
    }],
  }
})

// =================== Part Create/Edit Modal ===================
const partModalVisible = ref(false)
const partSaving = ref(false)
const partForm = ref<any>({
  id: null, name: '', category_id: null, brand: '', oem_sku: '', alt_sku: '',
  short_desc: '', condition: '全新', lead_time: '',
  specs: [], compat_servers: [], applicable_series: [],
})

const openCreatePartModal = () => {
  partForm.value = {
    id: null, name: '', category_id: selectedCategoryId.value, brand: '', oem_sku: '', alt_sku: '',
    short_desc: '', condition: '全新', lead_time: '',
    specs: [], compat_servers: [], applicable_series: [],
  }
  partModalVisible.value = true
}

const openEditPartModal = (part: any) => {
  partForm.value = {
    id: part.id,
    name: part.name,
    category_id: part.category_id,
    brand: part.brand || '',
    oem_sku: part.oem_sku || '',
    alt_sku: part.alt_sku || '',
    short_desc: part.short_desc || '',
    condition: part.condition || '全新',
    lead_time: part.lead_time || '',
    specs: (part.specs || []).map((s: any) => ({ key: s.spec_key, value: s.spec_value || '' })),
    compat_servers: (part.compat_servers || []).map((c: any) => c.server_model),
    applicable_series: part.applicable?.series || [],
  }
  partModalVisible.value = true
}

const addSpec = () => {
  partForm.value.specs.push({ key: '', value: '' })
}

const removeSpec = (idx: number) => {
  partForm.value.specs.splice(idx, 1)
}

// =================== 批量导入 / 导出 ===================
const importModalVisible = ref(false)
const importFile = ref<File | null>(null)
const importPreview = ref<any[]>([])
const importSummary = ref<any>({})
const importParsing = ref(false)
const importCommitting = ref(false)

const importPreviewColumns = [
  { title: '行', dataIndex: '_row_index', width: 60 },
  { title: '操作', key: 'action', width: 90 },
  { title: '料号', dataIndex: 'oem_sku', width: 140 },
  { title: '名称', dataIndex: 'name', ellipsis: true },
  { title: '分类', dataIndex: 'category_name', width: 120 },
  { title: '消息', dataIndex: 'message', ellipsis: true },
]

const actionLabel = (a: string) => ({ new: '新增', update: '更新', conflict: '冲突', invalid: '无效' } as any)[a] || a
const actionColor = (a: string) => ({ new: 'green', update: 'blue', conflict: 'red', invalid: 'default' } as any)[a] || 'default'

const triggerDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const onImportFileSelect = (file: File) => {
  importFile.value = file
  importPreview.value = []
  importSummary.value = {}
  return false
}

const resetImport = () => {
  importFile.value = null
  importPreview.value = []
  importSummary.value = {}
}

const downloadTemplate = async () => {
  try {
    const res = await axios.get('/api/admin/kp/parts/import-template', { responseType: 'blob' })
    triggerDownload(res.data, 'kp_parts_import_template.xlsx')
  } catch (e: any) {
    message.error('模板下载失败: ' + (e.response?.data?.detail || e.message))
  }
}

const exportParts = async () => {
  try {
    const params = selectedCategoryId.value ? { category_id: selectedCategoryId.value } : {}
    const res = await axios.get('/api/admin/kp/parts/export', { responseType: 'blob', params })
    triggerDownload(res.data, 'kp_parts.xlsx')
    message.success('已导出')
  } catch (e: any) {
    message.error('导出失败: ' + (e.response?.data?.detail || e.message))
  }
}

const previewImport = async () => {
  if (!importFile.value) {
    message.warning('请先选择文件')
    return
  }
  importParsing.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const res = await axios.post('/api/admin/kp/parts/import?dry_run=true', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importPreview.value = res.data.preview || []
    importSummary.value = res.data.summary || {}
    if (!importPreview.value.length) message.info('未解析到任何数据行')
  } catch (e: any) {
    message.error('解析失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    importParsing.value = false
  }
}

const confirmImport = async () => {
  importCommitting.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value!)
    const res = await axios.post('/api/admin/kp/parts/import?dry_run=false', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const s = res.data.summary || {}
    message.success(`导入完成:新增 ${s.created} · 更新 ${s.updated} · 跳过 ${s.skipped}${s.failed ? ` · 失败 ${s.failed}` : ''}`)
    importModalVisible.value = false
    resetImport()
    loadParts()
    loadCategories()
    loadStats()
  } catch (e: any) {
    message.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    importCommitting.value = false
  }
}

const savePart = async () => {
  if (!partForm.value.name) {
    message.error('配件名称不能为空')
    return
  }
  partSaving.value = true
  try {
    const payload = {
      ...partForm.value,
      specs: partForm.value.specs.filter((s: any) => s.key),
      compat_servers: partForm.value.compat_servers || [],
      applicable: partForm.value.applicable_series && partForm.value.applicable_series.length
        ? { series: partForm.value.applicable_series } : null,
    }

    if (partForm.value.id) {
      await axios.put(`/api/admin/kp/parts/${partForm.value.id}`, payload)
      message.success('更新成功')
    } else {
      await axios.post('/api/admin/kp/parts', payload)
      message.success('创建成功')
    }
    partModalVisible.value = false
    loadParts()
    loadCategories()
    loadStats()
    // 如果详情打开，刷新详情
    if (detailDrawerVisible.value && partForm.value.id) {
      openPartDetail(partForm.value.id)
    }
  } catch (e: any) {
    message.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    partSaving.value = false
  }
}

const deletePart = async (partId: number) => {
  try {
    await axios.delete(`/api/admin/kp/parts/${partId}`)
    message.success('删除成功')
    detailDrawerVisible.value = false
    loadParts()
    loadCategories()
    loadStats()
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// =================== Add/Edit Price ===================
const priceModalVisible = ref(false)
const priceSaving = ref(false)
const priceForm = ref<any>({ id: null, price: 0, currency: 'RMB', price_date: null, note: '' })

const openAddPriceModal = () => {
  priceForm.value = { id: null, price: 0, currency: detailPart.value?.latest_currency || 'RMB', price_date: null, note: '' }
  priceModalVisible.value = true
}

const openEditPriceModal = (h: any) => {
  priceForm.value = { id: h.id, price: h.price, currency: h.currency || 'RMB', price_date: h.price_date, note: h.note || '' }
  priceModalVisible.value = true
}

const savePrice = async () => {
  if (!priceForm.value.price) {
    message.error('价格不能为空')
    return
  }
  priceSaving.value = true
  try {
    if (priceForm.value.id) {
      await axios.put(`/api/admin/kp/prices/${priceForm.value.id}`, priceForm.value)
      message.success('报价更新成功')
    } else {
      await axios.post(`/api/admin/kp/parts/${detailPart.value.id}/prices`, priceForm.value)
      message.success('报价添加成功')
    }
    priceModalVisible.value = false
    openPartDetail(detailPart.value.id)
    loadParts()
    loadStats()
  } catch (e: any) {
    message.error((priceForm.value.id ? '更新' : '添加') + '失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    priceSaving.value = false
  }
}

const deletePrice = async (priceId: number) => {
  try {
    await axios.delete(`/api/admin/kp/prices/${priceId}`)
    message.success('已删除')
    openPartDetail(detailPart.value.id)
    loadParts()
    loadStats()
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// =================== Category Manage ===================
const categoryManageVisible = ref(false)
const newCategoryName = ref('')

const createCategory = async () => {
  if (!newCategoryName.value) return
  try {
    await axios.post('/api/admin/kp/categories', { name: newCategoryName.value })
    newCategoryName.value = ''
    loadCategories()
    message.success('分类创建成功')
  } catch (e: any) {
    message.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
}

const editingCategory = ref<any>(null)
const editingCategoryName = ref('')

const editCategory = (cat: any) => {
  editingCategory.value = cat
  editingCategoryName.value = cat.name
}

const cancelCategoryEdit = () => {
  editingCategory.value = null
  editingCategoryName.value = ''
}

const saveCategoryEdit = async () => {
  const newName = editingCategoryName.value.trim()
  if (!newName) {
    message.error('分类名称不能为空')
    return
  }
  if (newName === editingCategory.value.name) {
    cancelCategoryEdit()
    return
  }
  try {
    await axios.put(`/api/admin/kp/categories/${editingCategory.value.id}`, { name: newName })
    message.success('更新成功')
    cancelCategoryEdit()
    loadCategories()
  } catch (e: any) {
    message.error('更新失败: ' + (e.response?.data?.detail || e.message))
  }
}

const deleteCategory = async (catId: number) => {
  try {
    await axios.delete(`/api/admin/kp/categories/${catId}`)
    loadCategories()
    message.success('删除成功')
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// =================== Utils ===================
const CURRENCY_SYMBOLS: Record<string, string> = { RMB: '¥', CNY: '¥', USD: '$', EUR: '€' }
const currencySymbol = (currency: string | null | undefined) => {
  if (!currency) return '¥'
  return CURRENCY_SYMBOLS[currency.toUpperCase()] || currency
}
const formatPrice = (val: any) => {
  if (val == null) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const copyText = (text: string) => {
  if (!text) return
  navigator.clipboard.writeText(text).then(() => message.success('已复制'))
}

const conditionClass = (cond: string) => {
  if (cond === '翻新') return 'cpq-led--warning'
  if (cond === '拆机') return 'cpq-led--muted'
  return 'cpq-led--active'
}

const clearSearch = () => {
  searchText.value = ''
  pagination.value.current = 1
  loadParts()
}

// =================== Init ===================
onMounted(() => {
  loadCategories()
  loadBrands()
  loadSpecFacets()
  loadParts()
  loadStats()
  loadDuplicates()
})
</script>

<style scoped>
/* ============ 批量导入 Modal ============ */
.import-modal .import-step1 {
  display: flex; flex-direction: column; gap: 12px; align-items: flex-start;
}
.import-modal .import-filename { color: #888; font-size: 13px; }
.import-modal .import-actions { display: flex; gap: 8px; align-items: center; }
.import-modal .import-tip { color: #999; font-size: 12px; margin: 4px 0 0; line-height: 1.6; }
.import-modal .import-summary { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.import-modal .import-total { color: #888; font-size: 12px; margin-left: 4px; }
.import-modal .import-step2 .import-actions { justify-content: flex-end; margin-top: 12px; }

/* ============ 页面骨架 ============ */
.parts-page {
  position: relative;
  padding: 24px;
  background: var(--cpq-bg-gradient);
  min-height: 100vh;
  color: var(--cpq-text-primary);
}
/* 顶部签名光条 */
.parts-page::before {
  content: '';
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 2px;
  z-index: 100;
  background: linear-gradient(90deg, transparent, var(--cpq-accent-primary), transparent);
}

/* 入场动画 */
@keyframes fadeInUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }

/* ============ 页头 ============ */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 22px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
}
.page-title-group h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.3px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.page-title-icon { color: var(--cpq-accent-primary); font-size: 20px; }
.page-subtitle { margin: 4px 0 0; font-size: 13px; color: var(--cpq-text-secondary); }
.page-subtitle .num { color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.header-actions { display: flex; gap: 10px; align-items: center; }

/* 分段视图切换 */
.seg-nav {
  display: flex; gap: 4px; padding: 4px; border-radius: 10px;
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
}
.seg-item {
  display: flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 7px;
  font-size: 13px; color: var(--cpq-text-secondary); cursor: pointer;
  transition: all var(--cpq-transition-fast); border: none; background: transparent;
  font-family: inherit;
}
.seg-item:hover { color: var(--cpq-text-primary); background: var(--cpq-overlay-a6); }
.seg-item.active { color: var(--cpq-accent-on-primary); background: var(--cpq-accent-primary); font-weight: 600; }
.seg-item :deep(svg) { width: 15px; height: 15px; }

/* ============ 顶部分类胶囊条 ============ */
.category-nav-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 12px; margin-bottom: 18px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; animation-delay: 0.08s;
}
.cat-chip-scroll {
  flex: 1; display: flex; flex-wrap: wrap; gap: 6px; padding: 2px 0;
}
.cat-chip {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 14px; border-radius: 999px; white-space: nowrap;
  font-size: 13px; color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
  cursor: pointer; font-family: inherit;
  transition: all var(--cpq-transition-fast);
}
.cat-chip:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); background: var(--cpq-overlay-a6); }
.cat-chip.active { color: var(--cpq-accent-on-primary); background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); font-weight: 600; }
.cat-chip.active .cat-chip-count { background: var(--cpq-overlay-w15); color: var(--cpq-accent-on-primary); }
.cat-chip-ico { width: 14px; height: 14px; opacity: 0.85; }
.cat-chip-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cpq-text-muted); opacity: 0.6; }
.cat-chip.active .cat-chip-dot { background: var(--cpq-accent-on-primary); opacity: 1; }
.cat-chip-count {
  font-size: 11px; padding: 0 7px; line-height: 16px; border-radius: 10px;
  background: var(--cpq-overlay-w6); color: var(--cpq-text-muted);
  font-variant-numeric: tabular-nums;
}
.cat-manage-btn {
  flex-shrink: 0; display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 9px;
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary); cursor: pointer; font-family: inherit;
  transition: all var(--cpq-transition-fast);
}
.cat-manage-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }
.cat-manage-btn :deep(svg) { width: 15px; height: 15px; }

/* sidebar 规格折叠提示 */
.filter-hint {
  font-size: 12px; color: var(--cpq-text-muted); line-height: 1.6;
  padding: 12px 10px; border: 1px dashed var(--cpq-border-primary); border-radius: 8px; text-align: center;
}

/* ============ 主体布局 ============ */
.main-layout { display: flex; gap: 20px; align-items: flex-start; }

/* ============ 分类栏 ============ */
.category-sidebar {
  width: 220px;
  flex-shrink: 0;
  padding: 16px 12px;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  position: sticky;
  top: 24px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
  animation-delay: 0.05s;
}
.sidebar-title {
  font-size: 11px; font-weight: 600; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: 0.8px; padding: 0 8px 10px;
}
.sidebar-item {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 12px; border-radius: 9px; cursor: pointer; font-size: 13px;
  color: var(--cpq-text-secondary);
  transition: all var(--cpq-transition-fast);
  position: relative; margin-bottom: 2px;
}
.sidebar-ico { width: 15px; height: 15px; opacity: 0.8; }
.sidebar-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cpq-text-muted); opacity: 0.5; flex-shrink: 0; }
.sidebar-item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sidebar-item:hover { background: var(--cpq-overlay-a6); color: var(--cpq-text-primary); }
.sidebar-item.active {
  background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); font-weight: 500;
  box-shadow: inset 3px 0 0 var(--cpq-accent-primary);
}
.sidebar-item.active .sidebar-dot { background: var(--cpq-accent-primary); opacity: 1; }
.sidebar-item-count {
  font-size: 11px; color: var(--cpq-text-muted); background: var(--cpq-overlay-w6);
  padding: 1px 8px; border-radius: 10px; min-width: 26px; text-align: center;
  font-variant-numeric: tabular-nums;
}
.sidebar-item.active .sidebar-item-count { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary); }
.sidebar-footer { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--cpq-border-primary); }
.sidebar-manage-btn {
  display: flex; align-items: center; gap: 6px; width: 100%; padding: 7px 10px; border-radius: 8px;
  background: transparent; border: none; color: var(--cpq-text-secondary); font-size: 12px;
  cursor: pointer; font-family: inherit; transition: all var(--cpq-transition-fast);
}
.sidebar-manage-btn:hover { background: var(--cpq-overlay-a6); color: var(--cpq-accent-primary); }
.sidebar-manage-btn :deep(svg) { width: 14px; height: 14px; }

/* 筛选区 */
.filter-divider { height: 1px; background: var(--cpq-border-primary); margin: 14px 6px; }
.filter-group { padding: 0 6px; margin-bottom: 16px; }
.filter-title {
  font-size: 11px; font-weight: 600; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px;
}
.filter-opt {
  display: flex; align-items: center; gap: 9px; padding: 5px 8px; border-radius: 7px;
  font-size: 12.5px; color: var(--cpq-text-secondary); cursor: pointer;
  transition: all var(--cpq-transition-fast);
}
.filter-opt:hover { background: var(--cpq-overlay-a6); color: var(--cpq-text-primary); }
.filter-opt input { accent-color: var(--cpq-accent-primary); width: 14px; height: 14px; cursor: pointer; }
.filter-opt .opt-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.filter-opt .opt-count { font-size: 11px; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 6px 4px; }
.chip {
  font-size: 11.5px; padding: 3px 10px; border-radius: 10px;
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary); cursor: pointer;
  transition: all var(--cpq-transition-fast); user-select: none;
}
.chip:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }
.chip.active { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border-color: var(--cpq-overlay-a20); }
.chip-count { font-size: 10px; opacity: 0.7; margin-left: 3px; }
.clear-filter {
  width: calc(100% - 12px); margin: 2px 6px; padding: 8px; border-radius: 8px;
  background: transparent; border: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary); font-size: 12px; cursor: pointer;
  font-family: inherit; transition: all var(--cpq-transition-fast);
}
.clear-filter:hover { color: var(--cpq-accent-danger); border-color: var(--cpq-accent-danger); }

/* ============ 内容区 ============ */
.content-area { flex: 1; min-width: 0; }

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; gap: 14px; padding: 12px 16px;
  border-radius: 14px; margin-bottom: 18px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; animation-delay: 0.1s;
}
.toolbar-search { width: 320px; }
.toolbar-sort { width: 160px; }
.toolbar-count { margin-left: auto; font-size: 13px; color: var(--cpq-text-muted); }
.toolbar-count b { color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }

.card-pagination { margin-top: 18px; display: flex; justify-content: flex-end; }

/* ============ 仪表盘 ============ */
.stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 18px; animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; }
.stat-card { padding: 18px 20px; border-radius: 0; display: flex; flex-direction: column; gap: 6px; }
.stat-card.clickable { cursor: pointer; transition: transform var(--cpq-transition-fast), box-shadow var(--cpq-transition-fast); }
.stat-card.clickable:hover { transform: translateY(-2px); box-shadow: 0 10px 28px var(--cpq-shadow-color-strong); }
.stat-unit { font-size: 14px; font-weight: 500; color: var(--cpq-text-secondary); margin-left: 4px; }
.stat-label { font-size: 12px; color: var(--cpq-text-secondary); letter-spacing: 0.2px; }
.stat-value { font-size: 30px; font-weight: 700; color: var(--cpq-text-primary); line-height: 1.1; font-variant-numeric: tabular-nums; }
.stat-foot { font-size: 12px; min-height: 16px; }
.stat-delta.up { color: var(--cpq-accent-success, #3fbb6c); font-weight: 600; }
.stat-delta.down { color: var(--cpq-accent-danger); font-weight: 600; }
.stat-delta.flat { color: var(--cpq-text-muted); }
.stat-sub { color: var(--cpq-text-muted); }
.stat-spark { width: 100%; height: 44px; margin-top: 2px; }
.recent-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; animation-delay: 0.06s; }
.recent-panel { padding: 14px 18px; border-radius: 0; }
.recent-head h4 { margin: 0 0 6px; font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.recent-list { display: flex; flex-direction: column; }
.recent-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 8px 6px; border-radius: 8px; cursor: pointer; transition: background var(--cpq-transition-fast); }
.recent-row + .recent-row { border-top: 1px solid var(--cpq-border-primary); }
.recent-row:hover { background: var(--cpq-overlay-a6); }
.rr-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.rr-name { font-size: 13px; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rr-cat { font-size: 11px; color: var(--cpq-accent-primary); }
.rr-meta { font-size: 11px; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.rr-price { font-size: 13px; color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.recent-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 14px 6px; }
.all-list-link { margin-top: 16px; font-size: 13px; color: var(--cpq-accent-primary); cursor: pointer; display: inline-block; }
.all-list-link:hover { text-decoration: underline; }
.list-mode-banner { margin-bottom: 12px; }
.back-overview { background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary); color: var(--cpq-text-secondary); font-size: 12px; padding: 5px 12px; border-radius: 8px; cursor: pointer; font-family: inherit; transition: all var(--cpq-transition-fast); }
.back-overview:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }

/* ============ 工具栏筛选 ============ */
.toolbar-brand { width: 200px; }
.toolbar-price { flex-shrink: 0; }
.toolbar-price :deep(.ant-radio-button-wrapper) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); color: var(--cpq-text-secondary); }
.toolbar-price :deep(.ant-radio-button-wrapper-checked) { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); }
.spec-bar { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; border-radius: 12px; margin-bottom: 16px; }
.spec-bar-label { font-size: 12px; color: var(--cpq-text-muted); flex-shrink: 0; padding-top: 5px; }
.spec-bar-chips { flex: 1; display: flex; flex-wrap: wrap; gap: 6px; }
.spec-chip { font-size: 12px; padding: 3px 10px; border-radius: 12px; cursor: pointer; color: var(--cpq-text-secondary); background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary); transition: all var(--cpq-transition-fast); user-select: none; }
.spec-chip:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }
.spec-chip.active { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border-color: var(--cpq-overlay-a20); }
.spec-chip-count { font-size: 10px; opacity: 0.7; margin-left: 3px; }
.spec-more { flex-shrink: 0; margin-top: 1px; background: transparent; border: 1px solid var(--cpq-border-primary); border-radius: 8px; color: var(--cpq-text-secondary); font-size: 12px; padding: 3px 10px; cursor: pointer; font-family: inherit; transition: all var(--cpq-transition-fast); }
.spec-more:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }

/* ============ 卡片网格 ============ */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 14px;
}
.model-card {
  position: relative;
  overflow: hidden;
  padding: 16px;
  border-radius: 0;
  cursor: pointer;
  transition: transform 0.25s var(--cpq-ease-out-expo), box-shadow 0.25s var(--cpq-ease-out-expo);
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
}
.model-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 16px 40px var(--cpq-shadow-color-strong), 0 0 26px var(--cpq-overlay-a15), inset 0 1px 0 var(--cpq-overlay-w10);
}
.card-accent-bar {
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--cpq-accent-primary);
  transform: scaleX(0); transform-origin: left center;
  transition: transform 0.3s var(--cpq-ease-out-expo);
}
.model-card:hover .card-accent-bar { transform: scaleX(1); }
.model-card.no-price-card { opacity: 0.58; }

.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-category-tag {
  font-size: 11px; font-weight: 500; color: var(--cpq-accent-primary); letter-spacing: 0.2px;
  padding: 2px 10px; border-radius: 10px;
  background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a20);
}
.card-edit-btn {
  display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 8px;
  background: transparent; border: none; color: var(--cpq-text-muted); cursor: pointer;
  transition: all var(--cpq-transition-fast);
}
.card-edit-btn:hover { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.card-edit-btn :deep(svg) { width: 15px; height: 15px; }
.card-name { font-size: 14.5px; font-weight: 600; line-height: 1.35; margin-bottom: 7px; word-break: break-all; }
.card-sku { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; font-size: 11.5px; }
.sku-label { color: var(--cpq-text-muted); font-weight: 500; }
.sku-value { color: var(--cpq-text-secondary); cursor: pointer; font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.sku-value:hover { color: var(--cpq-accent-primary); text-decoration: underline; }
.card-price { display: flex; align-items: baseline; gap: 9px; margin-bottom: 12px; }
.price-value {
  font-size: 14px; font-weight: 600; color: var(--cpq-text-primary);
  font-variant-numeric: tabular-nums;
}
.price-sym { font-size: 12px; font-weight: 500; color: var(--cpq-text-secondary); }
.price-value.no-price { font-size: 13px; font-weight: 400; color: var(--cpq-text-muted); }
.price-date { font-size: 11px; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.card-meta {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  padding-top: 10px; border-top: 1px solid var(--cpq-border-primary);
}
/* 成色徽章改用全局 .cpq-led */

/* 表格视图 */
.table-wrap { padding: 4px 8px; border-radius: 14px; }
.table-price { color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.no-price { color: var(--cpq-text-muted); }

/* ============ 详情抽屉 ============ */
.detail-section { margin-bottom: 24px; }
.detail-section h4 {
  font-size: 14px; font-weight: 600; color: var(--cpq-text-primary);
  margin: 0 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-border-primary);
}
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-border-primary);
}
.section-header h4 { margin: 0; padding: 0; border: none; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.detail-field { display: flex; flex-direction: column; gap: 2px; }
.detail-field.full { margin-top: 12px; }
.field-label {
  font-size: 11px; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.field-value { font-size: 13px; color: var(--cpq-text-primary); }

.specs-table { border: 1px solid var(--cpq-border-primary); border-radius: 8px; overflow: hidden; }
.spec-row { display: flex; border-bottom: 1px solid var(--cpq-border-primary); }
.spec-row:last-child { border-bottom: none; }
.spec-key { width: 40%; padding: 8px 12px; background: var(--cpq-overlay-w6); font-size: 12px; font-weight: 500; color: var(--cpq-text-secondary); }
.spec-val { flex: 1; padding: 8px 12px; font-size: 13px; color: var(--cpq-text-primary); }

.chart-container { margin-bottom: 16px; padding: 12px; background: var(--cpq-overlay-w6); border-radius: 8px; }
.price-list { display: flex; flex-direction: column; gap: 4px; }
.price-item { display: flex; align-items: center; gap: 16px; padding: 6px 0; font-size: 12px; border-bottom: 1px solid var(--cpq-border-primary); }
.price-item:last-child { border-bottom: none; }
.price-date { color: var(--cpq-text-muted); min-width: 80px; font-variant-numeric: tabular-nums; }
.price-amount { color: var(--cpq-accent-primary); font-weight: 600; min-width: 80px; font-variant-numeric: tabular-nums; }
.price-note { color: var(--cpq-text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.price-actions { display: flex; gap: 2px; opacity: 0; transition: opacity var(--cpq-transition-fast); }
.price-item:hover .price-actions { opacity: 1; }

.compat-tags { display: flex; flex-wrap: wrap; gap: 6px; }
:deep(.compat-tag) { cursor: pointer; transition: all var(--cpq-transition-fast); }
:deep(.compat-tag:hover) { color: var(--cpq-accent-primary) !important; border-color: var(--cpq-accent-primary) !important; }

.drawer-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.drawer-title-name { font-size: 16px; font-weight: 600; color: var(--cpq-text-primary); }

.detail-actions { display: flex; gap: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--cpq-border-primary); }
.no-data { font-size: 12px; color: var(--cpq-text-muted); }

/* ============ 表单 ============ */
.edit-form { display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label { font-size: 13px; color: var(--cpq-text-secondary); font-weight: 500; }
.form-row-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.required { color: var(--cpq-accent-danger); }
.specs-editor { display: flex; flex-direction: column; gap: 6px; }
.spec-editor-row { display: flex; gap: 6px; align-items: center; }
.category-manage-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--cpq-border-primary); }
.category-edit-actions { display: flex; gap: 6px; }
.category-add-row { display: flex; gap: 8px; align-items: center; }

/* ============ 状态 ============ */
.loading-state { display: flex; justify-content: center; align-items: center; padding: 60px 0; color: var(--cpq-text-muted); font-size: 14px; }
.empty-state { display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 12px; padding: 60px 0; color: var(--cpq-text-muted); font-size: 14px; }
.empty-icon { font-size: 36px; line-height: 1; color: var(--cpq-text-muted); }
.empty-text { color: var(--cpq-text-muted); }

/* ============ Antd 暗色覆盖 ============ */
:deep(.ant-input), :deep(.ant-input-number), :deep(.ant-input-number-input),
:deep(.ant-input-affix-wrapper), :deep(.ant-input-search .ant-input) {
  background: var(--cpq-overlay-w6) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-input-affix-wrapper:focus),
:deep(.ant-input-affix-wrapper-focused) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a10) !important;
}
:deep(.ant-select-selector) {
  background: var(--cpq-overlay-w6) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-select-dropdown) { background: var(--cpq-bg-secondary) !important; }
:deep(.ant-select-item) { color: var(--cpq-text-primary) !important; }
:deep(.ant-select-item-option-active) { background: var(--cpq-overlay-a8) !important; }
:deep(.ant-picker) {
  background: var(--cpq-overlay-w6) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-picker-input > input) { color: var(--cpq-text-primary) !important; }
:deep(.ant-modal-content) { background: var(--cpq-bg-secondary) !important; color: var(--cpq-text-primary) !important; }
:deep(.ant-modal-header) { background: var(--cpq-bg-secondary) !important; }
:deep(.ant-modal-title) { color: var(--cpq-text-primary) !important; }
:deep(.ant-drawer-content) { background: var(--cpq-bg-secondary) !important; }
:deep(.ant-drawer-header) { background: var(--cpq-bg-secondary) !important; border-bottom-color: var(--cpq-border-primary) !important; }
:deep(.ant-drawer-title) { color: var(--cpq-text-primary) !important; }
:deep(.ant-spin-text) { color: var(--cpq-text-muted) !important; }
:deep(.ant-tag) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); color: var(--cpq-text-secondary); }
:deep(.ant-table) { background: transparent !important; }
:deep(.ant-table-thead > tr > th) {
  background: var(--cpq-overlay-w6) !important;
  color: var(--cpq-text-secondary) !important;
  border-bottom-color: var(--cpq-border-primary) !important;
  font-weight: 600;
}
:deep(.ant-table-tbody > tr > td) { border-bottom-color: var(--cpq-border-primary) !important; color: var(--cpq-text-primary) !important; }
:deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-a4) !important; }
:deep(.ant-pagination .ant-pagination-item) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); }
:deep(.ant-pagination .ant-pagination-item a) { color: var(--cpq-text-secondary); }
:deep(.ant-pagination .ant-pagination-item-active) { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
:deep(.ant-pagination .ant-pagination-item-active a) { color: var(--cpq-accent-on-primary); }
:deep(.ant-divider) { border-color: var(--cpq-border-primary); }

/* ============ 价格异动看板（抽屉内） ============ */
.movers-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.movers-head h4 { margin: 0; font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.movers-head :deep(.ant-radio-button-wrapper) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); color: var(--cpq-text-secondary); }
.movers-head :deep(.ant-radio-button-wrapper-checked) { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); }
.movers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.movers-col { display: flex; flex-direction: column; gap: 4px; }
.movers-col-title { font-size: 12px; font-weight: 600; padding: 4px 0; letter-spacing: 0.3px; }
.movers-col-title.up { color: var(--cpq-accent-success, #3fbb6c); }
.movers-col-title.down { color: var(--cpq-accent-danger); }
.movers-list { display: flex; flex-direction: column; }
.movers-row { display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center; padding: 8px 6px; border-radius: 8px; cursor: pointer; transition: background var(--cpq-transition-fast); }
.movers-row + .movers-row { border-top: 1px solid var(--cpq-border-primary); }
.movers-row:hover { background: var(--cpq-overlay-a6); }
.movers-name { font-size: 13px; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.movers-price { font-size: 12px; color: var(--cpq-text-secondary); font-variant-numeric: tabular-nums; }
.movers-delta { font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }
.movers-delta.up { color: var(--cpq-accent-success, #3fbb6c); }
.movers-delta.down { color: var(--cpq-accent-danger); }
.movers-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 14px 6px; text-align: center; }

/* ============ 比价矩阵（抽屉内） ============ */
.matrix-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.matrix-head h4 { margin: 0; font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.matrix-head :deep(.ant-radio-button-wrapper) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); color: var(--cpq-text-secondary); }
.matrix-head :deep(.ant-radio-button-wrapper-checked) { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); }
.matrix-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 18px; text-align: center; border: 1px dashed var(--cpq-border-primary); border-radius: 8px; }
.matrix-loading { display: flex; justify-content: center; padding: 24px; }
.matrix-box-wrap { padding: 8px; background: var(--cpq-overlay-w6); border-radius: 8px; margin-bottom: 12px; }
.matrix-box { width: 100%; height: 280px; }
.matrix-table-wrap { border-radius: 8px; overflow: hidden; }
.matrix-detail { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 0; }
.matrix-detail-chip { font-size: 12px; padding: 4px 10px; border-radius: 10px; background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary); color: var(--cpq-text-secondary); cursor: pointer; transition: all var(--cpq-transition-fast); }
.matrix-detail-chip:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }
.matrix-detail-chip b { color: var(--cpq-accent-primary); margin-left: 4px; }

/* ============ 疑似重复 drawer ============ */
.dup-tip { font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.7; padding: 10px 12px; background: var(--cpq-overlay-w6); border-radius: 8px; margin-bottom: 10px; }
.dup-summary { display: flex; gap: 8px; margin-bottom: 14px; }
.dup-list { display: flex; flex-direction: column; gap: 16px; }
.dup-group { display: flex; flex-direction: column; gap: 8px; }
.dup-group-head { display: flex; align-items: center; gap: 8px; }
.dup-sim { font-size: 11px; color: var(--cpq-text-muted); }
.dup-count { font-size: 11px; color: var(--cpq-accent-primary); margin-left: auto; }
.dup-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.dup-card { padding: 10px 12px; border-radius: 10px; background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary); cursor: pointer; transition: all var(--cpq-transition-fast); display: flex; flex-direction: column; gap: 4px; }
.dup-card:hover { border-color: var(--cpq-overlay-a20); background: var(--cpq-overlay-a4); transform: translateY(-1px); }
.dup-card-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); line-height: 1.35; word-break: break-all; }
.dup-card-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 11px; color: var(--cpq-text-secondary); }
.dup-sku { font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.dup-card-price { font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary); font-variant-numeric: tabular-nums; }
.dup-card-price.no-price { font-size: 12px; font-weight: 400; color: var(--cpq-text-muted); }
.dup-empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 60px 0; color: var(--cpq-text-muted); }
.dup-empty-ico { font-size: 40px; color: var(--cpq-text-muted); }
</style>
