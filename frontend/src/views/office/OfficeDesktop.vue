<template>
  <div class="od-page">
    <OfficeTopBar>
      <span class="od-pill"><i class="od-led"></i><span class="od-num">{{ colleagues.length }}</span>&nbsp;位 AI 同事</span>
    </OfficeTopBar>

    <div class="od-body">
      <div class="od-head">
        <span class="od-title">{{ greeting }}</span>
        <span class="od-hello">选择一个应用开始工作</span>
      </div>

      <div class="od-center">
        <div class="od-grid">
          <!-- 应用磁贴：主体点击 = 进入该应用的 3D 办公室（工作区）；⚙ 角标 = 系统设置页 -->
          <div class="od-tile" role="button" tabindex="0" @click="openWorkspace" @keydown.enter="openWorkspace">
            <button class="od-gear" title="CPQ 系统设置" @click.stop="openSettings">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </button>

            <div class="od-tile-top">
              <div class="od-icon">C</div>
              <div class="od-id">
                <div class="od-name-row">
                  <span class="od-name">CPQ 系统</span>
                  <span class="od-chip"><i class="od-led"></i>运行中</span>
                </div>
                <div class="od-desc">商机 · 报价 · 交付全流程——AI 同事在此完成需求分析、方案配置与报价协作</div>
              </div>
            </div>

            <div class="od-live">
              <div class="od-avatars">
                <span v-for="(c, i) in avatarColleagues" :key="c.role_key" class="od-avatar"
                      :class="c.color ? undefined : 'od-av-' + (i % 3)"
                      :style="c.color ? { background: c.color } : undefined">{{ initial(c.name) }}</span>
                <span v-if="colleagues.length > 3" class="od-avatar od-more od-num">+{{ colleagues.length - 3 }}</span>
              </div>
              <span class="od-live-text"><strong class="od-num">{{ colleagues.length }}</strong> 位 AI 同事 · <strong class="od-num">{{ workingCount }}</strong> 人在工作</span>
            </div>

            <span class="od-go">进入办公室 →</span>
          </div>
        </div>

        <p class="od-hint">接入新的业务系统后，这里会出现新的应用磁贴</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/* AI 办公室桌面（应用启动台）：一块磁贴 = 一个已接入的业务系统。
   主体点击 → 该应用工作区（/office/app/cpq，现有 3D 办公室）；
   ⚙ 角标 → 该应用设置页（/office/app/cpq/settings）。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import OfficeTopBar from './OfficeTopBar.vue'
import { officeApi } from '@/api/office'

const router = useRouter()
const colleagues = ref<any[]>([])
const statuses = ref<Record<string, { status?: string }>>({})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h >= 5 && h < 11) return '早上好'
  if (h >= 11 && h < 13) return '中午好'
  if (h >= 13 && h < 18) return '下午好'
  return '晚上好'
})

const avatarColleagues = computed(() => colleagues.value.slice(0, 3))
const workingCount = computed(() =>
  Object.values(statuses.value).filter((s) => s?.status === 'working').length)

function initial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

// 路由内 push 用 base 相对路径（router base=/office/，再写全路径会叠成 /office/office/...）
function openWorkspace() { router.push('/app/cpq') }
function openSettings() { router.push('/app/cpq/settings') }

onMounted(async () => {
  try {
    const [cfg, snap] = await Promise.all([
      officeApi.teamConfig(),
      officeApi.snapshot().catch(() => ({ snapshot: {} as Record<string, { status?: string }> })),
    ])
    colleagues.value = Array.isArray(cfg.colleagues) ? cfg.colleagues : []
    statuses.value = (snap as any).snapshot || {}
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '办公室数据加载失败，请重新登录后再试')
  }
})
</script>

<style scoped>
.od-page { min-height: 100vh; display: flex; flex-direction: column; }
.od-pill {
  display: inline-flex; align-items: center; gap: 6px;
  height: 28px; padding: 0 var(--cpq-space-3); border-radius: var(--cpq-radius-full);
  font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary);
  background: var(--cpq-glass-2-bg); border: 1px solid var(--cpq-glass-border);
}
.od-led { width: 6px; height: 6px; border-radius: 50%; background: var(--cpq-color-success); box-shadow: var(--cpq-led-active-glow); }
.od-num { font-variant-numeric: tabular lining; font-feature-settings: 'tnum' 1, 'lnum' 1; }

.od-body {
  flex: 1; width: 100%; max-width: 1080px; margin: 0 auto;
  display: flex; flex-direction: column;
  padding: var(--cpq-space-5) var(--cpq-space-5) 56px;
  box-sizing: border-box;
}
.od-head { display: flex; align-items: baseline; gap: var(--cpq-space-3); margin: var(--cpq-space-2) 0 var(--cpq-space-5); }
.od-title { font-size: var(--cpq-font-size-2xl); font-weight: 700; letter-spacing: .3px; color: var(--cpq-text-primary); }
.od-hello { font-size: var(--cpq-font-size-base); color: var(--cpq-text-muted); }
.od-center { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.od-grid {
  display: grid; gap: var(--cpq-space-5);
  grid-template-columns: repeat(auto-fill, minmax(min(420px, 100%), 1fr));
  max-width: 560px;
}

.od-tile {
  position: relative; text-align: left; display: flex; flex-direction: column; gap: var(--cpq-space-4);
  padding: var(--cpq-space-5);
  border-radius: var(--cpq-radius-xl);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur)); -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  border: 1px solid var(--cpq-glass-border);
  box-shadow: var(--cpq-glass-card-shadow);
  cursor: pointer;
  transition: box-shadow var(--cpq-dur-2) var(--cpq-ease-out-expo), transform var(--cpq-dur-2) var(--cpq-ease-spring), border-color var(--cpq-dur-2) var(--cpq-ease-out-expo);
  animation: od-tile-in var(--cpq-dur-3) var(--cpq-ease-out-expo) backwards;
}
@keyframes od-tile-in { from { opacity: 0; transform: translateY(16px) scale(.98); } to { opacity: 1; transform: none; } }
.od-tile:hover { transform: translateY(-4px); box-shadow: var(--cpq-glass-card-shadow-hover); border-color: var(--cpq-glass-border-strong); }
.od-tile:active { transform: translateY(-1px) scale(.995); }

.od-tile-top { display: flex; align-items: flex-start; gap: var(--cpq-space-4); }
.od-icon {
  width: 64px; height: 64px; flex: none; border-radius: var(--cpq-radius-xl);
  background: var(--cpq-accent-gradient);
  display: grid; place-items: center;
  color: var(--cpq-accent-on-primary); font-size: var(--cpq-font-size-2xl); font-weight: 800; letter-spacing: 1px;
  box-shadow: 0 8px 20px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
  transition: transform var(--cpq-dur-2) var(--cpq-ease-spring);
}
.od-tile:hover .od-icon { transform: scale(1.06) rotate(-2deg); }
.od-id { min-width: 0; display: flex; flex-direction: column; gap: var(--cpq-space-1); padding-top: 2px; }
.od-name-row { display: flex; align-items: center; gap: var(--cpq-space-2); }
.od-name { font-size: var(--cpq-font-size-xl); font-weight: 700; color: var(--cpq-text-primary); }
.od-chip {
  display: inline-flex; align-items: center; gap: 5px;
  height: 20px; padding: 0 var(--cpq-space-2); border-radius: var(--cpq-radius-full);
  font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary);
  background: var(--cpq-glass-2-bg); border: 1px solid var(--cpq-glass-border);
}
.od-chip .od-led { width: 5px; height: 5px; }
.od-desc { font-size: var(--cpq-font-size-base); color: var(--cpq-text-muted); line-height: var(--cpq-line-height-body); }

.od-live { display: flex; align-items: center; gap: var(--cpq-space-3); margin-top: auto; padding-top: var(--cpq-space-2); }
.od-avatars { display: flex; }
.od-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  display: grid; place-items: center;
  font-size: var(--cpq-font-size-sm); font-weight: 600; color: var(--cpq-accent-on-primary);
  border: 2px solid var(--cpq-bg-primary);
  margin-left: -8px;
}
.od-avatar:first-child { margin-left: 0; }
.od-av-0 { background: var(--cpq-accent-gradient); }
.od-av-1 { background: var(--cpq-color-success); }
.od-av-2 { background: var(--cpq-color-purple); }
.od-more { background: var(--cpq-glass-2-bg); color: var(--cpq-text-secondary); border-style: dashed; font-size: var(--cpq-font-size-xs); }
.od-live-text { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.od-live-text strong { color: var(--cpq-text-secondary); font-weight: 600; }

.od-gear {
  position: absolute; top: var(--cpq-space-3); right: var(--cpq-space-3);
  width: 32px; height: 32px; border-radius: var(--cpq-radius-full);
  display: grid; place-items: center;
  color: var(--cpq-text-muted);
  background: var(--cpq-glass-2-bg); border: 1px solid var(--cpq-glass-border);
  opacity: .72;
  transition: all var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.od-gear:hover { opacity: 1; color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); transform: rotate(45deg); }
.od-gear svg { width: 15px; height: 15px; }

.od-go {
  align-self: flex-end;
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--cpq-font-size-sm); font-weight: 600; color: var(--cpq-accent-primary);
  opacity: 0; transform: translateX(-6px);
  transition: all var(--cpq-dur-2) var(--cpq-ease-out-expo);
}
.od-tile:hover .od-go { opacity: 1; transform: none; }

.od-hint { margin-top: var(--cpq-space-5); font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); text-align: center; }

@media (max-width: 720px) {
  .od-body { padding-left: var(--cpq-space-4); padding-right: var(--cpq-space-4); }
}
</style>
