import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '../modules/auth/store';

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../modules/auth/views/LoginView.vue'),
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('../modules/shell/views/MainLayout.vue'),
    redirect: '/calendar',
    children: [
      {
        path: 'calendar',
        name: 'Calendar',
        component: () => import('../modules/calendar/views/CalendarView.vue'),
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../modules/dashboard/views/DashboardView.vue'),
      },
      {
        path: 'report',
        name: 'Report',
        component: () => import('../modules/report/views/ReportView.vue'),
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 保持 API 认证失效与前端导航同步，同时避免 HTTP 客户端在启动阶段反向依赖
// 路由（否则会产生模块循环依赖）。
if (typeof window !== 'undefined') {
  window.addEventListener('wishindiary:session-expired', () => {
    const authStore = useAuthStore();
    authStore.logout();
    if (router.currentRoute.value.name !== 'Login') {
      void router.push({ name: 'Login' });
    }
  });
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore();

  // 公开登录页无需 session 探活：除避免多余请求外，也防止匿名访问被记为两次 401。
  if (to.name === 'Login') {
    return authStore.isLoggedIn ? { name: 'Calendar' } : true;
  }

  const hasValidSession = await authStore.refreshSession();

  if (!hasValidSession) {
    return { name: 'Login' };
  }
  return true;
});

export default router;
