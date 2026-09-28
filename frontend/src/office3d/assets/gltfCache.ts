/**
 * 角色资产加载与缓存。（R2 自 Office3DCanvas 抽出，逻辑逐行等价）
 * 对上只暴露 CharacterAsset 抽象，不暴露 GLTFLoader 具象 —— F2 的 VRM 加载器实现同一接口即可接入。
 * store 的缓存/并发丢弃逻辑与具体加载器解耦（load 经构造参数注入），纯逻辑可单测。
 */
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { loadVrmCharacter } from './vrmLoader.ts'
import { bakeProceduralClipsIfMissing } from './glbSkeleton.ts'

export interface CharacterAsset {
  scene: THREE.Group
  animations: THREE.AnimationClip[]
  height: number
  depth: number
  frontRotation: number
  /** 资产来源 URL：同事 model_url 精确认领的依据。 */
  url?: string
}

export interface CharacterAssetStore {
  /** 当前已加载资产（reload 成功后整体替换）。 */
  readonly assets: CharacterAsset[]
  /** 按配置的模型 URL 列表重载；并发调用时后到者优先，慢一拍的旧请求结果整体丢弃。 */
  reload(urls: string[]): Promise<CharacterAsset[]>
}

export function createCharacterAssetStore(load: (url: string) => Promise<CharacterAsset>): CharacterAssetStore {
  const cache = new Map<string, Promise<CharacterAsset>>()
  const assets: CharacterAsset[] = []
  let loadSeq = 0

  /** 单 URL 的缓存式加载：命中缓存直接复用，否则解析后写入缓存。 */
  function loadCached(url: string): Promise<CharacterAsset> {
    let cached = cache.get(url)
    if (!cached) {
      cached = load(url)
      cached.catch(() => cache.delete(url))
      cache.set(url, cached)
    }
    return cached
  }

  return {
    assets,
    async reload(urls: string[]) {
      const seq = ++loadSeq
      const results = await Promise.allSettled(urls.map((url) => loadCached(url)))
      // 被更高序号的加载覆盖时丢弃结果，避免旧配置覆盖新配置。
      if (seq !== loadSeq) return assets
      assets.length = 0
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          assets.push(result.value)
        } else {
          console.error(`加载 AI 同事模型失败: ${urls[index]}`, result.reason)
        }
      })
      return assets
    },
  }
}

/** 解析单个 GLB 并获得包围盒尺寸（缓存的是加载结果，克隆时再复制场景树）。 */
export async function loadGltfCharacter(url: string): Promise<CharacterAsset> {
  const gltf = await new GLTFLoader().loadAsync(url)
  const box = new THREE.Box3().setFromObject(gltf.scene)
  const size = new THREE.Vector3()
  box.getSize(size)
  return {
    scene: gltf.scene,
    animations: gltf.animations || [],
    height: size.y || 2.5,
    depth: size.z || 0.45,
    frontRotation: 0,
  }
}

/** 按 URL 分派：.vrm 走 VRM 加载器（F2），其余走 GLB 模板；资产携带来源 URL 供按同事认领。
 * 绑骨但无动画的 GLB（AI 生成角色）自动烘焙 idle/walk/sit 并按实测朝向修正 frontRotation。 */
export async function loadCharacterAsset(url: string): Promise<CharacterAsset> {
  const asset = url.toLowerCase().endsWith('.vrm')
    ? await loadVrmCharacter(url)
    : await loadGltfCharacter(url)
  const baked = bakeProceduralClipsIfMissing(asset.scene, asset.animations)
  if (baked) {
    asset.animations = baked.clips
    asset.frontRotation = baked.frontRotation
  }
  return { ...asset, url }
}
