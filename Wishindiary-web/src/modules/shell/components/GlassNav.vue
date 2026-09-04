<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getPredictionApi } from '../../dashboard/api';
import { logoutApi } from '../../auth/api';
import { useAuthStore } from '../../auth/store';
import type { PredictionResponseData } from '../../../types/api';
import type { NavItem } from '../types';
import NavBrand from './nav/NavBrand.vue';
import NavigationTabs from './nav/NavigationTabs.vue';
import MobileNavTabs from './nav/MobileNavTabs.vue';
import CycleBadge from './nav/CycleBadge.vue';
import ProfileMenu from './nav/ProfileMenu.vue';
import LogoutButton from './nav/LogoutButton.vue';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const navShellRef = ref<HTMLElement | null>(null);

const currentViewName = computed(() => String(route.name ?? ''));

const navItems: NavItem[] = [
  { name: 'Calendar', label: '打卡与预测', icon: '📍' },
  { name: 'Dashboard', label: '数据看板', icon: '📊' },
  { name: 'Report', label: '深度报告', icon: '📑' },
];

// 玻璃态滚动状态：0=顶部，1=滚动后
const scrollY = ref(0);
let scrollRafId = 0;
let navResizeObserver: ResizeObserver | null = null;
const navHeightVarName = '--glass-nav-height';

const onScroll = () => {
  if (scrollRafId) return;
  scrollRafId = window.requestAnimationFrame(() => {
    scrollY.value = window.scrollY || 0;
    scrollRafId = 0;
  });
};

const scrollProgress = computed(() => {
  const progress = (scrollY.value - 8) / 120;
  return Math.min(1, Math.max(0, progress));
});

const isCompactNav = computed(() => scrollProgress.value > 0.18);

const navSurfaceMetrics = computed(() => {
  const progress = scrollProgress.value;
  // 顶部保持通透，滚动后增加磨砂不透明度；这样缩小导航时仍有玻璃层次。
  const alpha = 0.24 + progress * 0.46;
  const paddingY = 16 - progress * 5;
  const blur = 24 + progress * 12;
  const saturate = 155 + progress * 45;
  const radius = 40 - progress * 12;

  return {
    backgroundColor: `rgba(255, 255, 255, ${alpha})`,
    backgroundImage: `linear-gradient(180deg, rgba(255,255,255,${Math.min(0.94, alpha + 0.16)}) 0%, rgba(255,255,255,${Math.max(0.08, alpha - 0.12)}) 100%)`,
    borderColor: `rgba(255, 255, 255, ${0.72 - progress * 0.28})`,
    boxShadow:
      progress > 0.25
        ? '0 14px 32px -22px rgba(15, 23, 42, 0.18)'
        : '0 26px 70px -28px rgba(244, 63, 94, 0.18)',
    paddingTop: `${paddingY}px`,
    paddingBottom: `${paddingY}px`,
    borderRadius: `${radius}px`,
    backdropFilter: `blur(${blur}px) saturate(${saturate}%)`,
    WebkitBackdropFilter: `blur(${blur}px) saturate(${saturate}%)`,
  };
});

const syncNavHeight = () => {
  const element = navShellRef.value;
  if (!element) return;

  const nextHeight = Math.ceil(element.getBoundingClientRect().height);
  if (!nextHeight) return;

  const rootStyle = document.documentElement.style;
  const currentHeight = Number.parseFloat(rootStyle.getPropertyValue(navHeightVarName)) || 0;
  if (Math.abs(nextHeight - currentHeight) > 1) {
    rootStyle.setProperty(navHeightVarName, `${nextHeight}px`);
  }
};

const profileInitial = computed(() => {
  const name = authStore.currentUsername?.trim();
  if (!name) return 'W';
  return name.slice(0, 1).toUpperCase();
});

const profileEmail = computed(() => authStore.currentEmail || '邮箱注册待开放');

// 周期状态胶囊：距预测经期还有几天
const prediction = ref<PredictionResponseData | null>(null);
const daysUntil = ref<number | null>(null);
const fetchPrediction = async () => {
  try {
    const res = await getPredictionApi();
    if (res.data.status === 'success' && res.data.prediction) {
      prediction.value = res.data.prediction;
      const next = new Date(`${res.data.prediction.next_period_start}T00:00:00`);
      const now = new Date();
      now.setHours(0, 0, 0, 0);
      const diff = Math.round((next.getTime() - now.getTime()) / 86400000);
      daysUntil.value = diff;
    }
  } catch {
    prediction.value = null;
    daysUntil.value = null;
  }
};

const handleLogout = async () => {
  try {
    await logoutApi();
  } catch {
    // 本地登出仍继续执行
  }
  authStore.logout();
  void router.push('/login');
};

const navigateTo = (name: string) => {
  void router.push({ name });
};

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  syncNavHeight();
  void fetchPrediction();

  if (typeof ResizeObserver !== 'undefined' && navShellRef.value) {
    navResizeObserver = new ResizeObserver(() => {
      syncNavHeight();
    });
    navResizeObserver.observe(navShellRef.value);
  } else {
    window.addEventListener('resize', syncNavHeight, { passive: true });
  }
});

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll);
  window.removeEventListener('resize', syncNavHeight);
  if (navResizeObserver) {
    navResizeObserver.disconnect();
    navResizeObserver = null;
  }
  if (scrollRafId) {
    window.cancelAnimationFrame(scrollRafId);
    scrollRafId = 0;
  }
});
</script>

<template>
  <div class="fixed inset-x-0 top-0 z-50 pointer-events-none px-2 sm:px-3 lg:px-4 pt-2 sm:pt-3">
    <nav
      ref="navShellRef"
      class="pointer-events-auto mx-auto flex w-full max-w-7xl items-center justify-between gap-2 sm:gap-4 border transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] will-change-[transform,background-color,box-shadow,padding,border-radius,backdrop-filter]"
      :style="navSurfaceMetrics"
    >
      <!-- 移动端布局（<md） -->
      <div class="flex flex-col gap-2 md:hidden px-3 py-3">
        <div class="flex items-center justify-between gap-2">
          <NavBrand :compact="isCompactNav" @select="navigateTo('Calendar')" />

          <div class="flex items-center gap-1.5 shrink-0">
            <CycleBadge
              v-if="daysUntil !== null"
              :days-until="daysUntil"
              display-class="hidden sm:inline-flex"
            />
            <ProfileMenu
              :username="authStore.currentUsername"
              :email="profileEmail"
              :initial="profileInitial"
            />
            <LogoutButton @logout="handleLogout" />
          </div>
        </div>

        <MobileNavTabs :items="navItems" :active-name="currentViewName" @select="navigateTo" />
      </div>

      <!-- 桌面布局（md+） -->
      <div
        class="hidden md:flex w-full items-center justify-between gap-2 sm:gap-4 px-3 sm:px-4 lg:px-6 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
      >
        <NavBrand :compact="isCompactNav" @select="navigateTo('Calendar')" />

        <NavigationTabs :items="navItems" :active-name="currentViewName" @select="navigateTo" />

        <!-- 右侧：周期状态胶囊 + 个人资料 + 退出 -->
        <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <CycleBadge
            v-if="daysUntil !== null && !isCompactNav"
            :days-until="daysUntil"
            display-class="hidden xl:inline-flex"
          />
          <ProfileMenu
            :username="authStore.currentUsername"
            :email="profileEmail"
            :initial="profileInitial"
          />
          <LogoutButton @logout="handleLogout" />
        </div>
      </div>
    </nav>
  </div>
</template>
