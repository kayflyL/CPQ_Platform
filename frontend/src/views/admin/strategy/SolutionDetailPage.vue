<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { solutionApi, type Solution } from '@/api/solutions'
import MarkdownContent from './MarkdownContent.vue'

const route = useRoute()
const router = useRouter()
const key = route.params.key as string
const sol = ref<Solution | null>(null)
const loading = ref(false)

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

function splitMd(src?: string) {
  if (!src) return [] as { heading: string; body: string }[]
  const parts = src.split(/^##\s+/m)
  const out: { heading: string; body: string }[] = []
  for (let i = 0; i < parts.length; i++) {
    const block = parts[i].trim()
    if (!block) continue
    const nl = block.indexOf('\n')
    const heading = (nl === -1 ? block : block.slice(0, nl)).trim()
    const body = (nl === -1 ? '' : block.slice(nl + 1)).trim()
    if (heading) out.push({ heading, body })
  }
  return out
}
function paragraphs(body: string) { return body.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean) }
function isNeeds(h: string) { return /需要|负载需要/.test(h) }
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

      <section class="dk-body">
        <div v-for="(sec, i) in splitMd(sol.content_md)" :key="i" class="dk-sec">
          <template v-if="isNeeds(sec.heading)">
            <h4 class="dk-sec-h">{{ sec.heading }}</h4>
            <div class="dk-needs">
              <div v-for="(para, j) in paragraphs(sec.body)" :key="j" class="dk-need-card">
                <MarkdownContent :source="para" />
              </div>
            </div>
          </template>
          <template v-else>
            <h4 class="dk-sec-h">{{ sec.heading }}</h4>
            <div class="dk-sec-body"><MarkdownContent :source="sec.body" /></div>
          </template>
        </div>
      </section>

      <section v-if="sol.platforms?.length" class="dk-plat">
        <div class="dk-plat-head">
          <h4 class="dk-h">适配平台</h4>
          <p class="dk-subnote">以下平台已按本方案负载匹配，点卡片进入配置。</p>
        </div>
        <div class="dk-cfg">
          <div
            v-for="p in sol.platforms"
            :key="p.name"
            class="dk-cfg-item"
            :class="{ clickable: !!p.link }"
            @click="openLink(p.link)"
          >
            <span class="dk-cfg-plat">{{ p.name }}</span>
            <span class="dk-cfg-spec">{{ p.spec }}</span>
            <span v-if="p.link" class="dk-cfg-cta">进入配置 →</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dk { max-width: 1080px; margin: 0 auto; padding: 8px 28px 96px; }
.dk-bar { display: flex; align-items: center; gap: 10px; margin: 0 -28px 0; padding: 12px 28px; border-bottom: 1px solid var(--cpq-glass-border); background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur)); -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur)); position: sticky; top: 0; z-index: 30; box-shadow: 0 6px 18px -12px rgba(0,0,0,.5); }
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
.dk-body { margin-top: 10px; }
.dk-sec { padding-top: 8px; }
.dk-sec + .dk-sec { margin-top: 26px; }
.dk-sec-h { font-size: 20px; font-weight: 800; letter-spacing: -.4px; color: var(--cpq-text-primary); margin: 0 0 16px; }
.dk-sec-body { max-width: 800px; }
.dk-sec-body :deep(p) { color: var(--cpq-text-secondary); }
.dk-needs { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
@media (max-width: 760px) { .dk-needs { grid-template-columns: 1fr; } }
.dk-need-card { background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border); border-radius: 14px; padding: 18px 20px; min-height: 108px; }
.dk-need-card :deep(p) { margin: 0; color: var(--cpq-text-secondary); }

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
