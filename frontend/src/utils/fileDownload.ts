/**
 * Office 文件产物（PDF 报告等）下载/预览共享 helper。
 * 下载走 axios blob（带 Authorization 头），避免 <a href> 直链在 AUTH_ENABLED 下 401；
 * 预览返回 objectURL 给 iframe。AssistantPanel 文件卡与 TaskBoard 产物入口共用。
 */
import axios from 'axios'
import { attachAuthInterceptors } from '../api/authHttp'
import { downloadBlob } from './download'

const http = axios.create({ baseURL: '', timeout: 60000 })
attachAuthInterceptors(http)

async function fetchBlob(url: string): Promise<Blob> {
  const r = await http.get(url, { responseType: 'blob' })
  return r.data as Blob
}

/** 带鉴权拉取文件 blob（附件预览/上传中转共用；裸 fetch 在 AUTH_ENABLED 下会 401） */
export async function fetchAuthedBlob(url: string): Promise<Blob> {
  return fetchBlob(url)
}

export async function downloadOfficeFile(url: string, filename: string): Promise<void> {
  downloadBlob(await fetchBlob(url), filename)
}

export async function previewOfficeFileUrl(url: string): Promise<string> {
  return window.URL.createObjectURL(await fetchBlob(url))
}
