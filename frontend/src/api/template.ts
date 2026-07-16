/**
 * 模板管理 API（新版，基于 Univer snapshot）
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

/** 商机 API（预览用） */
export const opportunityApi = {
  /** 获取商机列表（带报价数据摘要） */
  list: async (): Promise<any[]> => {
    const response = await api.get('/opportunities/list', {
      params: { page_size: 100 }
    })
    return response.data.items || response.data || []
  },

  /** 获取商机报价数据（用于预览注入） */
  getQuoteData: async (opportunityId: string): Promise<Record<string, any>> => {
    const response = await api.post(`/opportunities/${opportunityId}/preview-json`)
    return response.data
  }
}
