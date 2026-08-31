import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/authStore';

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue')
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('../views/MainLayout.vue'),
    redirect: '/calendar', // 默认跳转到日历
    children: [
      {
        path: 'calendar',
        name: 'Calendar',
        component: () => import('../views/CalendarView.vue')
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/DashboardView.vue')
      },
      {
        path: 'report',
        name: 'Report',
        component: () => import('../views/ReportView.vue')
      }
    ]
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

// Keep API authentication failures and client-side navigation in sync without
// making the HTTP client depend on the router (which would create a module
// cycle during application startup).
if (typeof window !== 'undefined') {
  window.addEventListener('wishindiary:session-expired', () => {
    const authStore = useAuthStore();
    authStore.logout();
    if (router.currentRoute.value.name !== 'Login') {
      router.push({ name: 'Login' });
    }
  });
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore();

  // A public login page does not need a session probe. Apart from avoiding an
  // unnecessary request, this prevents a normal anonymous visit from being
  // logged as two consecutive 401 responses.
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
