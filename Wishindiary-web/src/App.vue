<script setup>
// App.vue 现在只是一个纯粹的根路由出口，什么逻辑都不需要写了！
</script>

<template>
  <div
    class="app-shell min-h-screen overflow-x-hidden text-slate-800 font-sans selection:bg-rose-200"
  >
    <div class="app-ambient" aria-hidden="true"></div>
    <!-- 路由匹配到的页面会在这里渲染 -->
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" class="relative z-10" />
      </transition>
    </router-view>
  </div>
</template>

<style>
.app-shell {
  position: relative;
  isolation: isolate;
  background: #fdfdfe;
}

.app-ambient {
  position: fixed;
  z-index: 0;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 8% 8%, rgb(251 207 232 / 0.34), transparent 28rem),
    radial-gradient(circle at 92% 18%, rgb(221 214 254 / 0.34), transparent 30rem),
    radial-gradient(circle at 50% 100%, rgb(254 205 211 / 0.28), transparent 34rem), #fdfdfe;
  animation: ambient-drift 18s ease-in-out infinite alternate;
}

@keyframes ambient-drift {
  from {
    transform: scale(1) translate3d(0, 0, 0);
  }
  to {
    transform: scale(1.05) translate3d(1.5%, -1%, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .app-ambient {
    animation: none;
  }
}

/* 全局基础样式保留 */
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #e5e7eb;
  border-radius: 10px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background-color: #d1d5db;
}

/* 页面切换动画 */
.fade-enter-active,
.fade-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(5px);
}
</style>
