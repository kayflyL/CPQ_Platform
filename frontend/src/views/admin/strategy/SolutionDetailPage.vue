<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { MdPreview, MdCatalog } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { solutionApi, type Solution } from '@/api/solutions'
import MarkdownContent from './MarkdownContent.vue'
import { useThemeStore } from '@/store/theme'

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()
const key = route.params.key as string
const sol = ref<Solution | null>(null)
const loading = ref(false)

// 阅读页与编辑器预览同源渲染（MdPreview + github 主题），所见即所得
const EDITOR_ID = 'solution-article-preview'
const scrollElement = document.documentElement

async function load() {
  loading.value = true
  try {
    sol.value = await solutionApi.get(key)
  } catch (e) {
    message.error('方案不存在或已删除')
    router.replace('/strategies')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function goList() { router.push('/strategies') }
function goEdit() { router.push(`/strategies/solutions/${key}/edit`) }
function openLink(link?: string) {
  if (!link) return
  if (/^https?:\/\//i.test(link)) window.open(link, '_blank')
  else router.push(link)
}
// 优先按绑定的机型跳详情页（link 仅兜底），链接不随数据漂移写死
function platformLink(p: { model_id?: number; link?: string }) {
  return p.model_id ? `/servers/models/${p.model_id}` : (p.link || '')
}
function remove() {
  Modal.confirm({
    title: '删除解决方案',
    content: `确定删除「${sol.value?.title}」吗？该操作不可恢复。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await solutionApi.remove(key)
      message.success('已删除')
      router.replace('/strategies')
    },
  })
}
</script>

<template>
  <div class="dk">
    <div class="dk-bar">
      <button class="dk-back" @click="goList">← 解决方案</button>
      <span class="dk-sep">/</span>
      <span class="dk-bread">{{ sol?.title || '方案' }}</span>
      <div class="dk-actions">
        <a-button size="small" type="text" @click="goEdit">编辑</a-button>
        <a-button size="small" type="text" danger @click="remove">删除</a-button>
      </div>
    </div>

    <div v-if="loading" class="dk-empty">加载中…</div>
    <template v-else-if="sol">
      <header class="dk-hero">
        <div class="dk-kicker">
          <span class="dk-scene">Solution · {{ sol.scene }}</span>
        </div>
        <h1 class="dk-title">{{ sol.title }}</h1>
        <p v-if="sol.sub" class="dk-sub">{{ sol.sub }}</p>
        <div v-if="sol.intro" class="dk-intro"><MarkdownContent :source="sol.intro" /></div>
        <div v-if="sol.features?.length" class="dk-feats">
          <span class="dk-feat" v-for="f in sol.features" :key="f">{{ f }}</span>
        </div>
      </header>

      <!-- 单栏连续文章 + 右侧目录（同 GitHub/文档站排版），渲染与编辑器预览同源 -->
      <div class="dk-layout">
        <article class="dk-article">
          <MdPreview
            :editor-id="EDITOR_ID"
            :model-value="sol.content_md || ''"
            :theme="themeStore.isDark ? 'dark' : 'light'"
            preview-theme="github"
            code-theme="github"
          />
        </article>
        <aside class="dk-toc">
          <div class="dk-toc-label">目录</div>
          <MdCatalog
            :editor-id="EDITOR_ID"
            :scroll-element="scrollElement"
            :theme="themeStore.isDark ? 'dark' : 'light'"
            :offset-top="90"
          />
        </aside>
      </div>

      <section v-if="sol.platforms?.length" class="dk-plat">
        <div class="dk-plat-head">
          <h4 class="dk-h">适配平台</h4>
          <p class="dk-subnote">以下平台绑定机型目录中的真实机型，点卡片查看机型详情。</p>
        </div>
        <div class="dk-cfg">
          <div
            v-for="p in sol.platforms"
            :key="p.name"
            class="dk-cfg-item"
            :class="{ clickable: !!platformLink(p) }"
            @click="openLink(platformLink(p))"
          >
            <span class="dk-cfg-plat">{{ p.name }}</span>
            <span class="dk-cfg-spec">{{ p.spec }}</span>
            <span v-if="platformLink(p)" class="dk-cfg-cta">查看机型详情 →</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dk { max-width: 1200px; margin: 0 auto; padding: 8px 28px 96px; }
.dk-bar { display: flex; align-items: center; gap: 10px; margin: 0 -28px 0; padding: 12px 28px; border-bottom: 1px solid var(--cpq-glass-border); background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur)); -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur)); position: sticky; top: var(--cpq-sticky-top, 0px); z-index: 30; box-shadow: 0 6px 18px -12px rgba(0,0,0,.5); }
.dk-back { color: var(--cpq-accent-primary); cursor: pointer; font-size: 13px; font-weight: 600; background: none; border: none; padding: 0; }
.dk-sep { color: var(--cpq-text-muted); }
.dk-bread { color: var(--cpq-text-primary); font-size: 13px; font-weight: 600; }
.dk-actions { margin-left: auto; display: flex; gap: 6px; }

.dk-hero { padding: 44px 0 30px; border-bottom: 1px solid var(--cpq-glass-border); }
.dk-kicker { margin-bottom: 16px; }
.dk-scene { font-size: 11px; text-transform: uppercase; letter-spacing: .16em; color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border: 1px solid var(--cpq-accent-primary); padding: 4px 12px; border-radius: 4px; font-weight: 700; }
.dk-title { font-size: clamp(30px, 4vw, 42px); font-weight: 800; letter-spacing: -1px; line-height: 1.12; margin: 0 0 16px; color: var(--cpq-text-primary); max-width: 760px; }
.dk-sub { color: var(--cpq-text-muted); font-size: 16.5px; line-height: 1.62; margin: 0 0 18px; max-width: 720px; }
.dk-intro { color: var(--cpq-text-primary); font-size: 15px; line-height: 1.85; max-width: 760px; margin: 0 0 18px; }
.dk-intro :deep(p) { margin: 0; }
.dk-feats { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }
.dk-feat { font-size: 11px; letter-spacing: .02em; color: var(--cpq-text-secondary); background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-glass-border); padding: 4px 12px; border-radius: 20px; }

/* 文章 + 目录双栏：文章单栏连续排版（GitHub 式），目录窄侧栏吸顶 */
.dk-layout { display: flex; gap: 36px; margin-top: 8px; align-items: flex-start; }
.dk-article { flex: 1; min-width: 0; max-width: 860px; }
/* 去 md-editor 皮肤：主题底色（暗色纯黑/亮色纯白）画在根容器 .md-editor 上，透明化必须落在根，--md-bk-color 随之继承进内层 */
.dk-article :deep(.md-editor) { --md-bk-color: transparent; background: transparent; box-shadow: none; }
.dk-article :deep(.md-editor-preview) { padding: 0; }
.dk-toc { width: 224px; flex-shrink: 0; position: sticky; top: calc(var(--cpq-sticky-top, 0px) + 76px); max-height: calc(100vh - 170px); overflow: auto; }
.dk-toc-label { font-size: 11px; font-weight: 700; letter-spacing: .12em; color: var(--cpq-text-muted); margin: 0 0 8px 4px; }
.dk-toc :deep(.md-editor-catalog) { width: 100%; font-size: 13px; background: transparent; }
@media (max-width: 1100px) { .dk-toc { display: none; } .dk-article { max-width: none; } }

.dk-plat { margin-top: 44px; }
.dk-plat-head { margin-bottom: 16px; }
.dk-h { font-size: 20px; font-weight: 800; letter-spacing: -.3px; margin: 0 0 8px; color: var(--cpq-text-primary); }
.dk-subnote { color: var(--cpq-text-muted); font-size: 13px; margin: 0; }
.dk-cfg { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.dk-cfg-item { background: linear-gradient(180deg, var(--cpq-overlay-w6), var(--cpq-glass-card-bg)); border: 1px solid var(--cpq-glass-border); border-radius: 16px; padding: 20px 22px; display: flex; flex-direction: column; gap: 10px; min-height: 140px; position: relative; overflow: hidden; transition: all .2s cubic-bezier(.16,1,.3,1); }
.dk-cfg-item::before { content: ''; position: absolute; left: 0; top: 0; right: 0; height: 2px; background: linear-gradient(90deg, var(--cpq-accent-primary), transparent); opacity: .6; }
.dk-cfg-item.clickable { cursor: pointer; }
.dk-cfg-item.clickable:hover { border-color: var(--cpq-accent-primary); transform: translateY(-3px); box-shadow: 0 16px 40px -16px rgba(0,0,0,.5); }
.dk-cfg-plat { font-size: 16px; font-weight: 800; letter-spacing: -.2px; color: var(--cpq-text-primary); }
.dk-cfg-spec { color: var(--cpq-text-muted); font-size: 12.5px; line-height: 1.7; }
.dk-cfg-cta { margin-top: auto; color: var(--cpq-accent-primary); font-size: 12.5px; font-weight: 600; }
.dk-empty { color: var(--cpq-text-muted); padding: 48px 0; text-align: center; }
</style>
