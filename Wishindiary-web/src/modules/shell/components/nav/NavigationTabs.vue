<script setup lang="ts">
import { computed, ref } from 'vue';
import type { NavItem } from '../../types';
import { useNavIndicator } from './useNavIndicator';

const props = defineProps<{ items: NavItem[]; activeName: string }>();
const emit = defineEmits<{ select: [name: string] }>();

const containerRef = ref<HTMLElement | null>(null);
const buttonRefs = ref<(HTMLElement | null)[]>([]);

const { indicatorStyle, setBtn } = useNavIndicator(
  computed(() => props.items),
  computed(() => props.activeName),
  containerRef,
  buttonRefs,
);
</script>

<template>
  <div
    ref="containerRef"
    class="relative flex bg-white/32 backdrop-blur-sm rounded-full p-1 border border-white/50 shadow-[0_8px_25px_-18px_rgba(15,23,42,0.2)] transition-all duration-300"
  >
    <!-- 滑动指示器：随激活项平滑滑动的白色胶囊 -->
    <span
      aria-hidden="true"
      class="pointer-events-none absolute top-1 bottom-1 left-0 rounded-full bg-white shadow-[0_4px_14px_-5px_rgba(15,23,42,0.35)] transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] will-change-[transform,width]"
      :style="indicatorStyle"
    ></span>
    <button
      v-for="(item, index) in items"
      :key="item.name"
      :ref="setBtn(index)"
      type="button"
      @click="emit('select', item.name)"
      :class="
        activeName === item.name
          ? 'text-gray-800'
          : 'text-gray-500 hover:text-gray-800 hover:bg-white/60'
      "
      class="relative z-10 flex items-center gap-1.5 px-2.5 sm:px-4 py-2 rounded-full text-xs font-bold transition-colors duration-300"
    >
      <span class="text-sm">{{ item.icon }}</span>
      <span class="hidden lg:inline">{{ item.label }}</span>
    </button>
  </div>
</template>
