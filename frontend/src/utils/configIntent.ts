/**
 * 方案助手「自然进入需求分析」的意图识别（纯函数，可单测）。
 *
 * 用户聊着聊着说想配置服务器 → 不必手动点「需求分析」，这里自动识别：
 *   - isConfigIntent(text)：强配置意图（配台/帮我配/选配/需求分析/生成BOM…）→ 直接进入需求分析
 *   - hasServerWord(text)：提到服务器但意图弱（想买/问价…）→ 对话里给「开始选配」按钮兜底
 *
 * 词表可配：system_config.ai_assistant_config.intent_words（后端默认在 system_config_repo 维护）；
 * 未配置时用下方内置默认（拒绝把业务词写死在组件里，全部收敛到这一个函数）。
 */
export const DEFAULT_CONFIG_INTENT_WORDS: string[] = [
  '配置服务器', '配一台服务器', '配台服务器', '配个服务器', '服务器配置',
  '帮我配', '给我配', '怎么配', '要配一台', '配置一台', '做一台服务器',
  '选配', '选型', '需求分析', '生成方案', '生成bom', '整机方案', '报价', 'bom',
] as const

const SERVER_WORD_RE = /服务器|主机|整机|机器|server/i

export function configIntentWords(words?: string[]): string[] {
  const list = (words || []).map((w) => String(w || '').trim().toLowerCase()).filter(Boolean)
  return list.length ? list : [...DEFAULT_CONFIG_INTENT_WORDS.map((w) => w.toLowerCase())]
}

/** 强配置意图：命中词表（子串，大小写不敏感）→ 自动进入需求分析。 */
export function isConfigIntent(text: string, words?: string[]): boolean {
  const low = (text || '').toLowerCase()
  if (!low) return false
  return configIntentWords(words).some((w) => w && low.includes(w))
}

/** 弱服务器意图：提到服务器/主机但没强到直接进分析 → 给「开始选配」按钮。 */
export function hasServerWord(text: string): boolean {
  return SERVER_WORD_RE.test(text || '')
}
