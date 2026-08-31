<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { solutionApi, type SolutionScene } from '@/api/solutions'
import MarkdownContent from './MarkdownContent.vue'

const route = useRoute()
const router = useRouter()
const key = route.params.key as string | undefined
const isEdit = !!key
const saving = ref(false)
const loading = ref(false)
const previewing = ref(false)
const featDraft = ref('')
const sceneOptions = ref<SolutionScene[]>([])

const labelOf = (k: string) => sceneOptions.value.find(c => c.key === k)?.label || ''

const form = reactive({
  key: '',
  scene_key: '',
  scene: '',
  title: '',
  sub: '',
  intro: '',
  content_md: '',
  features: [] as string[],
  platforms: [] as { name: string; spec: string; link?: string }[],
})

watch(() => form.scene_key, (k) => { if (k) form.scene = labelOf(k) })

function addFeature() {
  if (featDraft.value.trim()) { form.features.push(featDraft.value.trim()); featDraft.value = '' }
}
function removeFeature(i: number) { form.features.splice(i, 1) }
function togglePreview() { previewing.value = !previewing.value }

onMounted(async () => {
  loading.value = true
  try {
    sceneOptions.value = (await solutionApi.scenes()).scenes
    if (isEdit && key) {
      const s = await solutionApi.get(key)
      Object.assign(form, {
        key: s.key, scene_key: s.scene_key, title: s.title,
        sub: s.sub || '', intro: s.intro || '', content_md: s.content_md || '',
        features: [...(s.features || [])],
        platforms: [...(s.platforms || [])],
      })
    }
  } catch (e) {
    if (isEdit) { message.error('方案不存在或已删除'); router.replace('/strategies') }
    else message.error('场景列表加载失败')
  } finally {
    loading.value = false
  }
})

function cancel() { router.push(isEdit ? `/strategies/solutions/${key}` : '/strategies') }

async function save() {
  if (!form.title.trim()) { message.warning('请填写方案标题'); return }
  if (!isEdit && !form.key.trim()) { message.warning('请填写方案 key（英文标识）'); return }
  if (!form.scene_key) { message.warning('请选择应用场景'); return }
  saving.value = true
  try {
    const payload = {
      scene_key: form.scene_key,
      scene: form.scene || labelOf(form.scene_key),
      title: form.title,
      sub: form.sub, intro: form.intro, content_md: form.content_md,
      features: form.features, platforms: form.platforms,
    }
    if (isEdit && key) {
      await solutionApi.update(key, payload)
      message.success('已保存')
      router.replace(`/strategies/solutions/${key}`)
    } else {
      const created = await solutionApi.create({ ...payload, key: form.key })
      message.success('已创建')
      router.replace(`/strategies/solutions/${created.key}`)
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script><template>
  <div class="ed">
    <div class="ed-bar">
      <button class="ed-back" @click="cancel">← 返回</button>
      <span class="ed-bread">{{ isEdit ? '编辑解决方案' : '新建解决方案' }}</span>
      <div class="ed-actions">
        <a-button @click="cancel">取消</a-button>
        <a-button @click="togglePreview">{{ previewing ? '编辑' : '预览' }}</a-button>
        <a-button type="primary" :loading="saving" @click="save">保存</a-button>
      </div>
    </div>

    <div v-if="loading" class="ed-empty">加载中…</div>
    <div v-else class="ed-container">
      <!-- 1. 头部 banner 信息区：基本信息 + 价值标签 -->
      <section class="ed-card ed-banner">
        <div class="ed-banner-grid">
          <a-form layout="vertical" class="ed-fields">
            <a-form-item label="应用场景">
              <a-select v-model:value="form.scene_key" placeholder="选择应用场景">
                <a-select-option v-for="c in sceneOptions" :key="c.key" :value="c.key">{{ c.label }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="方案标识 key"><a-input v-model:value="form.key" :disabled="isEdit" placeholder="如 ai-infer" /></a-form-item>
            <a-form-item label="标题"><a-input v-model:value="form.title" placeholder="如 AI 推理一体机" /></a-form-item>
          </a-form>
          <a-form layout="vertical" class="ed-fields">
            <a-form-item label="一句话副标题"><a-input v-model:value="form.sub" placeholder="把模型装进显存，再谈吞吐" /></a-form-item>
            <a-form-item label="首段介绍（Markdown）"><a-textarea v-model:value="form.intro" :rows="3" placeholder="详情页 hero 首段，支持 **加粗**" /></a-form-item>
          </a-form>
        </div>

        <div class="ed-banner-tags">
          <h4 class="ed-sec">价值标签</h4>
          <div class="ed-tagrow">
            <a-input class="ed-tagin" v-model:value="featDraft" @press-enter="addFeature" placeholder="输入后回车添加" />
            <div class="ed-tags">
              <span v-for="(f, i) in form.features" :key="i" class="ed-tag">{{ f }} <a @click="removeFeature(i)">×</a></span>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. 中部正文区：Markdown 正文 -->
      <section class="ed-card ed-body">
        <div class="ed-sub">
          <h4 class="ed-sec">正文（Markdown）</h4>
          <a-textarea
            v-if="!previewing"
            v-model:value="form.content_md"
            class="ed-md-input"
            :rows="16"
            placeholder="## 这个负载需要什么&#10;&#10;**要点**：…&#10;&#10;## 配置思路&#10;&#10;- …"
          />
          <div v-else class="ed-md-preview"><MarkdownContent :source="form.content_md" /></div>
        </div>
      </section>

      <!-- 3. 底部：适配平台 -->
      <section class="ed-card ed-plats">
        <h4 class="ed-sec">适配平台（卡片 · 不带价格）</h4>
        <p class="ed-note">每张卡片：机型名 + 规格 + 可选的跳转链接（留空则不可点击）。</p>
        <div v-for="(p, i) in form.platforms" :key="i" class="ed-plat">
          <a-input v-model:value="p.name" placeholder="机型名，如 Orion ES22V3" />
          <a-input v-model:value="p.spec" placeholder="规格，如 双路 Xeon · 2×RTX 4090 · 128G" />
          <a-input v-model:value="p.link" placeholder="跳转链接，如 /strategies/selection" />
          <a-button size="small" danger type="text" @click="form.platforms.splice(i,1)">删</a-button>
        </div>
        <a-button size="small" block dashed @click="form.platforms.push({name:'',spec:'',link:''})">+ 添加适配平台</a-button>
      </section>
    </div>
  </div>
</template>
<style scoped>
.ed { max-width: 1180px; margin: 0 auto; padding: 8px 24px 80px; }
.ed-bar { display: flex; align-items: center; gap: 12px; margin: 0 -24px 0; padding: 12px 24px; border-bottom: 1px solid var(--cpq-glass-border); background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur)); -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur)); position: sticky; top: 0; z-index: 30; box-shadow: 0 6px 18px -12px rgba(0,0,0,.5); }
.ed-back { color: var(--cpq-accent-primary); cursor: pointer; font-size: 13px; font-weight: 600; background: none; border: none; padding: 0; }
.ed-bread { color: var(--cpq-text-primary); font-size: 13px; font-weight: 600; }
.ed-actions { margin-left: auto; display: flex; gap: 8px; }
.ed-empty { color: var(--cpq-text-muted); padding: 48px 0; text-align: center; }
.ed-container { display: flex; flex-direction: column; gap: 18px; margin-top: 24px; }
.ed-card { background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border); border-radius: 16px; padding: 22px; }
.ed-sec { font-size: 14px; font-weight: 700; color: var(--cpq-text-primary); margin: 0 0 14px; }
.ed-note { color: var(--cpq-text-muted); font-size: 12px; margin: -8px 0 12px; }
.ed-banner-grid { display: grid; grid-template-columns: 1fr 1.5fr; gap: 24px; }
@media (max-width: 800px) { .ed-banner-grid { grid-template-columns: 1fr; } }
.ed-banner-tags { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--cpq-glass-border); }
.ed-tagrow { display: flex; flex-direction: column; gap: 10px; }
.ed-tagin { max-width: 340px; }
.ed-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.ed-tag { font-size: 12px; color: var(--cpq-text-primary); background: var(--cpq-overlay-w6); padding: 3px 10px; border-radius: 10px; }
.ed-tag a { margin-left: 6px; color: var(--cpq-text-muted); cursor: pointer; }
.ed-body { display: flex; flex-direction: column; gap: 22px; }
.ed-sub + .ed-sub { border-top: 1px solid var(--cpq-glass-border); padding-top: 22px; }
.ed-md-input { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; line-height: 1.7; }
.ed-md-preview { border: 1px dashed var(--cpq-glass-border-strong); border-radius: 10px; padding: 16px; min-height: 300px; max-height: 720px; overflow: auto; background: var(--cpq-overlay-w3); }
.ed-plat { display: grid; grid-template-columns: 1fr 1.5fr 1.6fr auto; gap: 8px; align-items: center; margin-bottom: 8px; }
@media (max-width: 800px) { .ed-plat { grid-template-columns: 1fr; } }
</style>
