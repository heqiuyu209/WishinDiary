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
    class="relative grid grid-cols-3 gap-1.5 rounded-[24px] border border-white/55 bg-white/24 p-1.5 shadow-[0_8px_25px_-18px_rgba(15,23,42,0.2)] backdrop-blur-sm"
  >
    <!-- 滑动指示器：随激活项平滑滑动的白色圆角块 -->
    <span
      aria-hidden="true"
      class="pointer-events-none absolute top-1.5 bottom-1.5 left-0 rounded-[18px] bg-white shadow-[0_4px_14px_-5px_rgba(15,23,42,0.35)] transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] will-change-[transform,width]"
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
          : 'text-gray-500 hover:text-gray-800 hover:bg-white/55'
      "
      class="relative z-10 flex min-h-12 flex-col items-center justify-center gap-1 rounded-[18px] px-2 py-2 text-[11px] font-bold transition-colors duration-300"
    >
      <span class="text-sm">{{ item.icon }}</span>
      <span class="hidden sm:block leading-none">{{ item.label }}</span>
    </button>
  </div>
</template>
