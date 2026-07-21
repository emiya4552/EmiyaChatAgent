import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/home',
    },
    {
      path: '/home',
      name: 'home',
      component: () => import('../views/HomeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('../views/RegisterView.vue'),
    },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('../views/ForgotPasswordView.vue'),
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('../views/ResetPasswordView.vue'),
    },
    {
      path: '/chat',
      name: 'Chat',
      component: () => import('../views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/memories',
      name: 'memories',
      component: () => import('../views/MemoryPanelView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/mood',
      name: 'mood',
      component: () => import('../views/MoodDashboardView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/personas',
      name: 'personas',
      component: () => import('../views/PersonaManageView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/personas/create',
      name: 'persona-create',
      component: () => import('../views/PersonaFormView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/personas/:id/edit',
      name: 'persona-edit',
      component: () => import('../views/PersonaFormView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/personas/:id',
      name: 'persona-detail',
      component: () => import('../views/PersonaDetailView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/presets',
      name: 'presets',
      component: () => import('../views/PresetManageView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/presets/create',
      name: 'preset-create',
      component: () => import('../views/PresetFormView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/presets/:id/edit',
      name: 'preset-edit',
      component: () => import('../views/PresetFormView.vue'),
      meta: { requiresAuth: true },
    },
    // 正则预设管理
    {
      path: '/regex-presets',
      name: 'regex-presets',
      component: () => import('../views/RegexPresetManageView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/regex-presets/create',
      name: 'regex-preset-create',
      component: () => import('../views/RegexPresetFormView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/regex-presets/:id/edit',
      name: 'regex-preset-edit',
      component: () => import('../views/RegexPresetFormView.vue'),
      meta: { requiresAuth: true },
    },
    // Prompt 模板管理
    {
      path: '/templates',
      name: 'templates',
      component: () => import('../views/TemplateListView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/templates/new',
      name: 'template-create',
      component: () => import('../views/TemplateEditorView.vue'),
      meta: { requiresAuth: true },
    },
    {
      // 内置默认模板只读查看（无 :id 参数；TemplateEditorView 检测路由切换为只读）
      path: '/templates/default-view',
      name: 'template-default-view',
      component: () => import('../views/TemplateEditorView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/templates/:id',
      name: 'template-edit',
      component: () => import('../views/TemplateEditorView.vue'),
      meta: { requiresAuth: true },
    },
    // 账户设置（ADR-0009）
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { requiresAuth: true },
    },
    // 世界书管理
    {
      path: '/worldbooks',
      name: 'worldbooks',
      component: () => import('../views/WorldbookManageView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/worldbooks/:id/edit',
      name: 'worldbook-edit',
      component: () => import('../views/WorldbookEditorView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')

  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if ((to.path === '/login' || to.path === '/register') && token) {
    next('/home')
  } else {
    next()
  }
})

export default router
