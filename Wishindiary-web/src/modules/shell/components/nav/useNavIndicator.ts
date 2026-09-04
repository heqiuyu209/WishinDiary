import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import type { CSSProperties, ComponentPublicInstance, Ref } from 'vue';

/**
 * 滑动指示器定位逻辑：测量激活按钮相对容器的偏移，
 * 通过 translateX 驱动平滑滑动动画（GitHub 风格导航）。
 */
export function useNavIndicator(
  items: Ref<{ name: string }[]>,
  activeName: Ref<string>,
  containerRef: Ref<HTMLElement | null>,
  buttonRefs: Ref<(HTMLElement | null)[]>,
) {
  const layoutTick = ref(0);

  const activeIndex = computed(() =>
    Math.max(0, items.value.findIndex((item) => item.name === activeName.value)),
  );

  const indicatorStyle = computed<CSSProperties>(() => {
    void layoutTick.value;
    const btn = buttonRefs.value[activeIndex.value];
    const container = containerRef.value;
    if (!btn || !container) {
      return { opacity: 0 };
    }
    const btnRect = btn.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    if (!btnRect.width) {
      return { opacity: 0 };
    }
    return {
      width: `${btnRect.width}px`,
      transform: `translateX(${btnRect.left - containerRect.left}px)`,
      left: 0,
      opacity: 1,
    };
  });

  const refreshLayout = () => {
    layoutTick.value += 1;
  };

  onMounted(() => {
    refreshLayout();
    window.addEventListener('resize', refreshLayout, { passive: true });
  });

  onBeforeUnmount(() => {
    window.removeEventListener('resize', refreshLayout);
  });

  const setBtn = (index: number) => (el: Element | ComponentPublicInstance | null) => {
    if (el instanceof HTMLElement) {
      buttonRefs.value[index] = el;
    }
  };

  return { indicatorStyle, setBtn };
}
