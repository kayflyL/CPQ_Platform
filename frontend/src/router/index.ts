import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const routes = [
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/dashboard',
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '首页' }
      },
      {
        path: '/workspace',
        name: 'Workspace',
        component: () => import('@/views/quote/Workspace.vue'),
        meta: { title: '报价工作台' }
      },
      {
        path: '/opportunities',
        name: 'Opportunities',
        component: () => import('@/views/opportunity/OpportunityList.vue'),
        meta: { title: '商机线索' }
      },
      {
        path: '/opportunities/:opportunityId',
        name: 'OpportunityDetail',
        component: () => import('@/views/opportunity/OpportunityDetail.vue'),
        meta: { title: '商机详情' }
      },
      {
        path: '/recycle-bin',
        name: 'RecycleBin',
        component: () => import('@/views/opportunity/RecycleBin.vue'),
        meta: { title: '回收站' }
      },
      {
        path: '/base-pricing',
        name: 'BasePricing',
        component: () => import('@/views/admin/BasePricing.vue'),
        meta: { title: '配件' }
      },
      {
        path: '/servers',
        name: 'Servers',
        component: () => import('@/views/L6Pricing.vue'),
        meta: { title: '服务器' }
      },

      {
        path: '/excel-parser',
        name: 'ExcelParser',
        component: () => import('@/views/ExcelParser.vue'),
        meta: { title: 'Excel 解析' }
      },
      {
        path: '/business-fields',
        name: 'BusinessFields',
        component: () => import('@/views/admin/BusinessFieldManagement.vue'),
        meta: { title: '字段管理' }
      },
      {
        path: '/system-settings',
        name: 'SystemSettings',
        component: () => import('@/views/admin/SystemSettings.vue'),
        meta: { title: '系统设置' }
      },

      // Univer 导出模板（新系统）
      {
        path: '/univer-templates',
        name: 'UniverTemplateList',
        component: () => import('@/views/univer/UniverTemplateList.vue'),
        meta: { title: '导出模板' }
      },
      {
        path: '/univer-templates/:id/edit',
        name: 'UniverTemplateEdit',
        component: () => import('@/views/univer/UniverTemplateEditor.vue'),
        meta: { title: '编辑模板' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router