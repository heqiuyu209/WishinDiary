// Vitest 全局 setup：为 jsdom 环境补齐浏览器 API 与通用 mock。
import { config } from '@vue/test-utils';
import { vi } from 'vitest';

// jsdom 未实现 matchMedia，部分组件（v-calendar 等）会用到。
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// jsdom 未实现 ResizeObserver。
if (!('ResizeObserver' in window)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

config.global.stubs = {
  transition: false,
  'transition-group': false,
};
