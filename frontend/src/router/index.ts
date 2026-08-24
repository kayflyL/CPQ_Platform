import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/forbidden',
    name: 'Forbidden',
    component: () => import('@/views/Forbidden.vue'),
    meta: { title: '无权访问' }
  },
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/portal',
    children: [
      {
        path: '/portal',
        name: 'Portal',
        component: () => import('@/views/portal/Portal.vue'),
        meta: { title: '工作台', aiEntryPoint: true }
      },
      {
        path: '/portal/opps',
        redirect: '/opportunities',
      },
      {
        path: '/portal/workstation/:view',
        name: 'PortalWorkstation',
        component: () => import('@/views/portal/PortalWorkstationView.vue'),
        meta: { title: '门户工作台', perm: 'page.opportunities', aiEntryPoint: true }
      },
      {
        path: '/workspace',
        name: 'Workspace',
        component: () => import('@/views/quote/Workspace.vue'),
        meta: { title: '报价工作台', perm: 'page.opportunities', aiEntryPoint: true }
      },
      {
        path: '/opportunities',
        name: 'Opportunities',
        component: () => import('@/views/opportunity/OpportunityList.vue'),
        meta: { title: '商机线索', perm: 'page.opportunities_all', aiEntryPoint: true }
      },
      {
        path: '/opportunities/:opportunityId',
        name: 'OpportunityDetail',
        component: () => import('@/views/opportunity/OpportunityDetail.vue'),
        meta: { title: '商机详情', perm: 'page.opportunities', aiEntryPoint: true }
      },
      {
        path: '/recycle-bin',
        name: 'RecycleBin',
        component: () => import('@/views/opportunity/RecycleBin.vue'),
        meta: { title: '回收站', perm: 'page.opportunities' }
      },
      {
        path: '/parts',
        name: 'Parts',
        component: () => import('@/views/admin/Parts.vue'),
        meta: { title: '配件', perm: 'page.parts' }
      },
      {
        path: '/base-pricing',
        redirect: '/parts'
      },
      {
        path: '/servers',
        name: 'Servers',
        component: () => import('@/views/ServerConfig.vue'),
        meta: { title: '服务器配置', perm: 'page.servers' }
      },
      {
        path: '/servers/admin',
        name: 'ServersAdmin',
        component: () => import('@/views/ServerAdminPage.vue'),
        meta: { title: '服务器管理', perm: 'page.settings.admin' }
      },
      {
        path: '/servers/types/:typeId',
        name: 'ServerModels',
        component: () => import('@/views/ServerModelsPage.vue'),
        meta: { title: '机型目录', perm: 'page.servers' }
      },
      {
        path: '/servers/config/:modelId',
        name: 'ServerConfigWizard',
        component: () => import('@/views/ConfigWizardPage.vue'),
        meta: { title: '服务器配置', perm: 'page.servers' }
      },
      {
        path: '/servers/base-configs/new',
        name: 'BaseConfigNew',
        component: () => import('@/views/server-admin/BaseConfigEditorPage.vue'),
        meta: { title: '新建基准配置', perm: 'page.settings.admin' }
      },
      {
        path: '/servers/base-configs/:id',
        name: 'BaseConfigEdit',
        component: () => import('@/views/server-admin/BaseConfigEditorPage.vue'),
        meta: { title: '编辑基准配置', perm: 'page.settings.admin' }
      },

      {
        path: '/servers/models/new',
        name: 'ServerModelNew',
        component: () => import('@/views/server-admin/ModelEditorPage.vue'),
        meta: { title: '新建机型', perm: 'page.settings.admin' }
      },
      {
        path: '/servers/models/:modelId',
        name: 'ServerModelDetail',
        component: () => import('@/views/server-config/ModelDetailPage.vue'),
        meta: { title: '机型详情', perm: 'page.servers' }
      },
      {
        path: '/servers/models/:modelId/edit',
        name: 'ServerModelEdit',
        component: () => import('@/views/server-admin/ModelEditorPage.vue'),
        meta: { title: '编辑机型', perm: 'page.settings.admin' }
      },
      {
        path: '/servers/drawing/:modelId',
        name: 'ServerDrawingConfig',
        component: () => import('@/views/admin/ServerDrawingConfig.vue'),
        meta: { title: '服务器图纸配置', perm: 'page.settings.admin' }
      },

      {
        path: '/excel-parser',
        name: 'ExcelParser',
        component: () => import('@/views/ExcelParser.vue'),
        meta: { title: 'Excel 解析', perm: 'page.settings.excel' }
      },

      // 策略中心（门户 + 3 模块：对标服务器模块的真路由下钻）
      {
        path: '/strategies',
        name: 'StrategyPortal',
        component: () => import('@/views/admin/StrategyPortal.vue'),
        meta: { title: '策略中心', perm: 'page.strategies' }
      },
      {
        path: '/strategies/pricing',
        name: 'StrategyPricing',
        component: () => import('@/views/admin/pricing/PricingWorkspace.vue'),
        meta: { title: '报价策略', perm: 'page.strategies' }
      },
      {
        path: '/strategies/selection',
        name: 'StrategySelection',
        component: () => import('@/views/admin/selection/SelectionWorkspace.vue'),
        meta: { title: '选型配置', perm: 'page.strategies', aiEntryPoint: true }
      },
      {
        path: '/strategies/requirement',
        name: 'StrategyRequirement',
        component: () => import('@/views/admin/requirement/RequirementWorkspace.vue'),
        meta: { title: '需求分析', perm: 'page.strategies' }
      },
      // 导出模板（统一入口）
      {
        path: '/export-templates',
        name: 'ExportTemplates',
        component: () => import('@/views/export-templates/ExportTemplateList.vue'),
        meta: { title: '导出模板', perm: 'page.settings.templates' }
      },

      // AI 办公室（全局实时视图 + Manage Teams 画布入口）
      {
        path: '/ai-office',
        name: 'AiOffice',
        component: () => import('@/views/office/AiOfficeView.vue'),
        meta: { title: 'AI 办公室', aiEntryPoint: true }
      },
      
      // Univer 模板编辑器（Excel）
      {
        path: '/export-templates/excel/:id/edit',
        name: 'UniverTemplateEdit',
        component: () => import('@/views/univer/UniverTemplateEditor.vue'),
        meta: { title: '编辑 Excel 模板', perm: 'page.settings.templates' }
      },
      
      // 用户与权限（RBAC 管理，仅管理员可见）
      {
        path: '/settings/users',
        name: 'UserRoleManagement',
        component: () => import('@/views/admin/UserRoleManagement.vue'),
        meta: { title: '用户与权限', perm: 'page.settings.users' }
      },

      // 规格书模板编辑器
      {
        path: '/export-templates/spec/:id/edit',
        name: 'SpecTemplateEdit',
        component: () => import('@/views/spec-templates/SpecTemplateEditor.vue'),
        meta: { title: '编辑规格书模板', perm: 'page.settings.templates' }
      },
      {
        path: '/export-templates/spec/new',
        name: 'SpecTemplateNew',
        component: () => import('@/views/spec-templates/SpecTemplateEditor.vue'),
        meta: { title: '新建规格书模板', perm: 'page.settings.templates' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 登录守卫：未登录 → /login；已登录访问 /login → 首页
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureConfig()
  if (!auth.loaded) await auth.loadMe()
  if (to.path === '/login') {
    return auth.isAuthenticated ? { path: '/' } : true
  }
  if (to.path === '/forbidden') return true
  if (!auth.isAuthenticated) {
    return { path: '/login', query: to.fullPath ? { redirect: to.fullPath } : {} }
  }
  // 页面级权限：meta.perm 存在且无权限 → 403 页
  const perm = to.meta?.perm as string | undefined
  if (perm && !auth.can(perm)) {
    return { path: '/forbidden' }
  }
  return true
})

export default router
