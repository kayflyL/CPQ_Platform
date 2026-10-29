<template>
  <div class="atc-root">
    <!-- ───────────── 模板库 ───────────── -->
    <template v-if="view === 'library'">
      <div class="atc-lib-head">
        <div>
          <div class="atc-lib-title">产出物模板</div>
          <div class="atc-hint">
            模板 = 确定性版式骨架（区块 + 图表资产引用）；AI 只填内容，渲染走 HTML→PDF 管线。工作流输出节点可选模板替代随机排版。
          </div>
        </div>
        <div class="atc-chips">
          <button class="atc-chip active" type="button">PDF</button>
          <button class="atc-chip" type="button" disabled title="下期开放">Excel</button>
          <button class="atc-chip" type="button" disabled title="下期开放">PPT</button>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div class="atc-grid">
          <div v-for="tpl in templates" :key="tpl.id" class="atc-card" @click="openEditor(tpl)">
            <div class="atc-card-top">
              <span class="atc-fmt">PDF</span>
              <span class="atc-card-name">{{ tpl.name }}</span>
              <a-popconfirm title="删除该模板？输出节点引用将回退默认渲染。" ok-text="删除" cancel-text="取消" @confirm.stop="removeTemplate(tpl)">
                <a-button class="atc-card-del" type="text" size="small" danger @click.stop><DeleteOutlined /></a-button>
              </a-popconfirm>
            </div>
            <div class="atc-card-key">{{ tpl.key }}</div>
            <div class="atc-card-desc">{{ tpl.description || '（无描述）' }}</div>
            <div class="atc-card-meta">
              <span>{{ blockSummary(tpl) }}</span>
              <span>{{ (tpl.updated_at || '').slice(0, 10) }}</span>
            </div>
          </div>
          <button class="atc-card atc-card-add" type="button" @click="createTemplate">
            <span class="atc-add-plus">＋</span>
            <span>新建 PDF 模板</span>
          </button>
        </div>
      </a-spin>
    </template>

    <!-- ───────────── PDF 编辑器（三栏 · 画布直接编辑） ───────────── -->
    <template v-else>
      <div class="aec-head">
        <button type="button" class="aec-back" title="返回模板库" @click="backToLibrary">←</button>
        <a-input v-model:value="editing.name" class="aec-name" placeholder="模板名称" />
        <a-input v-model:value="editing.key" class="aec-key" placeholder="key（唯一标识）" :disabled="!!editing.id" />
        <span class="aec-chip">{{ pages }} 页</span>
        <span class="aec-chip">{{ k.blocks.value.length }} 区块</span>
        <div class="aec-spacer" />
        <button type="button" class="aec-btn" :disabled="!k.canUndo.value" title="撤销 (Ctrl+Z)" @click="k.undo()">↶</button>
        <button type="button" class="aec-btn" :disabled="!k.canRedo.value" title="重做 (Ctrl+Y)" @click="k.redo()">↷</button>
        <button type="button" class="aec-btn" @click="openAi">按契约生成</button>
        <button type="button" class="aec-btn" @click="presetOpen = true">▦ 预设库</button>
        <button type="button" class="aec-btn" @click="openJson">{} 序列化</button>
        <button type="button" class="aec-btn" @click="openRealPreview">真实数据预览</button>
        <button type="button" class="aec-btn" :loading="pdfLoading" @click="exportSamplePdf">导出样例 PDF</button>
        <button type="button" class="aec-btn primary" :loading="saving" @click="save">保存</button>
      </div>

      <div class="aec-body">
        <!-- 左栏 · 组件库 -->
        <aside class="aec-palette">
          <div class="aec-pal-head">组 件 库</div>
          <div class="aec-pal-list">
            <template v-for="g in paletteGroups" :key="g.title">
              <div class="aec-pal-group">{{ g.title }}</div>
              <div
                v-for="item in g.items"
                :key="item.defType"
                class="aec-pal-item"
                :class="{ slot: item.slot }"
                draggable="true"
                @dragstart="onPaletteDragStart(item.defType, $event)"
                @click="k.insert(item.defType)"
              >
                <span class="aec-pal-ico">{{ item.ico }}</span>
                <span class="aec-pal-txt">
                  <span class="aec-pal-name">{{ item.name }}</span>
                  <span class="aec-pal-sub">{{ item.sub }}</span>
                </span>
              </div>
            </template>
          </div>
          <div class="aec-pal-tip">
            拖到画布任意位置插入，或点一下追加到末尾。<br />绿色 = <b>数据槽</b>（渲染时由工作流产出填充，画布显示示例内容）。
          </div>
        </aside>

        <!-- 中央 · A4 画布 -->
        <main
          ref="canvasRef"
          class="aec-canvas"
          @scroll="placeBar"
          @dragover="onCanvasDragOver"
          @drop="onCanvasDrop"
          @dragleave="onCanvasDragLeave"
          @mouseover="onCanvasHover"
          @mouseleave="onCanvasLeave"
        >
          <div class="aec-paper-outer">
            <div ref="paperRef" class="aec-paper">
              <div class="aec-blocks" ref="blocksRef">
                <div
                  v-for="blk in k.blocks.value"
                  :key="blk.id"
                  class="aec-blk"
                  :class="{ sel: k.selectionId.value === blk.id }"
                  :data-bid="blk.id"
                  draggable="true"
                  :style="{ width: spanCss(blk) }"
                  @click.stop="k.select(blk.id!)"
                  @dragstart="onBlockDragStart(blk.id!, $event)"
                >
                  <!-- 画布示意渲染（真实渲染以后端管线为准） -->
                  <div class="aec-rpt" v-html="renderBlockHtml(blk, chartAssets)" />
                </div>
                <div v-if="!k.blocks.value.length" class="aec-empty">画布为空 · 从左侧拖入组件</div>
              </div>
              <!-- 插入指示线 -->
              <div class="aec-insline" v-show="insVisible" :style="{ top: insTop + 'px' }" />
              <!-- 页界参考线 -->
              <div v-for="i in Math.max(0, pages - 1)" :key="'pg' + i" class="aec-pageguide" :style="{ top: pageGuideTop(i) }">
                <span>— 第 {{ i }} 页止 · {{ i }} / {{ pages }} —</span>
              </div>
              <span class="aec-pageno">CPQ · {{ pages }} 页</span>
            </div>
          </div>
          <!-- 统一指示条（hover/选中共用）与宽度手柄：absolute 相对画布 -->
          <div v-show="barVisible" class="aec-blkbar" :style="{ top: barTop + 'px', left: barLeft + 'px' }">
            <span class="nm" :title="barName">{{ barName }}</span>
            <span class="grip" title="拖拽排序（整块也可直接拖）" draggable="true" @dragstart="onBarGripDragStart($event)">⠿</span>
            <button type="button" :title="'宽度 · 当前 ' + spanLabel(activeSpan)" @click="withActive((id) => cycleSpan(id))">{{ spanLabel(activeSpan) }}</button>
            <button type="button" title="复制 (Ctrl+D)" @click="withActive((id) => k.duplicate(id))">⧉</button>
            <button type="button" title="上移" @click="withActive((id) => k.moveRel(id, -1))">↑</button>
            <button type="button" title="下移" @click="withActive((id) => k.moveRel(id, 1))">↓</button>
            <button type="button" class="del" title="删除 (Del)" @click="withActive((id) => k.remove(id))">✕</button>
          </div>
          <div v-show="!!k.selectionId.value" class="aec-rz" :style="{ ...rzStyle, display: rzDisplay }" title="拖拽调整宽度（吸附 12 列栅格）" @mousedown.prevent="onRzDown" />
        </main>

        <!-- 右栏 · 单面板（折叠分区 + 摘要） -->
        <aside class="aec-panel">
          <div class="aec-panel-head">
            <span class="pi">{{ panelHead.ico }}</span>
            <span class="pt">
              <span class="a">{{ panelHead.a }}</span>
              <span class="b">{{ panelHead.b }}</span>
            </span>
          </div>
          <div class="aec-panel-body">
            <template v-if="k.selectedBlock.value">
              <!-- 版式 -->
              <div class="aec-sec" :class="{ closed: !!closed.span }">
                <h5 @click="toggleSec('span')"><span class="chev">▾</span>版式<span class="sum">{{ spanLabel(spanOf(k.selectedBlock.value)) }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row">
                    <label>宽度</label>
                    <div class="aec-seg">
                      <button v-for="s in SPAN_OPTS" :key="s" type="button" :class="{ on: spanOf(k.selectedBlock.value) === s }" @click="k.setSpan(k.selectedBlock.value!.id!, s)">{{ spanLabel(s) }}</button>
                    </div>
                  </div>
                </div>
              </div>
              <!-- 内容（title/heading/callout/literal/text 标题） -->
              <div v-if="k.selectedBlock.value.type === 'title'" class="aec-sec" :class="{ closed: !!closed.content }">
                <h5 @click="toggleSec('content')"><span class="chev">▾</span>抬头<span class="sum">{{ sel.title || '（跟随文档卡）' }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row"><label>主标题</label><a-input v-model:value="sel.title" size="small" placeholder="留空 = 跟随报告名" @change="k.commit()" /></div>
                  <div class="aec-row"><label>副题</label><a-input v-model:value="sel.subtitle" size="small" placeholder="留空 = 跟随文档卡副题" @change="k.commit()" /></div>
                  <div class="aec-row">
                    <label>品牌色</label>
                    <div class="aec-swatches">
                      <span
                        v-for="c in ACCENTS"
                        :key="c.v"
                        class="aec-sw"
                        :class="{ on: (sel.accent || '#1668C0') === c.v }"
                        :title="c.t"
                        :style="{ background: c.v }"
                        @click="setAccent(sel, c.v)"
                      />
                      <span class="aec-sw aec-sw-clear" :class="{ on: !sel.accent }" title="恢复默认" @click="setAccent(sel, '')">✕</span>
                    </div>
                  </div>
                  <div class="aec-row"><label>品牌名</label><a-input v-model:value="sel.brand_name" size="small" placeholder="默认 CPQ PLATFORM" @change="k.commit()" /></div>
                  <div class="aec-row"><label>品牌副标</label><a-input v-model:value="sel.brand_tag" size="small" placeholder="留空 = 跟随生成方" @change="k.commit()" /></div>
                  <div class="aec-row">
                    <label>Logo</label>
                    <div class="aec-logo-ctl">
                      <img v-if="sel.logo_url" :src="sel.logo_url" class="aec-logo-preview" />
                      <a-upload :show-upload-list="false" accept=".png,.jpg,.jpeg,.svg" :before-upload="uploadLogo">
                        <a-button size="small">{{ sel.logo_url ? '更换' : '上传' }}</a-button>
                      </a-upload>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="k.selectedBlock.value.type === 'heading'" class="aec-sec" :class="{ closed: !!closed.content }">
                <h5 @click="toggleSec('content')"><span class="chev">▾</span>内容<span class="sum">{{ sel.title || '小节标题' }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row"><label>文本</label><a-input v-model:value="sel.title" size="small" @change="k.commit()" /></div>
                  <div class="aec-note">编号自动按顺序生成（渲染端统一编）；画布上可直接点文字修改。</div>
                </div>
              </div>
              <div v-if="k.selectedBlock.value.type === 'callout'" class="aec-sec" :class="{ closed: !!closed.content }">
                <h5 @click="toggleSec('content')"><span class="chev">▾</span>内容<span class="sum">{{ ({ blue: '蓝', green: '绿', amber: '琥珀' } as Record<string, string>)[sel.tone || 'blue'] }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row">
                    <label>色调</label>
                    <div class="aec-seg">
                      <button v-for="tn in ['blue', 'green', 'amber']" :key="tn" type="button" :class="{ on: (sel.tone || 'blue') === tn }" @click="sel.tone = tn as any; k.commit()">{{ ({ blue: '蓝', green: '绿', amber: '琥珀' } as Record<string, string>)[tn] }}</button>
                    </div>
                  </div>
                  <div class="aec-row"><label>标题</label><a-input v-model:value="sel.co_title" size="small" placeholder="提示" @change="k.commit()" /></div>
                  <div class="aec-row aec-stack"><label>正文</label><a-textarea v-model:value="sel.text" :rows="4" @change="k.commit()" /></div>
                </div>
              </div>
              <div v-if="isLiteralSel" class="aec-sec" :class="{ closed: !!closed.content }">
                <h5 @click="toggleSec('content')"><span class="chev">▾</span>内容<span class="sum">{{ (sel.text || '').slice(0, 10) }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row aec-stack"><label>文案</label><a-textarea v-model:value="sel.text" :rows="5" placeholder="支持 markdown 子集" @change="k.commit()" /></div>
                </div>
              </div>
              <!-- 绑定（text 槽） -->
              <div v-if="k.selectedBlock.value.type === 'text' && sel.source !== 'literal'" class="aec-sec" :class="{ closed: !!closed.bind }">
                <h5 @click="toggleSec('bind')"><span class="chev">▾</span>绑定<span class="sum">{{ bindSummary }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row">
                    <label>内容来源</label>
                    <a-select v-model:value="sel.source" size="small" style="width: 100%" @change="k.commit()">
                      <a-select-option value="answer">AI 答复（整段 markdown）</a-select-option>
                      <a-select-option value="payload">payload_map 字段 / 契约章节</a-select-option>
                    </a-select>
                  </div>
                  <div v-if="sel.source === 'payload'" class="aec-row">
                    <label>章节键</label>
                    <a-auto-complete
                      v-model:value="sel.key"
                      :options="contractKeyOptions"
                      size="small"
                      style="width: 100%"
                      placeholder="选择契约章节或自由输入"
                      @change="k.commit()"
                    />
                  </div>
                  <div class="aec-note">章节键需与 workflow 目标层契约一致，输出节点保存时校验对账。</div>
                </div>
              </div>
              <!-- 资产（kpi/chart/table） -->
              <div v-if="['kpi', 'chart', 'table'].includes(k.selectedBlock.value.type)" class="aec-sec" :class="{ closed: !!closed.asset }">
                <h5 @click="toggleSec('asset')"><span class="chev">▾</span>资产<span class="sum">{{ assetSummary }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row">
                    <label>资产</label>
                    <a-select :value="sel.asset" size="small" style="width: 100%" @change="(v: any) => { sel.asset = v; k.commit() }">
                      <a-select-option v-for="a in assetsFor(k.selectedBlock.value!.type)" :key="a.id" :value="a.id">{{ a.name }}（{{ a.source_page }}）</a-select-option>
                    </a-select>
                  </div>
                </div>
              </div>
              <!-- 指标构成（kpi） -->
              <div v-if="k.selectedBlock.value.type === 'kpi' && kpiCatalog.length" class="aec-sec" :class="{ closed: !!closed.metrics }">
                <h5 @click="toggleSec('metrics')"><span class="chev">▾</span>指标构成<span class="sum">{{ (sel.metrics?.length || kpiCatalog.length) + ' 项' }}</span></h5>
                <div class="sec-body">
                  <label v-for="m in kpiCatalog" :key="m.key" class="aec-check">
                    <input type="checkbox" :checked="kpiPicked(m.key)" @change="(e: any) => toggleKpi(m.key, e.target.checked)" />
                    <span>{{ m.label }}</span>
                  </label>
                  <div v-for="(m, mi) in sel.metrics || []" :key="'mr' + m.key" class="aec-kpi-row2">
                    <span class="aec-kpi-name">{{ kpiName(m.key) }}</span>
                    <a-input :value="m.label" size="small" :placeholder="kpiName(m.key)" @change="(e: any) => setKpiLabel(m.key, e.target.value)" />
                    <button type="button" class="aec-mini" :disabled="mi === 0" @click="moveKpi(mi, -1)">↑</button>
                    <button type="button" class="aec-mini" :disabled="mi === (sel.metrics || []).length - 1" @click="moveKpi(mi, 1)">↓</button>
                  </div>
                </div>
              </div>
              <!-- 统计窗口（kpi/chart/table） -->
              <div v-if="['kpi', 'chart', 'table'].includes(k.selectedBlock.value.type)" class="aec-sec" :class="{ closed: !!closed.days }">
                <h5 @click="toggleSec('days')"><span class="chev">▾</span>统计窗口<span class="sum">{{ daysTextOf(sel) }}</span></h5>
                <div class="sec-body">
                  <div class="aec-seg">
                    <button type="button" :class="{ on: !sel.params?.days }" @click="setDaysMode('follow')">跟随数据范围</button>
                    <button type="button" :class="{ on: !!sel.params?.days }" @click="setDaysMode('fixed')">固定 N 天</button>
                  </div>
                  <div v-if="sel.params?.days" class="aec-row" style="margin-top: 9px">
                    <label>天数</label>
                    <a-input-number :value="Number(sel.params.days)" size="small" :min="1" :max="730" style="width: 100%" @change="(v: any) => setDays(v)" />
                  </div>
                  <div class="aec-note">{{ sel.params?.days ? '固定窗口是报告规格的一部分（如半年章恒 183 天），不受数据范围影响；仅用于结构语义，勿与数据范围抢权。' : '默认跟随：渲染时由文档卡「数据范围」推入 days；固定窗口仅用于结构语义（如半年章 183 天）。' }}</div>
                </div>
              </div>
              <!-- 图片 -->
              <div v-if="k.selectedBlock.value.type === 'image'" class="aec-sec" :class="{ closed: !!closed.content }">
                <h5 @click="toggleSec('content')"><span class="chev">▾</span>图片<span class="sum">{{ sel.src ? '已设置' : '未设置' }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row aec-stack">
                    <label>地址</label>
                    <a-input v-model:value="sel.src" size="small" placeholder="/api/artifact-templates/logo/x.png 或外链" @change="k.commit()" />
                  </div>
                </div>
              </div>
              <!-- 图表高度 -->
              <div v-if="k.selectedBlock.value.type === 'chart'" class="aec-sec" :class="{ closed: !!closed.chartH }">
                <h5 @click="toggleSec('chartH')"><span class="chev">▾</span>高度<span class="sum">{{ (sel.height || 240) + 'px' }}</span></h5>
                <div class="sec-body">
                  <div class="aec-row">
                    <label>像素</label>
                    <a-input-number v-model:value="sel.height" size="small" :min="160" :max="420" :step="20" style="width: 100%" @change="k.commit()" />
                  </div>
                </div>
              </div>
            </template>

            <!-- 未选中：页面设置 -->
            <template v-else>
              <div class="aec-sec" :class="{ closed: !!closed.page }">
                <h5 @click="toggleSec('page')"><span class="chev">▾</span>页面设置<span class="sum">{{ titleBlock ? (titleBlock.brand_name || 'CPQ PLATFORM') : '无抬头块' }}</span></h5>
                <div class="sec-body">
                  <template v-if="titleBlock">
                    <div class="aec-row"><label>品牌名</label><a-input v-model:value="titleBlock.brand_name" size="small" placeholder="默认 CPQ PLATFORM" @change="k.commit()" /></div>
                    <div class="aec-row">
                      <label>品牌色</label>
                      <div class="aec-swatches">
                        <span
                          v-for="c in ACCENTS"
                          :key="c.v"
                          class="aec-sw"
                          :class="{ on: (titleBlock.accent || '#1668C0') === c.v }"
                          :title="c.t"
                          :style="{ background: c.v }"
                          @click="setAccent(titleBlock, c.v)"
                        />
                        <span class="aec-sw aec-sw-clear" :class="{ on: !titleBlock.accent }" title="恢复默认" @click="setAccent(titleBlock, '')">✕</span>
                      </div>
                    </div>
                    <div class="aec-row"><label>品牌副标</label><a-input v-model:value="titleBlock.brand_tag" size="small" placeholder="留空 = 跟随生成方" @change="k.commit()" /></div>
                    <div class="aec-row"><label>副题</label><a-input v-model:value="titleBlock.subtitle" size="small" placeholder="留空 = 跟随文档卡副题" @change="k.commit()" /></div>
                    <div class="aec-row">
                      <label>Logo</label>
                      <div class="aec-logo-ctl">
                        <img v-if="titleBlock.logo_url" :src="titleBlock.logo_url" class="aec-logo-preview" />
                        <a-upload :show-upload-list="false" accept=".png,.jpg,.jpeg,.svg" :before-upload="uploadLogoToTitle">
                          <a-button size="small">{{ titleBlock.logo_url ? '更换' : '上传' }}</a-button>
                        </a-upload>
                      </div>
                    </div>
                  </template>
                  <div v-else class="aec-note">画布无抬头块（title）：加一个「报告抬头」即可在此钉品牌与副题。</div>
                </div>
              </div>
              <div class="aec-sec" :class="{ closed: !!closed.contract }">
                <h5 @click="toggleSec('contract')">
                  <span class="chev">▾</span>数据契约<span class="sum">{{ contractRows.length + ' 槽' }}</span>
                  <button type="button" class="aec-mini" style="margin-left: 8px" @click.stop="openRec">按契约校验</button>
                </h5>
                <div class="sec-body">
                  <div
                    v-for="(row, i) in contractRows"
                    :key="i"
                    class="aec-ct-row"
                    role="button"
                    tabindex="0"
                    @click="k.select(contractRows[i].bid!)"
                    @keydown.enter="k.select(contractRows[i].bid!)"
                  >
                    <span class="aec-ct-dot" :class="row.who" />
                    <span class="aec-ct-sym">{{ row.sym }}</span>
                    <span class="aec-ct-note">{{ row.note }}</span>
                  </div>
                </div>
              </div>
              <div class="aec-note" style="margin-top: 10px">
                渲染配方：区块 + 图表资产（服务端取数）→ HTML（A4）→ Playwright PDF。文本槽由输出节点的 AI 答复或 payload_map 填充，模板层零 AI。
              </div>
            </template>
          </div>
          <!-- 图层（常驻折叠区） -->
          <details class="aec-layers" open>
            <summary>图 层 <span class="cnt">{{ k.blocks.value.length }} 区块</span></summary>
            <div class="aec-layerlist">
              <div
                v-for="blk in k.blocks.value"
                :key="'l' + blk.id"
                class="aec-layer"
                :class="{ on: k.selectionId.value === blk.id, slot: !!blockDef(blk.type)?.slot }"
                @click="k.select(blk.id!)"
              >
                <span class="li">{{ blockDef(blk.type)?.ico }}</span>
                <span class="ln"><span class="a">{{ blockDef(blk.type)?.label }}</span><span class="b">{{ blockDisplayName(blk, chartAssets) }}</span></span>
                <span class="aec-layer-sp">{{ spanLabel(spanOf(blk)) }}</span>
              </div>
            </div>
          </details>
        </aside>
      </div>

      <!-- 真实数据预览抽屉 -->
      <a-drawer v-model:open="previewOpen" title="真实数据预览（后端渲染 · 取真库数据）" width="860" destroy-on-close>
        <a-spin :spinning="previewLoading">
          <iframe v-if="previewHtml" class="aec-preview-frame" :srcdoc="previewHtml" title="真实数据预览" />
          <div v-else class="aec-empty" style="height: 300px">加载中…</div>
        </a-spin>
      </a-drawer>

      <!-- 预设模板库抽屉 -->
      <a-drawer v-model:open="presetOpen" title="预设模板库" width="380">
        <div class="aec-preset-list">
          <div v-for="(p, i) in PRESETS" :key="p.name" class="aec-preset-card" @click="applyPreset(i)">
            <div class="aec-preset-thumb">
              <span class="aec-preset-tag" :style="{ background: p.tagColor }">{{ p.tag }}</span>
              <div class="aec-preset-thumb-inner" v-html="p.thumb" />
            </div>
            <div class="aec-preset-meta">
              <div class="n">{{ p.name }}</div>
              <div class="d">{{ p.desc }}</div>
            </div>
          </div>
        </div>
      </a-drawer>

      <!-- 序列化查看器 -->
      <a-modal v-model:open="jsonOpen" title="blocks JSON（存库即此结构 · version+1）" :footer="null" width="640px">
        <pre class="aec-json">{{ jsonText }}</pre>
      </a-modal>

      <!-- 按契约生成（过程可见 · 六步揭晓） -->
      <a-modal v-model:open="aiOpen" title="按契约生成模板骨架 · 过程可见" :footer="null" width="880px" destroy-on-close>
        <div v-if="!aiStarted" class="aecg-wrap" style="padding: 4px 2px 8px">
          <div class="aec-note" style="margin-bottom: 12px">
            生成依据 = 契约全文（含每章内容要求）；图表 / KPI 从资产货架智能调用，每个图表可追溯出处。结果进画布可撤销，不自动保存。
          </div>
          <div class="aec-row">
            <label>契约</label>
            <a-select v-model:value="aiFlowKey" style="width: 100%" :options="contractSelectOptions" placeholder="选择工作流文档卡契约" />
          </div>
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <button type="button" class="aec-btn primary" :disabled="aiLoading" @click="doGenerate">{{ aiLoading ? '生成中…' : '开始生成' }}</button>
          </div>
        </div>
        <div v-else class="aecg-wrap">
          <div class="aecg-head">
            <div class="t">依据 = 契约全文（含每章内容要求）；资产货架 = 实现手段；每个图表可追溯出处</div>
            <span class="sig">过程可见 · 非黑盒</span>
          </div>
          <div class="aecg-stage">
            <div class="aecg-rail">
              <div v-for="(s, i) in aiStepList" :key="s.key" class="aecg-step" :class="stepCls(i)">
                <span class="no">{{ i + 1 }}</span>
                <span class="bd"><div class="t">{{ s.title }}</div></span>
                <span class="spin" />
              </div>
            </div>
            <div class="aecg-feed" ref="aiFeedRef">
              <template v-for="(s, i) in aiRevealedSteps" :key="i + '-' + s.key">
                <!-- step1 契约 -->
                <div v-if="s.key === 'contract'" class="aecg-card">
                  <div class="ct">契约内容 <span class="tag">目标层文档卡 · 原文</span></div>
                  <div class="chips">
                    <span class="chip">报告名 <b>{{ s.items.name }}</b></span>
                    <span class="chip range">数据范围：{{ s.items.range }}</span>
                    <span class="chip">{{ (s.items.sections || []).length }} 个章节</span>
                  </div>
                  <div style="margin-top: 8px">
                    <div v-for="(sec, si) in s.items.sections" :key="si" class="aecg-row">
                      <span class="who">{{ Number(si) + 1 }}、{{ sec.title }}</span>
                      <span class="need">{{ sec.requires }}</span>
                    </div>
                  </div>
                </div>
                <!-- step2 内容要求解析 -->
                <div v-else-if="s.key === 'requires'" class="aecg-card">
                  <div class="ct">数据需求抽取 <span class="tag">逐章 · 依据=内容要求原文</span></div>
                  <div v-for="(c, ci) in s.items.chapters || []" :key="ci" class="aecg-row">
                    <span class="who">{{ c.title }}</span>
                    <span class="need"><span v-for="(n, ni) in c.needs || []" :key="ni" class="aecg-tagchip">{{ n }}</span></span>
                  </div>
                </div>
                <!-- step3 资产匹配 -->
                <div v-else-if="s.key === 'match'" class="aecg-card">
                  <div class="ct">需求 × 资产 <span class="tag">货架=资产注册表 · 每条带出处</span></div>
                  <div v-for="(m, mi) in s.items.maps || []" :key="mi" class="aecg-map">
                    <span class="a">{{ m.a }}</span><span class="m">→</span><span class="b">{{ m.b }}</span>
                    <span class="src">出处 {{ m.src }}</span>
                  </div>
                  <div v-if="!(s.items.maps || []).length" class="aecg-row"><span class="need">AI 未返回匹配明细</span></div>
                </div>
                <!-- step4 骨架 -->
                <div v-else-if="s.key === 'compose'" class="aecg-card">
                  <div class="ct">区块序列 <span class="tag">章节槽照契约顺序 · 绿=数据块</span></div>
                  <div class="aecg-blkseq">
                    <span v-for="(b, bi) in s.items.seq || []" :key="bi" class="seq" :class="{ data: b.data }">{{ b.type }}<i v-if="b.note"> {{ b.note }}</i></span>
                  </div>
                </div>
                <!-- step5 校验 -->
                <div v-else-if="s.key === 'validate'" class="aecg-card">
                  <div class="ct">确定性校验 <span class="tag">LLM 只提议 · 规则裁决</span></div>
                  <div v-for="(c, ci) in s.items.checks || []" :key="ci" class="aecg-vrow">
                    <span class="vk">{{ c.k }}</span><span class="vv">{{ c.v }}</span>
                  </div>
                </div>
                <!-- step6 完成 -->
                <div v-else class="aecg-fin">✓ {{ s.title }} · 骨架就绪 · 进画布后可继续增删图表，Ctrl+Z 可退回</div>
              </template>
              <div v-if="aiLoading" class="aecg-row" style="justify-content: center">生成中…（读取契约 → 逐章解析 → 匹配货架 → 编排 → 校验）</div>
            </div>
          </div>
          <div class="aecg-foot">
            <span class="aec-note" style="flex: 1">生成依据 = 契约全文（含每章内容要求）；图表/KPI 从资产货架调用，全部带出处；进画布后可继续增删。</span>
            <button type="button" class="aec-btn" @click="aiOpen = false">取消</button>
            <button type="button" class="aec-btn primary" :disabled="!aiDone" @click="applyGenerated">骨架进画布</button>
          </div>
        </div>
      </a-modal>

      <!-- 按契约校验 / 补齐 -->
      <a-modal v-model:open="recOpen" title="按契约校验 / 补齐（确定性 · 无 AI）" :confirm-loading="recLoading" ok-text="应用补齐" cancel-text="取消" @ok="doReconcile">
        <div class="aec-row">
          <label>契约</label>
          <a-select v-model:value="recFlowKey" style="width: 100%" :options="contractSelectOptions" placeholder="选择工作流文档卡契约" />
        </div>
        <div class="aec-note">缺的章节槽按契约追加（title=章节名）；未知 key 只报不删。</div>
      </a-modal>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import axios from 'axios'
import {
  artifactTemplateApi,
  type ArtifactBlock,
  type ArtifactTemplate,
  type ChartAssetMeta,
  type DocContract,
  type GenerateResult,
  type GenerateTraceStep,
  type KpiMetricPick,
} from '@/api/artifactTemplates'
import {
  BLOCK_DEFS, SPAN_OPTS, blockDef, blockDisplayName, blockUid, renderBlockHtml, skeletonBlocks, spanLabel,
  useArtifactKernel,
} from '@/components/artifact/useArtifactKernel'

/* ───────────── 库 ───────────── */
const view = ref<'library' | 'editor'>('library')
const loading = ref(false)
const templates = ref<ArtifactTemplate[]>([])
const chartAssets = ref<ChartAssetMeta[]>([])

const editing = reactive({ id: 0, key: '', name: '', description: '' })
const saving = ref(false)
const pdfLoading = ref(false)

const k = useArtifactKernel([])

/* ───────────── 画布交互状态 ───────────── */
const canvasRef = ref<HTMLElement | null>(null)
const paperRef = ref<HTMLElement | null>(null)
const blocksRef = ref<HTMLElement | null>(null)

const hoverId = ref('')
const insVisible = ref(false)
const insTop = ref(0)
let draggedJustNow = false
const closed = reactive<Record<string, boolean>>({})

const barVisible = computed(() => !!(hoverId.value || k.selectionId.value))
const barName = computed(() => {
  const id = hoverId.value || k.selectionId.value
  const blk = k.blocks.value.find((b) => b.id === id)
  return blk ? blockDisplayName(blk, chartAssets.value) : ''
})
const activeId = computed(() => hoverId.value || k.selectionId.value)
const activeSpan = computed(() => spanOf(k.blocks.value.find((b) => b.id === activeId.value)))
const barTop = ref(0)
const barLeft = ref(0)
const rzStyle = ref<{ top: string; left: string }>({ top: '0px', left: '0px' })
const rzDisplay = ref('none')

function spanOf(blk?: ArtifactBlock | null): number {
  const n = Number(blk?.span)
  return [4, 6, 8, 12].includes(n) ? n : 12
}
function spanCss(blk: ArtifactBlock): string {
  const s = spanOf(blk)
  return s === 12 ? '100%' : `calc(${s}/12*100% - 7px)`
}

/* ───────────── 指示条 / 宽度手柄定位 ───────────── */
function placeBar() {
  const canvas = canvasRef.value, blocksEl = blocksRef.value
  if (!canvas || !blocksEl) return
  const id = hoverId.value || k.selectionId.value
  const blk = k.blocks.value.find((b) => b.id === id)
  const bar = canvas.querySelector<HTMLElement>('.aec-blkbar')
  if (!blk || !bar) { rzDisplay.value = 'none'; return }
  const el = blocksEl.querySelector<HTMLElement>(`[data-bid="${blk.id}"]`)
  if (!el) { bar.style.display = 'none'; rzDisplay.value = 'none'; return }
  const wr = canvas.getBoundingClientRect(), r = el.getBoundingClientRect()
  const sx = canvas.scrollLeft, sy = canvas.scrollTop
  bar.style.display = 'flex'
  barTop.value = Math.max(2, r.top - wr.top + sy - 24)
  barLeft.value = Math.max(2, r.left - wr.left + sx)
  if (k.selectionId.value === blk.id) {
    rzStyle.value = {
      top: `${r.top - wr.top + sy + r.height / 2 - 16}px`,
      left: `${r.right - wr.left + sx - 5}px`,
    }
    rzDisplay.value = 'flex'
  } else rzDisplay.value = 'none'
}

function withActive(fn: (id: string) => void) {
  const id = hoverId.value || k.selectionId.value
  if (!id) return
  if (id !== k.selectionId.value) k.select(id)
  fn(id)
}
function cycleSpan(id: string) {
  const cur = spanOf(k.blocks.value.find((b) => b.id === id))
  k.setSpan(id, SPAN_OPTS[(SPAN_OPTS.indexOf(cur as 4 | 6 | 8 | 12) + 1) % 4])
}

/* ───────────── 画布拖放（palette 插入 + 整块拖拽 + 指示线） ───────────── */
let dragCtx: { idx: number } | null = null

function onPaletteDragStart(defType: string, e: DragEvent) {
  e.dataTransfer?.setData('text/plain', 'new:' + defType)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}
function onBlockDragStart(id: string, e: DragEvent) {
  const el = blocksRef.value?.querySelector<HTMLElement>(`[data-bid="${id}"]`)
  if (el && e.target instanceof Node && el.querySelector('[data-edit]') && (e.target as HTMLElement).closest?.('[data-edit]')) {
    e.preventDefault()
    return
  }
  e.dataTransfer?.setData('text/plain', 'move:' + id)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
  // craft.js createShadow：拖拽幽灵 = 块 DOM 克隆
  if (el) {
    const ghost = el.cloneNode(true) as HTMLElement
    ghost.style.position = 'absolute'
    ghost.style.left = '-9999px'
    ghost.style.top = '-9999px'
    ghost.style.width = el.offsetWidth + 'px'
    document.body.appendChild(ghost)
    e.dataTransfer?.setDragImage(ghost, 24, 24)
    setTimeout(() => ghost.remove(), 0)
  }
}
function onBarGripDragStart(e: DragEvent) {
  if (!activeId.value) { e.preventDefault(); return }
  e.dataTransfer?.setData('text/plain', 'move:' + activeId.value)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function insertionIndex(clientY: number): number {
  const els = [...(blocksRef.value?.querySelectorAll<HTMLElement>('.aec-blk') || [])]
  for (let i = 0; i < els.length; i++) {
    const r = els[i].getBoundingClientRect()
    if (clientY < r.top + r.height / 2) return i
  }
  return els.length
}
function onCanvasDragOver(e: DragEvent) {
  if (!e.dataTransfer?.types.includes('text/plain')) return
  e.preventDefault()
  dragCtx = { idx: insertionIndex(e.clientY) }
  const els = [...(blocksRef.value?.querySelectorAll<HTMLElement>('.aec-blk') || [])]
  const blocksTop = blocksRef.value ? blocksRef.value.getBoundingClientRect().top : 0
  let y: number
  if (!els.length) y = 8
  else if (dragCtx.idx >= els.length) {
    const r = els[els.length - 1].getBoundingClientRect()
    y = r.bottom - blocksTop + 7
  } else {
    const r = els[dragCtx.idx].getBoundingClientRect()
    y = r.top - blocksTop + 7
  }
  insTop.value = y - (paperRef.value ? paperRef.value.getBoundingClientRect().top : 0)
  insVisible.value = true
}
function onCanvasDrop(e: DragEvent) {
  e.preventDefault()
  insVisible.value = false
  const data = e.dataTransfer?.getData('text/plain') || ''
  if (!dragCtx) return
  const idx = dragCtx.idx
  dragCtx = null
  draggedJustNow = true
  setTimeout(() => { draggedJustNow = false }, 80)
  if (data.startsWith('new:')) k.insert(data.slice(4), idx)
  else if (data.startsWith('move:')) {
    const id = data.slice(5)
    const from = k.blocks.value.findIndex((b) => b.id === id)
    let to = idx
    if (from > -1 && from < idx) to = idx - 1
    if (from !== to && to > -1) k.move(id, to)
  }
}
function onCanvasDragLeave(e: DragEvent) {
  if (e.target === canvasRef.value || (e.target as HTMLElement).id === 'paper') insVisible.value = false
}

/* ───────────── 右缘宽度手柄 ───────────── */
function onRzDown() {
  const id = k.selectionId.value
  if (!id || !blocksRef.value) return
  document.body.classList.add('aec-resizing')
  const blocksLeft = blocksRef.value.getBoundingClientRect().left
  const onMove = (ev: MouseEvent) => {
    const frac = ((ev.clientX - blocksLeft) / (blocksRef.value?.offsetWidth || 1)) * 12
    const span = SPAN_OPTS.reduce((a, b) => (Math.abs(b - frac) < Math.abs(a - frac) ? b : a))
    const blk = k.blocks.value.find((x) => x.id === id)
    if (blk && spanOf(blk) !== span) {
      blk.span = span === 12 ? undefined : span
      placeBar()
    }
  }
  const onUp = () => {
    document.body.classList.remove('aec-resizing')
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    if (draggedJustNow) return
    k.commit()
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

/* ───────────── 画布内联编辑（contenteditable，blur 提交） ───────────── */
function wireEditables() {
  const els = blocksRef.value?.querySelectorAll<HTMLElement>('[data-edit]') || []
  els.forEach((el) => {
    el.setAttribute('contenteditable', 'true')
    el.addEventListener('blur', () => {
      const host = el.closest('.aec-blk') as HTMLElement | null
      const blk = k.blocks.value.find((b) => b.id === host?.dataset.bid)
      if (!blk) return
      const txt = el.innerText.trim()
      const field = 'text' in blk && el.closest('.aec-rpt') && (blk.type === 'callout' || (blk.type === 'text' && blk.source === 'literal')) ? 'text' : 'title'
      if (blk.type === 'callout' && el.closest('.aec-co-body')) {
        if (blk.text !== txt) { blk.text = txt; k.commit() }
      } else if (blk.type === 'callout' && el.closest('.aec-co-title')) {
        if (blk.co_title !== txt) { blk.co_title = txt; k.commit() }
      } else if (blk.text !== undefined && (blk.type === 'text' && blk.source === 'literal') && el.closest('.aec-literal')) {
        if (blk.text !== txt) { blk.text = txt; k.commit() }
      } else if (blk.title !== txt) {
        blk.title = txt
        k.commit()
      }
      void field
    })
  })
}

/* ───────────── 页界参考线 ───────────── */
const pages = ref(1)
let ro: ResizeObserver | null = null
function measurePages() {
  const blocksEl = blocksRef.value
  if (!blocksEl) return
  pages.value = Math.max(1, Math.ceil((blocksEl.scrollHeight || 1) / 1123))
}
function pageGuideTop(i: number): string {
  const blocksEl = blocksRef.value
  if (!blocksEl || !paperRef.value) return '0px'
  return `${blocksEl.offsetTop + i * 1123 - 30}px`
}

/* ───────────── 画布悬停（指示条跟随） ───────────── */
function onCanvasHover(e: MouseEvent) {
  const host = (e.target as HTMLElement).closest?.('.aec-blk') as HTMLElement | null
  const id = host?.dataset.bid || ''
  if (id && id !== hoverId.value) { hoverId.value = id; placeBar() }
}
function onCanvasLeave() {
  if (hoverId.value) { hoverId.value = ''; placeBar() }
}

watch(
  () => [k.blocks.value, editing.name],
  () => {
    nextTick(() => { wireEditables(); measurePages(); placeBar() })
  },
  { deep: true },
)
watch(
  () => k.selectionId.value,
  () => nextTick(placeBar),
)

/* ───────────── 面板：组件库分组 / 区块属性 ───────────── */
const paletteGroups = computed(() => {
  const groups: { title: string; items: { defType: string; ico: string; name: string; sub: string; slot?: boolean }[] }[] = []
  for (const d of BLOCK_DEFS) {
    let g = groups.find((x) => x.title === d.group)
    if (!g) { g = { title: d.group, items: [] }; groups.push(g) }
    g.items.push({ defType: d.type, ico: d.ico, name: d.label, sub: d.sub, slot: d.slot })
  }
  if (chartAssets.value.length) {
    groups.push({
      title: '图表资产',
      items: chartAssets.value.map((a) => ({
        defType: a.kind === 'kpi' ? 'kpi' : a.kind === 'table' ? 'table' : 'chart',
        ico: a.kind === 'kpi' ? '◧' : a.kind === 'table' ? '▦' : '▲',
        name: a.name,
        sub: `点击插入 · ${a.source_page}`,
        slot: true,
      })),
    })
  }
  return groups
})

const sel = computed(() => k.selectedBlock.value as ArtifactBlock & Record<string, any>)
const titleBlock = computed(() => k.blocks.value.find((b) => b.type === 'title') || null)
const isLiteralSel = computed(() => k.selectedBlock.value?.type === 'text' && sel.value.source === 'literal')
const panelHead = computed(() => {
  const b = k.selectedBlock.value
  if (!b) return { ico: '▤', a: '页面设置', b: '未选中区块 · 模板级设置' }
  const def = blockDef(b.type)
  return { ico: def?.ico || '▪', a: blockDisplayName(b, chartAssets.value), b: def?.sub || '' }
})

const bindSummary = computed(() => {
  if (!k.selectedBlock.value || k.selectedBlock.value.type !== 'text') return ''
  if (sel.value.source === 'literal') return '静态文案'
  if (sel.value.source === 'payload') return sel.value.key ? `payload.${sel.value.key}` : '未绑定'
  return 'AI 答复'
})
const assetSummary = computed(() => {
  const a = chartAssets.value.find((x) => x.id === sel.value.asset)
  return a ? a.name : sel.value.asset || '未选资产'
})
const kpiCatalog = computed(() => (sel.value.type === 'kpi' ? chartAssets.value.find((a) => a.id === sel.value.asset)?.metrics || [] : []))
function kpiPicked(key: string): boolean {
  return (sel.value.metrics || []).some((m) => m.key === key)
}
function toggleKpi(key: string, on: boolean) {
  const cur: KpiMetricPick[] = sel.value.metrics || kpiCatalog.value.map((m) => ({ key: m.key }))
  sel.value.metrics = on ? [...cur, { key }] : cur.filter((m) => m.key !== key)
  k.commit()
}
function kpiName(key: string): string {
  return kpiCatalog.value.find((m) => m.key === key)?.label || key
}
function setKpiLabel(key: string, label: string) {
  const m = (sel.value.metrics || []).find((x) => x.key === key)
  if (!m) return
  if (label) m.label = label
  else delete m.label
}
function moveKpi(i: number, dir: -1 | 1) {
  const arr = sel.value.metrics
  if (!arr) return
  const j = i + dir
  if (j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
function setDaysMode(mode: 'follow' | 'fixed') {
  sel.value.params = { ...(sel.value.params || {}) }
  if (mode === 'follow') delete sel.value.params.days
  else sel.value.params.days = Number(sel.value.params.days) || 30
  k.commit()
}
function setDays(v: any) {
  sel.value.params = { ...(sel.value.params || {}), days: Number(v) || 30 }
  k.commit()
}
function daysTextOf(blk: ArtifactBlock): string {
  return blk.params?.days ? `固定 ${blk.params.days} 天` : '跟随数据范围'
}
function assetsFor(type: string): ChartAssetMeta[] {
  const kind = type === 'kpi' ? 'kpi' : type === 'table' ? 'table' : 'chart'
  return chartAssets.value.filter((a) => a.kind === kind)
}
function toggleSec(key: string) {
  closed[key] = !closed[key]
}

/* ───────────── 页面设置 / 数据契约 ───────────── */
const contractRows = computed(() => {
  const rows: { who: 'ai' | 'tool' | 'sys'; sym: string; note: string; bid?: string }[] = []
  k.blocks.value.forEach((blk) => {
    if (blk.type === 'title') rows.push({ who: 'sys', sym: 'meta.title', note: '抬头品牌/副题（可钉固定文案）', bid: blk.id })
    else if (blk.type === 'heading') rows.push({ who: 'sys', sym: 'template', note: `小节题：${blk.title || ''}`, bid: blk.id })
    else if (blk.type === 'text') {
      if (blk.source === 'literal') rows.push({ who: 'sys', sym: 'template', note: '模板固定文案', bid: blk.id })
      else if (blk.source === 'payload') rows.push({ who: 'ai', sym: `payload.${blk.key || '?'}`, note: 'AI 填充：输出节点 payload_map / 契约章节', bid: blk.id })
      else rows.push({ who: 'ai', sym: 'answer', note: 'AI 填充：整段 markdown 答复', bid: blk.id })
    } else if (blk.type === 'callout') rows.push({ who: 'sys', sym: 'template', note: `提示卡：${blk.co_title || ''}`, bid: blk.id })
    else if (blk.asset) {
      const a = chartAssets.value.find((x) => x.id === blk.asset)
      rows.push({ who: 'tool', sym: `{${blk.type}:${blk.asset}}`, note: `工具取数：${a?.name || blk.asset}（${a?.source_page || '系统'}）`, bid: blk.id })
    }
  })
  return rows
})

async function uploadLogo(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await axios.post('/api/artifact-templates/logo', fd)
    if (k.selectedBlock.value?.type === 'title') k.selectedBlock.value.logo_url = res.data?.url || ''
  } catch {
    message.error('Logo 上传失败')
  }
  return false
}
function uploadLogoToTitle(file: File) {
  const tb = titleBlock.value
  const selId = k.selectionId.value
  if (tb?.id) k.select(tb.id)
  const r = uploadLogo(file)
  if (selId && tb?.id !== selId) k.select(selId)
  return r
}

/* ───────────── 库/保存/预览 ───────────── */
function blockSummary(tpl: ArtifactTemplate): string {
  const charts = tpl.blocks.filter((b) => b.type === 'chart').length
  const tables = tpl.blocks.filter((b) => b.type === 'table').length
  return `${tpl.blocks.length} 区块 · ${charts} 图 · ${tables} 表`
}
function openEditor(tpl: ArtifactTemplate) {
  editing.id = tpl.id
  editing.key = tpl.key
  editing.name = tpl.name
  editing.description = tpl.description
  k.replaceAll(JSON.parse(JSON.stringify(tpl.blocks || [])))
  view.value = 'editor'
}
function createTemplate() {
  editing.id = 0
  editing.key = ''
  editing.name = ''
  editing.description = ''
  k.replaceAll(skeletonBlocks())
  view.value = 'editor'
}
function backToLibrary() {
  view.value = 'library'
  loadTemplates()
}
async function removeTemplate(tpl: ArtifactTemplate) {
  try {
    await artifactTemplateApi.remove(tpl.id)
    message.success('已删除')
    await loadTemplates()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

async function loadTemplates() {
  loading.value = true
  try {
    templates.value = await artifactTemplateApi.list()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '模板列表加载失败')
  } finally {
    loading.value = false
  }
}
async function loadAssets() {
  try {
    chartAssets.value = await artifactTemplateApi.listChartAssets()
  } catch {
    /* 资产加载失败不阻塞编辑器 */
  }
}

async function save() {
  const key = editing.key.trim()
  if (!key) { message.warning('请填写模板 key'); return }
  if (!/^[A-Za-z0-9_-]+$/.test(key)) { message.warning('key 仅限字母/数字/-/_'); return }
  if (!k.blocks.value.length) { message.warning('至少需要一个区块'); return }
  saving.value = true
  try {
    const payload = { key, name: editing.name.trim() || key, format: 'pdf', description: editing.description, blocks: k.blocks.value }
    if (editing.id) await artifactTemplateApi.update(editing.id, payload)
    else {
      const created = await artifactTemplateApi.create(payload)
      editing.id = created.id
    }
    message.success('已保存')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

/* ───────────── 预设库 / 序列化查看器 ───────────── */
const presetOpen = ref(false)
const jsonOpen = ref(false)
const jsonText = ref('')

/* ───────────── 契约下拉 / 按契约对账 / AI 生成 ───────────── */
const contracts = ref<DocContract[]>([])
const contractSelectOptions = computed(() =>
  contracts.value.map((c) => ({ value: `${c.flow_key}||${c.doc_name}`, label: `${c.doc_name}（${c.flow_name} · ${c.sections.length} 章节）` })),
)
const contractKeyOptions = computed(() => {
  const seen = new Set<string>()
  const out: { value: string; label: string }[] = []
  for (const c of contracts.value) {
    for (const s of c.sections) {
      if (seen.has(s.key)) continue
      seen.add(s.key)
      out.push({ value: s.key, label: `${s.title} · ${s.key}（${c.flow_name}）` })
    }
  }
  return out
})
async function loadContracts() {
  try {
    contracts.value = await artifactTemplateApi.listContracts()
  } catch { /* 契约加载失败不阻塞编辑器（章节键仍可自由输入） */ }
}

const ACCENTS: { v: string; t: string }[] = [
  { v: '#1668C0', t: '品牌蓝（默认）' },
  { v: '#0E8A80', t: '青' },
  { v: '#6D5EF0', t: '紫' },
  { v: '#2F9E63', t: '绿' },
]
function setAccent(blk: ArtifactBlock, v: string) {
  if (v) blk.accent = v
  else delete blk.accent
  k.commit()
}

const aiOpen = ref(false)
const aiLoading = ref(false)
const aiFlowKey = ref('')
const aiStarted = ref(false)
const aiDone = ref(false)
const aiTrace = ref<{ steps: GenerateTraceStep[] } | null>(null)
const aiRevealed = ref(0)
const AI_STEP_TITLES = [
  { key: 'contract', title: '读取契约' },
  { key: 'requires', title: '逐章解析内容要求' },
  { key: 'match', title: '匹配资产货架' },
  { key: 'compose', title: '编排骨架' },
  { key: 'validate', title: '校验与出处标注' },
  { key: 'done', title: '骨架就绪' },
]
const aiStepList = computed(() => aiTrace.value?.steps?.length ? aiTrace.value.steps : AI_STEP_TITLES.map((s) => ({ key: s.key, title: s.title, items: {} })))
const aiRevealedSteps = computed(() => aiStepList.value.slice(0, aiRevealed.value))
function stepCls(i: number): Record<string, boolean> {
  const last = aiRevealed.value - 1
  return { done: i < last, on: i === last }
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function openAi() {
  aiFlowKey.value = contractSelectOptions.value[0]?.value || ''
  aiStarted.value = false
  aiTrace.value = null
  aiRevealed.value = 0
  aiDone.value = false
  aiOpen.value = true
}
async function doGenerate() {
  const [fk, dn] = String(aiFlowKey.value).split('||')
  if (!fk) { message.warning('请选择契约'); return }
  aiLoading.value = true
  aiStarted.value = true
  aiTrace.value = null
  aiRevealed.value = 0
  try {
    const res = await artifactTemplateApi.generate({ flow_key: fk, doc_name: dn })
    aiResult.value = res
    aiTrace.value = res.trace
    for (let i = 1; i <= res.trace.steps.length; i++) {
      aiRevealed.value = i
      await sleep(950)
      if (i < res.trace.steps.length) await sleep(500)
    }
    aiDone.value = true
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '生成失败')
    aiOpen.value = false
    aiStarted.value = false
  } finally {
    aiLoading.value = false
  }
}
const aiResult = ref<GenerateResult | null>(null)
function applyGenerated() {
  if (!aiResult.value) return
  k.replaceAll(aiResult.value.blocks)
  message.success('骨架已进画布 · Ctrl+Z 可退回 · 图表/KPI 可继续从组件库增删')
  aiOpen.value = false
}

const recOpen = ref(false)
const recLoading = ref(false)
const recFlowKey = ref('')
function openRec() {
  recFlowKey.value = contractSelectOptions.value[0]?.value || ''
  recOpen.value = true
}
async function doReconcile() {
  const [fk, dn] = String(recFlowKey.value).split('||')
  if (!fk) { message.warning('请选择契约'); return }
  recLoading.value = true
  try {
    const res = await artifactTemplateApi.reconcile({ blocks: k.blocks.value, flow_key: fk, doc_name: dn })
    k.replaceAll(res.blocks)
    message.success(
      `对账完成：补 ${res.missing_added.length} 槽` + (res.unknown_keys.length ? `；未知 key：${res.unknown_keys.join('、')}` : '；无未知 key'),
      5,
    )
    recOpen.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '对账失败')
  } finally {
    recLoading.value = false
  }
}

function thumbStd() {
  return `<div style="height:7px;width:46%;background:#1668C0;border-radius: var(--cpq-radius-xs);opacity:.85"></div>
    <div style="display:flex;gap:5px;margin-top:8px">${'<div style="flex:1;height:24px;background:#eef3fa;border-radius: var(--cpq-radius-sm)"></div>'.repeat(4)}</div>
    <div style="display:flex;gap:5px;margin-top:6px"><div style="flex:1;height:32px;background:#dfe8f4;border-radius: var(--cpq-radius-sm)"></div><div style="flex:1;height:32px;background:#dfe8f4;border-radius: var(--cpq-radius-sm)"></div></div>
    <div style="height:5px;width:82%;background:#e6ebf2;border-radius: var(--cpq-radius-xs);margin-top:8px"></div>
    <div style="height:5px;width:64%;background:#e6ebf2;border-radius: var(--cpq-radius-xs);margin-top:5px"></div>`
}
function thumbWk() {
  return `<div style="height:7px;width:38%;background:#1668C0;border-radius: var(--cpq-radius-xs);opacity:.85"></div>
    <div style="display:flex;gap:5px;margin-top:8px"><div style="flex:1;height:28px;background:#eef3fa;border-radius: var(--cpq-radius-sm)"></div><div style="flex:1;height:28px;background:#eef3fa;border-radius: var(--cpq-radius-sm)"></div></div>
    <div style="height:34px;background:#dfe8f4;border-radius: var(--cpq-radius-sm);margin-top:6px"></div>`
}
function thumbPit() {
  return `<div style="height:7px;width:52%;background:#1668C0;border-radius: var(--cpq-radius-xs);opacity:.85"></div>
    <div style="display:flex;gap:5px;margin-top:8px">${'<div style="flex:1;height:22px;background:#eef3fa;border-radius: var(--cpq-radius-sm)"></div>'.repeat(4)}</div>
    <div style="height:38px;background:#dfe8f4;border-radius: var(--cpq-radius-sm);margin-top:7px"></div>
    <div style="display:flex;gap:5px;margin-top:6px"><div style="flex:1;height:24px;background:#dfe8f4;border-radius: var(--cpq-radius-sm)"></div><div style="flex:1;height:24px;background:#dfe8f4;border-radius: var(--cpq-radius-sm)"></div></div>`
}
const PRESETS: { name: string; tag: string; tagColor: string; desc: string; thumb: string; build: () => ArtifactBlock[] }[] = [
  {
    name: 'house · 标准趋势报告', tag: '17 区块', tagColor: '#1668C0',
    desc: '抬头 + KPI + 概览双图 + 小节题 + 七章槽 + 半年表 + 玫瑰/排行并排 + 洞察卡',
    thumb: thumbStd(),
    build: () => [
      { id: blockUid(), type: 'title' },
      { id: blockUid(), type: 'kpi', asset: 'cockpit.kpi' },
      { id: blockUid(), type: 'chart', asset: 'cockpit.trend', span: 6, height: 240 },
      { id: blockUid(), type: 'chart', asset: 'cockpit.dist', span: 6, height: 240 },
      { id: blockUid(), type: 'heading', title: '半年度商机趋势' },
      { id: blockUid(), type: 'text', source: 'payload', key: 'half_year', title: '' },
      { id: blockUid(), type: 'table', asset: 'cockpit.platform_monthly', params: { days: 183 } },
      { id: blockUid(), type: 'heading', title: '平台格局' },
      { id: blockUid(), type: 'text', source: 'payload', key: 'platform', title: '' },
      { id: blockUid(), type: 'heading', 'title': '机箱形态' },
      { id: blockUid(), type: 'text', source: 'payload', key: 'chassis', title: '' },
      { id: blockUid(), type: 'chart', asset: 'cockpit.chassis_dist', span: 6, height: 240, params: { days: 183 } },
      { id: blockUid(), type: 'chart', asset: 'cockpit.sales_rank', span: 6, height: 240 },
      { id: blockUid(), type: 'text', source: 'payload', key: 'top_sales', title: '' },
      { id: blockUid(), type: 'callout', tone: 'blue', co_title: '关键洞察', text: '推理一体机需求连续三月上升，建议提前备货 GPU 密集型基准配置。' },
      { id: blockUid(), type: 'heading', title: '周数据 / 月数据' },
      { id: blockUid(), type: 'text', source: 'payload', key: 'weekly', title: '' },
      { id: blockUid(), type: 'text', source: 'payload', key: 'monthly', title: '' },
    ],
  },
  {
    name: '极简周报', tag: '5 区块', tagColor: '#16a34a',
    desc: '抬头 + KPI 双卡 + 周数据 + 趋势图 + 注意卡',
    thumb: thumbWk(),
    build: () => [
      { id: blockUid(), type: 'title' },
      { id: blockUid(), type: 'kpi', asset: 'cockpit.kpi', metrics: [{ key: 'total_opps' }, { key: 'total_configs' }] },
      { id: blockUid(), type: 'text', source: 'payload', key: 'weekly', title: '' },
      { id: blockUid(), type: 'chart', asset: 'cockpit.trend', height: 240 },
      { id: blockUid(), type: 'callout', tone: 'amber', co_title: '注意', text: 'GPU 密集型需求已连续三周上升，建议核对推理一体机基准配置库存。' },
    ],
  },
  {
    name: '图表驾驶舱', tag: '7 区块', tagColor: '#6d5ef0',
    desc: '抬头 + KPI + 树图整行 + 玫瑰/排行半行 + 明细表 + 洞察',
    thumb: thumbPit(),
    build: () => [
      { id: blockUid(), type: 'title' },
      { id: blockUid(), type: 'kpi', asset: 'cockpit.kpi' },
      { id: blockUid(), type: 'chart', asset: 'cockpit.model_trend', height: 260 },
      { id: blockUid(), type: 'chart', asset: 'cockpit.chassis_dist', span: 6, height: 240 },
      { id: blockUid(), type: 'chart', asset: 'cockpit.sales_rank', span: 6, height: 240 },
      { id: blockUid(), type: 'table', asset: 'cockpit.platform_monthly' },
      { id: blockUid(), type: 'text', source: 'payload', key: 'insights', title: '' },
    ],
  },
]

async function applyPreset(i: number) {
  k.replaceAll(PRESETS[i].build())
  presetOpen.value = false
  message.success('已载入预设 · ' + PRESETS[i].name + '（Ctrl+Z 可退回）')
}
function openJson() {
  jsonText.value = JSON.stringify(k.blocks.value, null, 1)
  jsonOpen.value = true
}

/* ───────────── 真实数据预览（后端渲染）与样例 PDF ───────────── */
const previewOpen = ref(false)
const previewHtml = ref('')
const previewLoading = ref(false)
async function openRealPreview() {
  previewOpen.value = true
  previewLoading.value = true
  previewHtml.value = ''
  try {
    previewHtml.value = await artifactTemplateApi.preview({
      key: editing.key || 'preview',
      name: editing.name,
      format: 'pdf',
      blocks: k.blocks.value,
    })
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '预览失败')
  } finally {
    previewLoading.value = false
  }
}

async function exportSamplePdf() {
  pdfLoading.value = true
  try {
    const res = await axios.post(
      '/api/artifact-templates/render-sample-pdf',
      { key: editing.key || 'sample', name: editing.name, format: 'pdf', description: editing.description, blocks: k.blocks.value },
      { responseType: 'blob' },
    )
    const url = URL.createObjectURL(res.data)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (e: any) {
    message.error(await blobDetail(e) || 'PDF 渲染失败')
  } finally {
    pdfLoading.value = false
  }
}
async function blobDetail(e: any): Promise<string> {
  try {
    if (e?.response?.data instanceof Blob) {
      const text = await e.response.data.text()
      return JSON.parse(text)?.detail || ''
    }
  } catch { /* ignore */ }
  return ''
}

/* ───────────── 键盘 ───────────── */
function onKeydown(e: KeyboardEvent) {
  const el = document.activeElement as HTMLElement | null
  const inInput = !!el && (/INPUT|TEXTAREA|SELECT/.test(el.tagName) || el.isContentEditable)
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? k.redo() : k.undo() }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); k.redo() }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') { e.preventDefault(); if (k.selectionId.value) k.duplicate(k.selectionId.value) }
  else if (!inInput && (e.key === 'Delete' || e.key === 'Backspace') && k.selectionId.value) k.remove(k.selectionId.value)
}

onMounted(() => {
  loadTemplates()
  loadAssets()
  loadContracts()
  window.addEventListener('keydown', onKeydown)
  ro = new ResizeObserver(() => { measurePages(); placeBar() })
  if (blocksRef.value) ro.observe(blocksRef.value)
  nextTick(() => { wireEditables(); measurePages(); placeBar() })
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  ro?.disconnect()
})
</script>

<style scoped>
.atc-root {
  --atc-border: #e5e7eb;
  --atc-ink: #1f2430;
  --atc-sub: #6b7280;
  --atc-blue: #1668c0;
  --atc-green: #16a34a;
  --atc-panel: #ffffff;
  --atc-soft: #f9fafb;
  color: var(--atc-ink);
  padding: 4px 2px;
}

/* ═══════════ 模板库 ═══════════ */
.atc-lib-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.atc-lib-title { font-size: 15px; font-weight: 700; }
.atc-hint { font-size: var(--cpq-font-size-sm); color: var(--atc-sub); line-height: 1.6; }
.atc-chips { display: flex; gap: 8px; flex-shrink: 0; }
.atc-chip { border: 1px solid var(--atc-border); background: var(--atc-panel); color: var(--atc-sub); border-radius: var(--cpq-radius-full); padding: 4px 14px; font-size: var(--cpq-font-size-sm); cursor: pointer; }
.atc-chip.active { border-color: var(--atc-blue); color: var(--atc-blue); font-weight: 600; }
.atc-chip:disabled { opacity: 0.45; cursor: not-allowed; }
.atc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }
.atc-card { border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-lg); background: var(--atc-panel); padding: 16px; cursor: pointer; display: flex; flex-direction: column; gap: 6px; min-height: 130px; text-align: left; transition: border-color 0.15s, box-shadow 0.15s; }
.atc-card:hover { border-color: var(--atc-blue); box-shadow: 0 4px 16px rgba(22, 104, 192, 0.1); }
.atc-card-top { display: flex; align-items: center; gap: 8px; }
.atc-fmt { font-size: 10px; font-weight: 700; color: var(--atc-blue); border: 1px solid currentColor; border-radius: var(--cpq-radius-xs); padding: 1px 5px; }
.atc-card-name { font-weight: 700; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.atc-card-del { opacity: 0; }
.atc-card:hover .atc-card-del { opacity: 1; }
.atc-card-key { font-family: ui-monospace, Consolas, monospace; font-size: var(--cpq-font-size-xs); color: var(--atc-sub); }
.atc-card-desc { font-size: var(--cpq-font-size-sm); color: var(--atc-sub); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.atc-card-meta { margin-top: auto; display: flex; justify-content: space-between; font-size: var(--cpq-font-size-xs); color: var(--atc-sub); }
.atc-card-add { border-style: dashed; align-items: center; justify-content: center; color: var(--atc-sub); background: transparent; gap: 8px; }
.atc-card-add:hover { color: var(--atc-blue); }
.atc-add-plus { font-size: 22px; line-height: 1; }

/* ═══════════ 编辑器顶栏 ═══════════ */
.aec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.aec-back { width: 30px; height: 30px; border-radius: var(--cpq-radius-sm); border: 1px solid var(--atc-border); background: var(--atc-panel); color: var(--atc-sub); cursor: pointer; }
.aec-back:hover { color: var(--atc-blue); }
.aec-name { width: 200px; }
.aec-key { width: 200px; font-family: ui-monospace, Consolas, monospace; }
.aec-chip { font-size: var(--cpq-font-size-xs); color: var(--atc-sub); background: var(--atc-soft); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-full); padding: 3px 10px; white-space: nowrap; }
.aec-spacer { flex: 1; }
.aec-btn { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 12px; border-radius: var(--cpq-radius-sm); border: 1px solid var(--atc-border); background: var(--atc-panel); color: var(--atc-ink); font-size: 12.5px; cursor: pointer; white-space: nowrap; transition: all 0.15s; }
.aec-btn:hover { border-color: var(--atc-blue); color: var(--atc-blue); }
.aec-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.aec-btn.primary { background: var(--atc-blue); border-color: var(--atc-blue); color: #fff; }
.aec-btn.primary:hover { color: #fff; filter: brightness(1.06); }
.aec-btn.ai { background: linear-gradient(135deg, #6d5ef0, #8b5cf6); border-color: transparent; color: #fff; }
.aec-btn.ai:hover { color: #fff; filter: brightness(1.06); }
.aec-swatches { display: flex; align-items: center; gap: 6px; }
.aec-sw { width: 20px; height: 20px; border-radius: var(--cpq-radius-sm); cursor: pointer; display: inline-block; border: 2px solid transparent; }
.aec-sw.on { border-color: var(--atc-ink); }
.aec-sw-clear { background: var(--atc-soft); border: 1px solid var(--atc-border); color: var(--atc-sub); font-size: 10px; line-height: 16px; text-align: center; }

/* ═══════════ 按契约生成 · 过程可见面板 ═══════════ */
.aecg-wrap { display: flex; flex-direction: column; }
.aecg-head { display: flex; align-items: center; gap: 10px; padding: 2px 2px 10px; }
.aecg-head .t { flex: 1; font-size: var(--cpq-font-size-sm); color: var(--atc-sub); }
.aecg-head .sig { font-size: 10.5px; color: var(--ink3, #9ca3af); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-full); padding: 2px 10px; white-space: nowrap; }
.aecg-stage { display: grid; grid-template-columns: 236px 1fr; gap: 12px; align-items: start; }
.aecg-rail { display: flex; flex-direction: column; gap: 7px; }
.aecg-step { display: flex; gap: 9px; align-items: center; padding: 9px 11px; border-radius: var(--cpq-radius-md); border: 1px solid var(--atc-border); background: rgba(255, 255, 255, 0.02); opacity: 0.38; transition: all 0.25s; }
.aecg-step .no { width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; font-size: var(--cpq-font-size-xs); font-weight: 800; background: var(--cpq-overlay-w8); color: var(--atc-sub); }
.aecg-step .t { font-size: 12.5px; font-weight: 700; }
.aecg-step .bd { min-width: 0; }
.aecg-step .spin { display: none; width: 11px; height: 11px; margin-left: auto; border: 2px solid rgba(22, 104, 192, 0.2); border-top-color: var(--atc-blue); border-radius: 50%; animation: aecgsp 0.7s linear infinite; }
.aecg-step.on { opacity: 1; border-color: rgba(22, 104, 192, 0.55); background: rgba(22, 104, 192, 0.08); }
.aecg-step.on .no { background: var(--atc-blue); color: #fff; }
.aecg-step.on .spin { display: block; }
.aecg-step.done { opacity: 1; }
.aecg-step.done .no { background: var(--atc-green); color: #fff; }
@keyframes aecgsp { to { transform: rotate(360deg) } }
.aecg-feed { min-height: 300px; max-height: 460px; overflow-y: auto; padding-right: 4px; }
.aecg-card { border: 1px solid var(--atc-border); background: var(--cpq-overlay-w3); border-radius: var(--cpq-radius-md); padding: 11px 13px; margin-bottom: 10px; animation: aecgpop 0.3s ease; }
@keyframes aecgpop { from { opacity: 0; transform: translateY(6px) } to { opacity: 1 } }
.aecg-card .ct { display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 800; color: var(--atc-blue); margin-bottom: 8px; }
.aecg-card .ct .tag { font-size: 10px; font-weight: 700; color: var(--atc-sub); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-full); padding: 1px 8px; letter-spacing: 0; }
.aecg-chips { display: flex; flex-wrap: wrap; gap: 7px; }
.aecg-chip, .aecg-row .need .chip { font-size: var(--cpq-font-size-xs); background: var(--cpq-overlay-w5); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-full); padding: 3px 10px; color: var(--atc-ink); }
.aecg-chip b { color: var(--atc-blue); }
.aecg-chip.range { color: var(--atc-green); border-color: rgba(22, 163, 74, 0.3); }
.aecg-row { display: flex; align-items: flex-start; gap: 8px; padding: 6px 9px; border-radius: var(--cpq-radius-sm); margin-bottom: 5px; background: rgba(255, 255, 255, 0.025); border: 1px solid var(--atc-border); font-size: var(--cpq-font-size-sm); }
.aecg-row .who { flex-shrink: 0; font-size: var(--cpq-font-size-xs); color: var(--atc-blue); font-weight: 700; width: 110px; }
.aecg-row .need { color: var(--atc-sub); line-height: 1.55; }
.aecg-tagchip { display: inline-block; font-size: var(--cpq-font-size-xs); background: var(--cpq-overlay-w5); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-full); padding: 2px 9px; margin: 1px 4px 1px 0; color: var(--atc-ink); }
.aecg-map { display: grid; grid-template-columns: minmax(130px, 160px) 18px 1fr; gap: 7px; align-items: center; padding: 7px 10px; border-radius: var(--cpq-radius-sm); margin-bottom: 5px; font-size: var(--cpq-font-size-sm); background: rgba(255, 255, 255, 0.025); border: 1px solid var(--atc-border); }
.aecg-map .a { color: var(--atc-blue); font-weight: 700; }
.aecg-map .m { color: var(--atc-sub); text-align: center; }
.aecg-map .b { color: var(--atc-green); font-weight: 700; word-break: break-all; }
.aecg-map .src { grid-column: 1 / -1; font-size: 10.5px; color: var(--atc-sub); line-height: 1.5; }
.aecg-map .src::before { content: '出处 '; color: #d08700; font-weight: 700; }
.aecg-blkseq { display: flex; flex-wrap: wrap; gap: 6px; }
.aecg-blkseq .seq { font-size: var(--cpq-font-size-xs); border: 1px solid var(--atc-border); background: var(--cpq-overlay-w4); border-radius: var(--cpq-radius-sm); padding: 4px 9px; }
.aecg-blkseq .seq.data { border-color: rgba(22, 163, 74, 0.4); color: var(--atc-green); }
.aecg-blkseq .seq i { font-style: normal; color: var(--atc-sub); margin-left: 4px; }
.aecg-vrow { display: flex; gap: 8px; align-items: flex-start; font-size: var(--cpq-font-size-sm); padding: 5px 2px; }
.aecg-vrow .vk { flex-shrink: 0; font-weight: 700; color: var(--atc-green); }
.aecg-vrow .vv { color: var(--atc-sub); line-height: 1.55; }
.aecg-fin { display: flex; align-items: center; gap: 10px; background: rgba(22, 163, 74, 0.07); border: 1px solid rgba(22, 163, 74, 0.3); border-radius: var(--cpq-radius-md); padding: 11px 14px; font-size: 12.5px; color: var(--atc-ink); }
.aecg-foot { display: flex; align-items: center; gap: 9px; padding: 10px 2px 2px; border-top: 1px solid var(--atc-border); margin-top: 8px; }

/* ═══════════ 三栏 ═══════════ */
.aec-body { display: grid; grid-template-columns: 212px minmax(0, 1fr) 306px; gap: 12px; align-items: stretch; }
.aec-palette, .aec-panel { border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-lg); background: var(--atc-panel); display: flex; flex-direction: column; overflow: hidden; max-height: calc(92vh - 120px); }
.aec-pal-head { padding: 13px 16px 6px; font-size: var(--cpq-font-size-xs); letter-spacing: 0.14em; color: var(--atc-sub); font-weight: 700; }
.aec-pal-list { padding: 2px 10px 10px; overflow-y: auto; flex: 1; }
.aec-pal-group { margin: 9px 0 4px; font-size: 11.5px; color: var(--atc-sub); font-weight: 700; padding-left: 6px; }
.aec-pal-item { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: var(--cpq-radius-md); cursor: grab; border: 1px solid transparent; transition: all 0.13s; user-select: none; margin-bottom: 2px; }
.aec-pal-item:hover { background: var(--atc-soft); border-color: rgba(22, 104, 192, 0.25); }
.aec-pal-item:active { cursor: grabbing; }
.aec-pal-ico { width: 27px; height: 27px; border-radius: var(--cpq-radius-sm); display: inline-flex; align-items: center; justify-content: center; font-size: 13px; background: rgba(22, 104, 192, 0.1); color: var(--atc-blue); flex-shrink: 0; font-weight: 700; }
.aec-pal-item.slot .aec-pal-ico { background: rgba(22, 163, 74, 0.1); color: var(--atc-green); }
.aec-pal-txt { display: flex; flex-direction: column; min-width: 0; }
.aec-pal-name { font-size: 12.5px; font-weight: 600; }
.aec-pal-sub { font-size: 10.5px; color: var(--atc-sub); margin-top: 1px; }
.aec-pal-tip { margin: auto 14px 14px; padding: 9px 12px; border-radius: var(--cpq-radius-md); background: rgba(22, 104, 192, 0.06); color: var(--atc-blue); font-size: 11.5px; line-height: 1.65; }

/* 画布 */
.aec-canvas { position: relative; overflow: auto; max-height: calc(92vh - 120px); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-lg); background: radial-gradient(rgba(31, 36, 48, 0.05) 1px, transparent 1px) 0 0 / 22px 22px, var(--atc-soft); }
.aec-paper-outer { padding: 28px 0 60px; display: flex; flex-direction: column; align-items: center; min-width: max-content; }
.aec-paper { width: 794px; min-height: 1123px; background: #fff; border-radius: var(--cpq-radius-xs); box-shadow: 0 12px 36px rgba(15, 23, 42, 0.14); padding: 56px 60px 64px; position: relative; }
.aec-blocks { display: flex; flex-wrap: wrap; gap: 14px; position: relative; min-height: 110px; }
.aec-blk { position: relative; border-radius: var(--cpq-radius-sm); outline: 1.5px solid transparent; outline-offset: 1px; transition: width 0.16s ease, outline-color 0.1s; }
.aec-blk:hover { outline-color: rgba(22, 104, 192, 0.42); }
.aec-blk.sel { outline-color: var(--atc-blue); }
.aec-insline { position: absolute; left: 60px; right: 60px; left: calc(50% - 397px + 60px); width: calc(794px - 120px); border-top: 3px solid var(--atc-blue); filter: drop-shadow(0 0 5px rgba(22, 104, 192, 0.5)); z-index: 30; pointer-events: none; display: v-bind("insVisible ? 'block' : 'none'"); transition: top 0.15s ease-in; }
.aec-pageguide { position: absolute; left: calc(50% - 397px + 24px); width: 746px; border-top: 1.5px dashed rgba(22, 104, 192, 0.35); display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 5; }
.aec-pageguide span { background: #fff; border: 1px solid rgba(22, 104, 192, 0.3); color: var(--atc-blue); font-size: 10.5px; border-radius: var(--cpq-radius-full); padding: 1px 12px; transform: translateY(-50%); }
.aec-pageno { position: absolute; bottom: 16px; right: 28px; font-size: 10px; color: #9ca3af; letter-spacing: 0.1em; }
.aec-blkbar { position: absolute; z-index: 60; display: flex; align-items: center; gap: 1px; background: var(--atc-blue); color: #fff; border-radius: var(--cpq-radius-sm); padding: 3px 4px; box-shadow: 0 10px 28px rgba(31, 45, 70, 0.22); font-size: var(--cpq-font-size-sm); }
.aec-blkbar .nm { font-size: var(--cpq-font-size-xs); font-weight: 700; padding: 3px 8px; max-width: 190px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-right: 1px solid rgba(255, 255, 255, 0.28); margin-right: 2px; }
.aec-blkbar .grip { cursor: grab; padding: 3px 6px; border-radius: var(--cpq-radius-sm); color: #cfe2f7; }
.aec-blkbar .grip:active { cursor: grabbing; }
.aec-blkbar button { color: #eaf2fc; padding: 3px 7px; border-radius: var(--cpq-radius-sm); font-size: var(--cpq-font-size-sm); background: none; border: none; cursor: pointer; }
.aec-blkbar button:hover { background: rgba(255, 255, 255, 0.18); }
.aec-blkbar button.del:hover { background: rgba(214, 69, 80, 0.9); }
.aec-rz { position: absolute; z-index: 55; top: 50%; margin-top: -16px; width: 10px; height: 32px; display: none; align-items: center; justify-content: center; cursor: ew-resize; color: #fff; }
.aec-rz::before { content: ''; width: 4.5px; height: 26px; border-radius: var(--cpq-radius-xs); background: var(--atc-blue); box-shadow: 0 0 0 3px rgba(22, 104, 192, 0.22); }

/* 画布内报表样式在文件末尾的非 scoped <style> 块 —— v-html 子树吃不到 scoped 作用域 */
.aec-rpt { position: relative; }

/* 右栏面板 */
.aec-panel-head { display: flex; align-items: center; gap: 9px; padding: 12px 16px 10px; border-bottom: 1px solid var(--atc-border); }
.aec-panel-head .pi { width: 27px; height: 27px; border-radius: var(--cpq-radius-sm); display: inline-flex; align-items: center; justify-content: center; font-size: 13px; background: rgba(22, 104, 192, 0.1); color: var(--atc-blue); font-weight: 700; flex-shrink: 0; }
.aec-panel-head .pt { display: flex; flex-direction: column; min-width: 0; }
.aec-panel-head .a { font-size: 13px; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.aec-panel-head .b { font-size: 10.5px; color: var(--atc-sub); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.aec-panel-body { flex: 1; overflow-y: auto; padding: 4px 16px 14px; }
.aec-sec { border-bottom: 1px solid var(--atc-border); padding: 9px 0 11px; }
.aec-sec h5 { display: flex; align-items: center; gap: 7px; font-size: var(--cpq-font-size-xs); color: var(--atc-blue); letter-spacing: 0.12em; font-weight: 800; margin: 0 0 9px; cursor: pointer; user-select: none; }
.aec-sec h5 .chev { font-size: 9px; transition: transform 0.15s; color: var(--atc-sub); }
.aec-sec.closed h5 .chev { transform: rotate(-90deg); }
.aec-sec h5 .sum { margin-left: auto; font-size: 10.5px; font-weight: 600; letter-spacing: 0; color: var(--atc-sub); max-width: 62%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.aec-sec.closed .sec-body { display: none; }
.aec-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: var(--cpq-font-size-sm); }
.aec-row label { width: 56px; color: var(--atc-sub); flex-shrink: 0; }
.aec-row.aec-stack { flex-direction: column; align-items: stretch; gap: 5px; }
.aec-row.aec-stack label { width: auto; }
.aec-seg { display: flex; background: var(--atc-soft); border-radius: var(--cpq-radius-sm); padding: 2px; gap: 2px; width: 100%; }
.aec-seg button { flex: 1; padding: 4px 4px; border-radius: var(--cpq-radius-sm); font-size: 11.5px; color: var(--atc-sub); background: none; border: none; cursor: pointer; }
.aec-seg button.on { background: #fff; color: var(--atc-blue); box-shadow: 0 1px 4px rgba(31, 45, 70, 0.12); font-weight: 700; }
.aec-note { font-size: var(--cpq-font-size-xs); color: var(--atc-sub); background: var(--atc-soft); border-radius: var(--cpq-radius-sm); padding: 8px 10px; line-height: 1.6; }
.aec-check { display: inline-flex; align-items: center; gap: 5px; font-size: var(--cpq-font-size-sm); cursor: pointer; margin: 2px 12px 2px 0; }
.aec-check input { accent-color: var(--atc-blue); }
.aec-kpi-row2 { display: flex; align-items: center; gap: 5px; margin: 4px 0; }
.aec-kpi-name { flex: 0 0 76px; font-size: var(--cpq-font-size-xs); color: var(--atc-sub); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.aec-mini { flex: 0 0 20px; height: 22px; font-size: var(--cpq-font-size-xs); cursor: pointer; line-height: 1; border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-xs); background: transparent; color: var(--atc-sub); }
.aec-mini:disabled { opacity: 0.35; cursor: default; }
.aec-logo-ctl { display: flex; align-items: center; gap: 6px; }
.aec-logo-preview { width: 32px; height: 32px; object-fit: contain; border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-xs); background: #fff; }
.aec-ct-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; cursor: pointer; border-radius: var(--cpq-radius-sm); padding: 3px 4px; margin: 0 -4px; transition: background 0.15s; }
.aec-ct-row:hover { background: var(--atc-soft); }
.aec-ct-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.aec-ct-dot.ai { background: var(--atc-green); }
.aec-ct-dot.tool { background: var(--atc-blue); }
.aec-ct-dot.sys { background: #9ca3af; }
.aec-ct-sym { font-family: ui-monospace, Consolas, monospace; font-size: 10.5px; color: var(--atc-ink); background: var(--atc-soft); border-radius: var(--cpq-radius-xs); padding: 1px 6px; }
.aec-ct-note { color: var(--atc-sub); font-size: 10.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.aec-layers { border-top: 1px solid var(--atc-border); padding: 8px 0 4px; }
.aec-layers summary { list-style: none; display: flex; align-items: center; gap: 7px; cursor: pointer; font-size: var(--cpq-font-size-xs); color: var(--atc-blue); letter-spacing: 0.12em; font-weight: 800; padding: 4px 16px 8px; user-select: none; }
.aec-layers summary::-webkit-details-marker { display: none; }
.aec-layers .cnt { margin-left: auto; font-size: 10px; color: var(--atc-sub); letter-spacing: 0; }
.aec-layerlist { padding: 0 10px 10px; max-height: 210px; overflow-y: auto; }
.aec-layer { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: var(--cpq-radius-sm); cursor: pointer; border: 1px solid transparent; margin-bottom: 2px; }
.aec-layer:hover { background: var(--atc-soft); }
.aec-layer.on { background: var(--atc-soft); border-color: rgba(22, 104, 192, 0.35); }
.aec-layer .li { width: 22px; height: 22px; border-radius: var(--cpq-radius-sm); display: inline-flex; align-items: center; justify-content: center; font-size: var(--cpq-font-size-xs); flex-shrink: 0; background: rgba(22, 104, 192, 0.1); color: var(--atc-blue); font-weight: 700; }
.aec-layer.slot .li { background: rgba(22, 163, 74, 0.1); color: var(--atc-green); }
.aec-layer .ln { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.aec-layer .ln .a { font-size: 11.5px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.aec-layer .ln .b { font-size: 10px; color: var(--atc-sub); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.aec-layer-sp { font-size: 9.5px; color: #9ca3af; }
.aec-empty { display: flex; align-items: center; justify-content: center; color: var(--atc-sub); font-size: 12.5px; min-height: 110px; width: 100%; }
.aec-preview-frame { width: 100%; height: calc(100vh - 160px); border: 0; background: #fff; }

[data-theme='dark'] .atc-root {
  --atc-border: rgba(255, 255, 255, 0.12);
  --atc-ink: #e5e7eb;
  --atc-sub: #9ca3af;
  --atc-panel: var(--cpq-overlay-w4);
  --atc-soft: var(--cpq-overlay-w8);
}
[data-theme='dark'] .aec-paper { box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45); }
</style>

<style>
/* ═══════════ 画布内报表内容样式（非 scoped）——v-html 子树吃不到 scoped 作用域，
   必须全局；aec-* 前缀已命名空间化，无碰撞风险。暗色主题下纸张恒白、墨色恒深。 ═══════════ */
body.aec-resizing, body.aec-resizing * { cursor: ew-resize !important; user-select: none !important; }
.aec-brandline { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid var(--atc-blue); padding-bottom: 9px; margin-bottom: 18px; }
.aec-brand { font-weight: 800; letter-spacing: 0.28em; color: var(--atc-blue); font-size: 12.5px; }
.aec-meta { font-size: var(--cpq-font-size-xs); color: #9ca3af; }
.aec-hero h1 { font-size: 28px; font-weight: 900; color: #1f2430; margin: 2px 0 0; }
.aec-accent { display: none; }
.aec-hero-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 9px; }
.aec-hero-meta span { font-size: var(--cpq-font-size-xs); color: var(--atc-sub); background: var(--atc-soft); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-full); padding: 2px 10px; }
.aec-sec-title { display: flex; align-items: baseline; gap: 10px; padding: 3px 0 2px; }
.aec-sec-title .tt { font-size: 16.5px; font-weight: 800; color: #1f2430; }
.aec-sec-title .rule { flex: 1; border-top: 1px solid rgba(22, 104, 192, 0.25); transform: translateY(-4px); }
.aec-text p { font-size: 13px; line-height: 1.9; color: #3a4350; text-align: justify; margin: 0; }
.aec-literal { font-size: 11.5px; color: var(--atc-sub); background: var(--atc-soft); border: 1px solid var(--atc-border); border-radius: var(--cpq-radius-md); padding: 10px 14px; line-height: 1.7; }
.aec-unbound { border: 1.5px dashed rgba(208, 135, 0, 0.5); border-radius: var(--cpq-radius-md); padding: 18px 16px; text-align: center; color: #d08700; font-size: var(--cpq-font-size-sm); background: rgba(208, 135, 0, 0.04); line-height: 1.7; }
.aec-slot-chip { position: absolute; top: -9px; right: 8px; z-index: 8; font-size: 10px; line-height: 1; color: var(--atc-green); background: rgba(22, 163, 74, 0.1); border: 1px solid rgba(22, 163, 74, 0.3); border-radius: var(--cpq-radius-full); padding: 3px 8px; opacity: 0.75; pointer-events: none; }
.aec-blk:hover .aec-slot-chip, .aec-blk.sel .aec-slot-chip { opacity: 1; }
.aec-kpi-row { display: flex; gap: 11px; flex-wrap: wrap; }
.aec-kpi { flex: 1; min-width: 116px; background: #f8fafd; border: 1px solid #e5e7eb; border-radius: var(--cpq-radius-md); padding: 13px 15px 11px; position: relative; }
.aec-kpi .k { font-size: var(--cpq-font-size-xs); color: var(--atc-sub); display: flex; align-items: center; gap: 6px; }
.aec-kpi .k i { width: 6px; height: 6px; border-radius: 50%; background: var(--atc-blue); opacity: 0.7; flex-shrink: 0; }
.aec-kpi .d { position: absolute; right: 12px; top: 12px; font-size: 10px; font-weight: 700; border-radius: var(--cpq-radius-full); padding: 2px 7px; }
.aec-kpi .d.up { color: #1c7c47; background: rgba(22, 163, 74, 0.12); }
.aec-kpi .vrow { display: flex; align-items: baseline; gap: 6px; margin-top: 4px; }
.aec-kpi .v { font-size: 23px; font-weight: 800; color: #123c6e; font-variant-numeric: tabular-nums; }
.aec-kpi .u { font-size: 10.5px; color: #9ca3af; }
.aec-chart { border: 1px solid #e5e7eb; border-radius: var(--cpq-radius-md); background: #fbfcfe; position: relative; overflow: hidden; }
.aec-chart .cap { position: absolute; left: 11px; top: 9px; font-size: 11.5px; font-weight: 700; color: #414b5c; z-index: 2; }
.aec-chart .wm { position: absolute; right: 10px; bottom: 7px; font-size: 10px; color: #9ca3af; background: rgba(255, 255, 255, 0.85); border-radius: var(--cpq-radius-sm); padding: 1px 7px; z-index: 2; }
.aec-chart svg { display: block; width: 100%; height: 100%; }
.aec-table { width: 100%; border-collapse: collapse; font-size: var(--cpq-font-size-sm); border-radius: var(--cpq-radius-md); overflow: hidden; border: 1px solid #e5e7eb; }
.aec-table th { background: #f7f8fa; color: #414b5c; font-weight: 700; padding: 7px 11px; text-align: left; border-bottom: 1px solid #e5e7eb; }
.aec-table td { padding: 6px 11px; border-bottom: 1px solid #eef0f3; color: #3a4350; font-variant-numeric: tabular-nums; }
.aec-table tr.sum td { font-weight: 800; color: #123c6e; background: #f4f8fd; border-top: 1.5px solid rgba(22, 104, 192, 0.25); }
.aec-callout { border: 1px solid #dbeafe; background: #f5f9ff; border-radius: var(--cpq-radius-md); padding: 12px 15px; display: flex; gap: 10px; align-items: flex-start; }
.aec-callout.tone-green { border-color: #d3eedd; background: #f4fbf6; }
.aec-callout.tone-amber { border-color: #f3e3c0; background: #fdf9f0; }
.aec-callout .ci { font-size: var(--cpq-font-size-base); line-height: 1.4; }
.aec-callout .aec-co-title { font-size: 12.5px; font-weight: 800; color: #1f2430; margin-bottom: 3px; }
.aec-callout .aec-co-body { font-size: var(--cpq-font-size-sm); color: #3a4350; line-height: 1.75; }
.aec-divider { border: none; border-top: 1px solid #e5e7eb; margin: 5px 0; }
.aec-img { max-width: 100%; border-radius: var(--cpq-radius-sm); }
.aec-imgph { border: 1.5px dashed rgba(31, 36, 48, 0.22); border-radius: var(--cpq-radius-md); background: var(--atc-soft); display: grid; place-items: center; color: var(--atc-sub); font-size: var(--cpq-font-size-sm); min-height: 84px; }
[data-edit] { outline: none; border-radius: var(--cpq-radius-xs); }
[data-edit]:hover { box-shadow: 0 0 0 2px rgba(22, 104, 192, 0.2); }
[data-edit]:focus { box-shadow: 0 0 0 2px rgba(22, 104, 192, 0.45); background: rgba(22, 104, 192, 0.04); }
</style>
