/**
 * 静态环境网格按材质合并（draw call 优化）。
 *
 * 用途:
 *   3D 办公室场景由大量小网格（墙板、桌腿、踢脚线等）组成，每个 Mesh 一次 draw call，
 *   数百个静态小物件会把 draw call 推到瓶颈。本模块遍历传入的静态环境组 root，
 *   把其中可合并的 Mesh 按「材质 + 阴影开关」分桶，各合并成一个大 Mesh 挂回 root
 *   （name = 'static-merged'），再把原始小网格隐藏。显示器屏幕（userData.monitor === true）
 *   不参与合并，保持可被单独射线拾取。
 *
 * 为什么隐藏原件而非删除（拾取代理）:
 *   three 的 Raycaster 对 visible = false 的对象仍会做射线求交（visible 只影响渲染剔除，
 *   不影响 raycast），所以隐藏后的原件继续充当「拾取代理」——射线依旧命中原件，
 *   业务层能通过原件的 userData / name 识别具体是哪个物件，拾取逻辑无需任何改动。
 *   因此原件只隐藏、不销毁，其 geometry 也不可 dispose。
 *
 * 为什么禁用合并体 raycast（m.raycast = () => {}）:
 *   合并体把全部小物件的顶点按世界坐标堆在一个几何体里，若参与拾取，射线会命中
 *   这个无业务语义的整体，且会遮住对原件代理的命中。置空 raycast 让合并体对拾取
 *   完全透明，拾取语义完全由隐藏的原件承担。
 *
 * 编辑态注意（调用方）:
 *   合并是一次性的重活（clone + toNonIndexed + applyMatrix4 + attribute 清理 + 合并）。
 *   编辑态若频繁 rebuild 场景（拖拽、增删物件），每次都重新合并会有可感知的耗时。
 *   调用方应在编辑态跳过本函数，只在进入浏览/演示态或场景结构稳定后调用一次。
 *
 * 前提: 几何体按 mesh.matrixWorld（世界空间）烘焙后挂回 root 下，因此 root 自身
 *   应处于单位变换（场景原点、无平移旋转缩放），否则合并体会被二次变换。
 */
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

interface StaticBucket {
  geometries: THREE.BufferGeometry[]
  material: THREE.Material
  castShadow: boolean
  receiveShadow: boolean
  sourceMeshes: THREE.Mesh[]
}

export function mergeStaticGroup(root: THREE.Object3D): THREE.Group {
  // 1. 先把整棵子树的 world matrix 刷到最新，后续按 matrixWorld 烘焙才正确
  root.updateMatrixWorld(true)

  // 2. 收集满足全部条件的 Mesh（收集与隐藏分离，绝不在 traverse 过程中改 visible）
  const collected: THREE.Mesh[] = []
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    if (!mesh.isMesh) return
    if ((obj as THREE.SkinnedMesh).isSkinnedMesh) return // 蒙皮顶点由骨骼逐帧驱动，无法静态烘焙
    if ((obj as THREE.Sprite).isSprite) return // Sprite 走独立渲染路径
    const material = mesh.material
    if (Array.isArray(material)) return // 多材质组无法按单一材质分桶
    if (mesh.userData.monitor === true) return // 显示器屏幕保持可被单独射线拾取，不合并
    collected.push(mesh)
  })

  // 3+4. 逐 mesh 准备几何体并按 材质 uuid|阴影开关 分桶
  const buckets = new Map<string, StaticBucket>()
  for (const mesh of collected) {
    let geo = mesh.geometry.clone()
    if (geo.index) geo = geo.toNonIndexed()
    // 烘焙到世界空间，合并体只需单位变换即可正确渲染
    geo.applyMatrix4(mesh.matrixWorld)

    // 只保留 position/normal/uv：先快照 key 再删，避免遍历时修改；
    // 属性集合统一后 mergeGeometries 才不会因不一致返回 null
    const attrKeys = Object.keys(geo.attributes)
    for (const key of attrKeys) {
      if (key !== 'position' && key !== 'normal' && key !== 'uv') {
        geo.deleteAttribute(key)
      }
    }
    geo.clearGroups()

    const material = mesh.material as THREE.Material
    const bucketKey = `${material.uuid}|${mesh.castShadow ? '1' : '0'}|${mesh.receiveShadow ? '1' : '0'}`
    let bucket = buckets.get(bucketKey)
    if (!bucket) {
      bucket = {
        geometries: [],
        material,
        castShadow: mesh.castShadow,
        receiveShadow: mesh.receiveShadow,
        sourceMeshes: [],
      }
      buckets.set(bucketKey, bucket)
    }
    bucket.geometries.push(geo)
    bucket.sourceMeshes.push(mesh)
  }

  // 5+6. 每桶合并出一个大 Mesh
  const mergedGroup = new THREE.Group()
  mergedGroup.name = 'static-merged'
  const mergedBuckets: StaticBucket[] = []
  let i = 0
  for (const bucket of buckets.values()) {
    const mergedGeo = mergeGeometries(bucket.geometries, false)
    if (!mergedGeo) {
      // 合并失败（属性不一致等）：跳过该桶，其 sourceMeshes 保持可见，场景不受影响
      console.warn(
        `[mergeStatic] 桶合并失败已跳过：材质 ${bucket.material.uuid}，${bucket.geometries.length} 个几何体`,
      )
      continue
    }

    const m = new THREE.Mesh(mergedGeo, bucket.material)
    m.castShadow = bucket.castShadow
    m.receiveShadow = bucket.receiveShadow
    m.matrixAutoUpdate = false
    m.name = 'static-merged-' + i
    // 必须禁用合并体的射线：隐藏的原件继续当拾取代理，合并体自身不参与拾取
    m.raycast = () => {}
    mergedGroup.add(m)
    mergedBuckets.push(bucket)
    i += 1
  }

  // 7. 先挂到 root，再隐藏原件——顺序不能反，避免对场景树 traverse 造成混淆
  root.add(mergedGroup)

  // 8. 隐藏成功桶的原件。three 对 visible = false 的对象仍会射线求交（visible 只影响渲染），
  //    这些不可见原件继续充当射线拾取代理，业务层拾取逻辑无需改动。
  //    用第 2 步收集好的数组逐个隐藏，不在 traverse 过程中改 visible。
  for (const bucket of mergedBuckets) {
    for (const mesh of bucket.sourceMeshes) {
      mesh.visible = false
    }
  }

  // 9. 返回合并组（调用方可用于 dispose / 调试定位）
  return mergedGroup
}
