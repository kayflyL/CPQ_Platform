/**
 * 角色资产 store 单测（R2）—— node 原生 test runner：
 *   node --test frontend/src/office3d/assets/gltfCache.test.ts
 *
 * GLB 解析（loadGltfCharacter）依赖浏览器 fetch/DOM，不在 node 单测范围；
 * 这里锁住 store 的下限：缓存命中、失败清缓存、混合成败保序、并发 reload 后到者优先。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createCharacterAssetStore, type CharacterAsset } from './gltfCache.ts'

function fakeAsset(id: string): CharacterAsset {
  return { scene: { name: id } as any, animations: [], height: 2.5, depth: 0.45, frontRotation: 0 }
}

/** 按 URL 计数的假加载器，可编程每次调用成功/失败。 */
function fakeLoader() {
  const calls: string[] = []
  const plan: Record<string, Array<'ok' | 'fail'>> = {}
  const impl = (url: string): Promise<CharacterAsset> => {
    plan[url] = plan[url] || []
    const mode = plan[url].shift() ?? 'ok'
    calls.push(url)
    return mode === 'ok' ? Promise.resolve(fakeAsset(url)) : Promise.reject(new Error('boom'))
  }
  return { impl, calls, plan }
}

test('reload 成功：按序填充 assets；同 URL 二次 reload 走缓存', async () => {
  const { impl, calls } = fakeLoader()
  const store = createCharacterAssetStore(impl)
  const first = await store.reload(['a', 'b'])
  assert.equal(first.length, 2)
  assert.deepEqual(first.map((a) => (a.scene as any).name), ['a', 'b'])
  await store.reload(['a'])
  assert.equal(calls.filter((u) => u === 'a').length, 1, 'a 应命中缓存不重复加载')
})

test('失败清缓存：失败 URL 下次 reload 可重试成功', async () => {
  const { impl, plan, calls } = fakeLoader()
  plan['x'] = ['fail', 'ok']
  const store = createCharacterAssetStore(impl)
  const r1 = await store.reload(['x'])
  assert.equal(r1.length, 0)
  const r2 = await store.reload(['x'])
  assert.equal(r2.length, 1)
  assert.equal(calls.filter((u) => u === 'x').length, 2, '失败后应重新加载')
})

test('混合成败：fulfilled 结果按 URL 序保序', async () => {
  const { impl, plan } = fakeLoader()
  plan['bad'] = ['fail']
  const store = createCharacterAssetStore(impl)
  const r = await store.reload(['ok1', 'bad', 'ok2'])
  assert.deepEqual(r.map((a) => (a.scene as any).name), ['ok1', 'ok2'])
})

test('并发 reload：后到者优先，慢一拍的旧请求结果被丢弃', async () => {
  let resolveSlow!: (v: CharacterAsset) => void
  const slow = new Promise<CharacterAsset>((r) => (resolveSlow = r))
  const loaderCalls: string[] = []
  const impl = (url: string) => {
    loaderCalls.push(url)
    return url === 'slow' ? slow : Promise.resolve(fakeAsset('fast'))
  }
  const store = createCharacterAssetStore(impl)
  const p1 = store.reload(['slow'])
  const p2 = store.reload(['fast'])
  await p2
  assert.deepEqual(store.assets.map((a) => (a.scene as any).name), ['fast'])
  resolveSlow(fakeAsset('slow'))
  await p1
  assert.deepEqual(store.assets.map((a) => (a.scene as any).name), ['fast'], '旧请求的结果不应覆盖新配置')
})
