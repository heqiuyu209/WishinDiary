<script setup>
import GlassNav from '../components/GlassNav.vue';

const layoutStyle = {
  paddingTop: 'calc(var(--glass-nav-height, 6rem) + 1rem)',
};
</script>

<template>
  <div class="min-h-screen flex flex-col items-center w-full" :style="layoutStyle">
    <!-- 玻璃导航栏（fixed，滚动时收缩） -->
    <GlassNav class="w-full" />

    <!-- 路由匹配到的子页面 -->
    <div class="w-full max-w-6xl px-4 sm:px-6 lg:px-8 py-8">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
  </div>
</template>
