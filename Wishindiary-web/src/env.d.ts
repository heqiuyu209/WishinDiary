/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const component: DefineComponent<Record<string, never>, Record<string, never>, any>;
  export default component;
}

// v-calendar 3.x 未发布官方类型，使用最小声明。
declare module 'v-calendar' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export const DatePicker: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export const Calendar: any;
}
