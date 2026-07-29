import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const routes = [
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/opportunities',
    children: [
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
        path: '/parts',
        name: 'Parts',
        component: () => import('@/views/admin/Parts.vue'),
        meta: { title: '配件' }
      },
      {
        path: '/base-pricing',
        redirect: '/parts'
      },
      {
        path: '/servers',
        name: 'Servers',
        component: () => import('@/views/ServerConfig.vue'),
        meta: { title: '服务器配置' }
      },
      {
        path: '/servers/admin',
        name: 'ServersAdmin',
        component: () => import('@/views/ServerAdminPage.vue'),
        meta: { title: '服务器管理' }
      },
      {
        path: '/servers/types/:typeId',
        name: 'ServerModels',
        component: () => import('@/views/ServerModelsPage.vue'),
        meta: { title: '机型目录' }
      },
      {
        path: '/servers/config/:modelId',
        name: 'ServerConfigWizard',
        component: () => import('@/views/ConfigWizardPage.vue'),
        meta: { title: '服务器配置' }
      },
      {
        path: '/servers/base-configs/new',
        name: 'BaseConfigNew',
        component: () => import('@/views/server-admin/BaseConfigEditorPage.vue'),
        meta: { title: '新建基准配置' }
      },
      {
        path: '/servers/base-configs/:id',
        name: 'BaseConfigEdit',
        component: () => import('@/views/server-admin/BaseConfigEditorPage.vue'),
        meta: { title: '编辑基准配置' }
      },

      {
        path: '/servers/models/new',
        name: 'ServerModelNew',
        component: () => import('@/views/server-admin/ModelEditorPage.vue'),
        meta: { title: '新建机型' }
      },
      {
        path: '/servers/models/:modelId',
        name: 'ServerModelDetail',
        component: () => import('@/views/server-config/ModelDetailPage.vue'),
        meta: { title: '机型详情' }
      },
      {
        path: '/servers/models/:modelId/edit',
        name: 'ServerModelEdit',
        component: () => import('@/views/server-admin/ModelEditorPage.vue'),
        meta: { title: '编辑机型' }
      },

      {
        path: '/excel-parser',
        name: 'ExcelParser',
        component: () => import('@/views/ExcelParser.vue'),
        meta: { title: 'Excel 解析' }
      },

      // 策略中心
      {
        path: '/strategies',
        name: 'Strategies',
        component: () => import('@/views/admin/Strategies.vue'),
        meta: { title: '策略中心' }
      },

      // 导出模板（统一入口）
      {
        path: '/export-templates',
        name: 'ExportTemplates',
        component: () => import('@/views/export-templates/ExportTemplateList.vue'),
        meta: { title: '导出模板' }
      },

      // AI 设置
      {
        path: '/ai-settings',
        name: 'AiSettings',
        component: () => import('@/views/settings/AiSettings.vue'),
        meta: { title: 'AI 设置' }
      },
      
      // Univer 模板编辑器（Excel）
      {
        path: '/export-templates/excel/:id/edit',
        name: 'UniverTemplateEdit',
        component: () => import('@/views/univer/UniverTemplateEditor.vue'),
        meta: { title: '编辑 Excel 模板' }
      },
      
      // 规格书模板编辑器
      {
        path: '/export-templates/spec/:id/edit',
        name: 'SpecTemplateEdit',
        component: () => import('@/views/spec-templates/SpecTemplateEditor.vue'),
        meta: { title: '编辑规格书模板' }
      },
      {
        path: '/export-templates/spec/new',
        name: 'SpecTemplateNew',
        component: () => import('@/views/spec-templates/SpecTemplateEditor.vue'),
        meta: { title: '新建规格书模板' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
