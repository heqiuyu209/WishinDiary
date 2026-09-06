<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../store';
import { getSessionApi, loginApi, registerApi } from '../api';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';
import { formatDate, today } from '../../../shared/utils/date';

const router = useRouter();
const authStore = useAuthStore();

const isRegistering = ref(false);
const usernameInput = ref('');
const passwordInput = ref('');
const message = ref('');
const errorMsg = ref('');
const isSubmitting = ref(false);

// --- 注册时可选补录最近经期开始日期（加速个性化预测）---
const showBackfill = ref(false);
const periodDates = ref<string[]>(['', '']);
const todayStr = formatDate(today());
const MAX_BACKFILL_DATES = 4;

const toggleBackfill = () => {
  showBackfill.value = !showBackfill.value;
  if (showBackfill.value && periodDates.value.length === 0) {
    periodDates.value = ['', ''];
  }
};

const addPeriodDate = () => {
  if (periodDates.value.length < MAX_BACKFILL_DATES) periodDates.value.push('');
};

const removePeriodDate = (index: number) => {
  periodDates.value.splice(index, 1);
};

/** 收集补录日期：去空、去重、升序、剔除未来日期；不足 1 个时返回空数组。 */
const collectBackfillDates = (): string[] => {
  const cleaned = periodDates.value.map((d) => d.trim()).filter(Boolean);
  const pastOrToday = cleaned.filter((d) => d <= todayStr);
  return [...new Set(pastOrToday)].sort();
};

const validateInput = (): string => {
  const username = usernameInput.value;
  const password = passwordInput.value;
  if (!username) return '请输入账号';
  if (isRegistering.value && (username.length < 3 || username.length > 50)) {
    return '账号需要 3–50 个字符';
  }
  if (isRegistering.value && !/^[A-Za-z0-9_.-]+$/.test(username)) {
    return '账号只能包含英文字母、数字、下划线（_）、点（.）和短横线（-）';
  }
  if (!password) return '请输入密码';
  if (isRegistering.value && [...password].length < 8) return '密码至少需要 8 个字符';
  if (isRegistering.value && new TextEncoder().encode(password).length > 72) {
    return '密码过长：最多 72 个 UTF-8 字节，中文和表情会占用多个字节';
  }
  if (isRegistering.value && showBackfill.value) {
    const backfill = collectBackfillDates();
    if (backfill.length === 1) return '补录经期开始日期至少需要 2 个（才能构成完整周期），无需补录请收起该步骤';
  }
  return '';
};

const handleSubmit = async () => {
  if (isSubmitting.value) return;
  message.value = '';
  errorMsg.value = validateInput();
  if (errorMsg.value) return;
  isSubmitting.value = true;
  try {
    if (isRegistering.value) await handleRegister();
    else await handleLogin();
  } finally {
    isSubmitting.value = false;
  }
};

const handleLogin = async () => {
  try {
    await loginApi({
      username: usernameInput.value,
      password: passwordInput.value,
    });
    // 确认浏览器能携带 Cookie，再进入受保护页面。
    try {
      const session = await getSessionApi();
      authStore.login(session.data.username ?? usernameInput.value);
    } catch {
      authStore.logout();
      errorMsg.value =
        window.location.protocol === 'http:'
          ? '登录会话未能建立。当前使用 HTTP，请改用 HTTPS，或联系管理员检查 HTTP 访问配置。'
          : '登录会话未能建立，请确认浏览器允许本站 Cookie，然后重试。';
      return;
    }
    await router.push('/calendar');
  } catch (err) {
    errorMsg.value = extractApiErrorMessage(err, '登录失败');
  }
};

const handleRegister = async () => {
  try {
    const backfillDates = collectBackfillDates();
    const res = await registerApi({
      username: usernameInput.value,
      password: passwordInput.value,
      ...(backfillDates.length ? { period_start_dates: backfillDates } : {}),
    });
    const recorded = res.data?.period_dates_recorded ?? 0;
    message.value =
      recorded > 0
        ? `注册成功！已为您补录 ${recorded} 次经期记录，可直接登录享受个性化预测。`
        : '注册成功，请直接登录！';
    isRegistering.value = false;
    showBackfill.value = false;
    periodDates.value = ['', ''];
    errorMsg.value = '';
  } catch (err) {
    errorMsg.value = extractApiErrorMessage(err, '注册失败');
  }
};
</script>

<template>
  <div class="flex flex-col items-center py-12 px-4 w-full">
    <div class="mb-10 text-center space-y-2 relative">
      <div
        class="inline-flex items-center justify-center p-3 bg-white rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100 mb-2"
      >
        <span class="text-3xl">🌸</span>
      </div>
      <h1
        class="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-rose-500 to-pink-500 bg-clip-text text-transparent"
      >
        WishinDiary
      </h1>
      <p class="text-sm text-gray-400 font-medium tracking-wide">
        AI-Powered Female Health Intelligence
      </p>
    </div>

    <form
      novalidate
      @submit.prevent="handleSubmit"
      class="bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.06)] border border-gray-100/60 p-8 w-full max-w-md space-y-7 relative overflow-hidden"
    >
      <div
        class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-rose-400 to-pink-500"
      ></div>

      <div class="text-center space-y-1.5">
        <h2 class="text-2xl font-bold text-gray-800">
          {{ isRegistering ? '创建新账户' : '欢迎回来' }}
        </h2>
        <p class="text-xs text-gray-400">
          {{ isRegistering ? '加入智能健康追踪' : '请输入您的凭证以继续' }}
        </p>
      </div>

      <div class="space-y-4">
        <div class="space-y-1.5">
          <label
            for="username"
            class="text-[11px] font-bold text-gray-500 uppercase tracking-widest"
          >
            账号
          </label>
          <input
            id="username"
            v-model="usernameInput"
            type="text"
            :minlength="isRegistering ? 3 : 1"
            maxlength="50"
            :pattern="isRegistering ? '[A-Za-z0-9_.-]+' : undefined"
            :aria-describedby="isRegistering ? 'username-hint' : undefined"
            required
            autocomplete="username"
            class="w-full px-4 py-3 bg-gray-50/50 border border-gray-200 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-rose-100 focus:border-rose-400 outline-none transition-all duration-300"
            placeholder="Username"
          />
          <p v-if="isRegistering" id="username-hint" class="text-xs text-gray-500">
            3–50 个字符，可使用英文字母、数字、下划线（_）、点（.）和短横线（-）。
          </p>
        </div>
        <div class="space-y-1.5">
          <label
            for="password"
            class="text-[11px] font-bold text-gray-500 uppercase tracking-widest"
          >
            密码
          </label>
          <input
            id="password"
            v-model="passwordInput"
            type="password"
            :minlength="isRegistering ? 8 : 1"
            maxlength="128"
            :autocomplete="isRegistering ? 'new-password' : 'current-password'"
            :aria-describedby="isRegistering ? 'password-hint' : undefined"
            required
            class="w-full px-4 py-3 bg-gray-50/50 border border-gray-200 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-rose-100 focus:border-rose-400 outline-none transition-all duration-300"
            placeholder="••••••••"
          />
          <p v-if="isRegistering" id="password-hint" class="text-xs text-gray-500">
            至少 8 个字符，最多 72 个 UTF-8 字节（纯英文、数字或半角符号最多 72 个字符）。
          </p>
        </div>
      </div>

      <div v-if="isRegistering" class="space-y-3">
        <button
          id="backfill-toggle"
          type="button"
          @click="toggleBackfill"
          class="w-full flex items-center justify-between px-4 py-3 bg-rose-50/60 border border-rose-100 rounded-2xl text-sm text-rose-600 font-medium hover:bg-rose-50 transition-colors"
        >
          <span>🌸 补录最近经期日期（可选，加速个性化预测）</span>
          <span class="text-rose-400 text-xs">{{ showBackfill ? '收起' : '展开' }}</span>
        </button>

        <div v-if="showBackfill" id="backfill-panel" class="space-y-3">
          <p class="text-xs text-gray-500 leading-relaxed">
            可选：补录最近 2~4 次经期开始日期后，注册即可立即获得基础统计量与预测区间，无需等待积累 4 个完整周期。日期不晚于今天、相邻间隔 15~60 天。
          </p>
          <div
            v-for="(_slot, index) in periodDates"
            :key="index"
            class="flex items-center gap-2"
          >
            <label :for="`backfill-date-${index}`" class="sr-only">
              第 {{ index + 1 }} 个经期开始日期
            </label>
            <input
              :id="`backfill-date-${index}`"
              v-model="periodDates[index]"
              type="date"
              :max="todayStr"
              class="w-full px-3 py-2.5 bg-gray-50/50 border border-gray-200 rounded-xl text-sm focus:bg-white focus:ring-2 focus:ring-rose-100 focus:border-rose-400 outline-none transition-all duration-300"
            />
            <button
              type="button"
              :disabled="periodDates.length <= 2"
              :aria-label="`移除第 ${index + 1} 个日期`"
              @click="removePeriodDate(index)"
              class="shrink-0 px-2.5 py-2.5 text-xs text-gray-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              移除
            </button>
          </div>
          <button
            v-if="periodDates.length < MAX_BACKFILL_DATES"
            id="backfill-add"
            type="button"
            @click="addPeriodDate"
            class="w-full text-xs text-rose-500 hover:text-rose-600 font-medium transition-colors"
          >
            + 添加一次经期开始日期
          </button>
        </div>
      </div>

      <div
        v-if="message"
        class="p-3 bg-emerald-50 border border-emerald-100 text-emerald-600 rounded-xl text-xs font-medium text-center"
      >
        {{ message }}
      </div>
      <div
        v-if="errorMsg"
        role="alert"
        class="p-3 bg-red-50 border border-red-100 text-red-600 rounded-xl text-xs font-medium text-center"
      >
        {{ errorMsg }}
      </div>

      <div class="space-y-4 pt-2">
        <button
          v-if="!isRegistering"
          type="submit"
          :disabled="isSubmitting"
          class="w-full bg-gradient-to-r from-rose-500 to-pink-500 hover:from-rose-600 hover:to-pink-600 text-white font-bold py-3.5 rounded-2xl shadow-md transition-all active:scale-[0.98]"
        >
          进入系统
        </button>
        <button
          v-else
          type="submit"
          :disabled="isSubmitting"
          class="w-full bg-gradient-to-r from-rose-500 to-pink-500 hover:from-rose-600 hover:to-pink-600 text-white font-bold py-3.5 rounded-2xl shadow-md transition-all active:scale-[0.98]"
        >
          确认注册
        </button>

        <button
          type="button"
          :disabled="isSubmitting"
          @click="((isRegistering = !isRegistering), (errorMsg = ''), (message = ''))"
          class="w-full text-gray-400 hover:text-gray-600 text-xs font-medium transition-colors"
        >
          {{ isRegistering ? '已有账号？返回登录' : '没有账号？点击注册' }}
        </button>
      </div>
    </form>
  </div>
</template>
