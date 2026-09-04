import { defineConfig, devices } from '@playwright/test';

/**
 * E2E 测试配置。
 *
 * 本地运行需先启动后端 API：
 *   - 后端（含 MySQL）见仓库根目录 wishindiary-api，需先执行迁移并启动 uvicorn。
 *   - 前端由 webServer 自动以 preview 模式启动（需先 `npm run build`）。
 *
 * CI 中由 .github/workflows/ci.yml 的 frontend-e2e job 负责准备 MySQL 与后端，并注入
 * PLAYWRIGHT_BASE_URL 指向后端已就绪的前端地址（默认 http://localhost:4173）。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:4173',
    trace: 'retain-on-first-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run preview -- --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
