/** 机型目录页 3D 展示区配置接口。
 *  配置存储在数据库 l6.server_types.showcase_config，由后台管理界面维护。
 *  此文件仅提供 TypeScript 接口定义。
 */

/** 渲染参数配置 */
export interface RenderConfig {
  ambient_intensity?: number
  key_light_intensity?: number
  fill_light_intensity?: number
  key_light_color?: string
  fill_light_color?: string
  background_color?: string
  tone_mapping?: 'NoToneMapping' | 'LinearToneMapping' | 'ACESFilmicToneMapping'
  exposure?: number
}

/** 展示配置（存储在 server_types.showcase_config） */
export interface ShowcaseConfig {
  glb_path: string | null
  title: string
  description: string
  bullets: string[]
  render?: {
    light?: RenderConfig
    dark?: RenderConfig
    camera_fov?: number
    auto_rotate_speed?: number
    enable_damping?: boolean
    damping_factor?: number
  }
}

/** 从 ServerType 获取展示配置。
 *  ServerType.showcase_config 由后台管理界面维护，无需前端硬编码。
 */
export function getShowcaseConfig(type: { showcase_config?: ShowcaseConfig }): ShowcaseConfig | null {
  return type.showcase_config || null
}
