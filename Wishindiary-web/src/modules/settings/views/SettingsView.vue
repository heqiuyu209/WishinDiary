<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useAuthStore } from '../../auth/store';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';
import {
  getNotificationSettingsApi,
  requestEmailCodeApi,
  saveNotificationPreferencesApi,
  unbindEmailApi,
  verifyEmailApi,
} from '../api';
import type {
  NotificationPreferences,
  NotificationSettings,
  StatusResponse,
} from '../../../types/api';
import type { AxiosResponse } from 'axios';

const auth = useAuthStore();
const state = ref<NotificationSettings | null>(null);
const email = ref('');
const code = ref('');
const message = ref('');
const error = ref('');
const busy = ref(false);
const loading = ref(true);
const cooldown = ref(0);
let cooldownTimer: number | undefined;
const preferences = reactive<NotificationPreferences>({
  enabled: false,
  lead_days: 2,
  timezone: 'Asia/Shanghai',
});
const timezones = computed(() => {
  const zones = [
    { value: 'Asia/Shanghai', label: '中国 · 北京时间' },
    { value: 'UTC', label: 'UTC' },
    { value: 'America/New_York', label: '美国 · 纽约' },
    { value: 'America/Los_Angeles', label: '美国 · 洛杉矶' },
    { value: 'Europe/London', label: '英国 · 伦敦' },
  ];
  if (!zones.some((z) => z.value === preferences.timezone))
    zones.push({ value: preferences.timezone, label: preferences.timezone });
  return zones;
});

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    state.value = (await getNotificationSettingsApi()).data;
    Object.assign(preferences, {
      enabled: state.value.enabled,
      lead_days: state.value.lead_days,
      timezone: state.value.timezone,
    });
    auth.currentEmail = state.value.email ?? '';
  } catch (err) {
    error.value = extractApiErrorMessage(err, '设置加载失败，请重试');
  } finally {
    loading.value = false;
  }
};

const perform = async (action: () => Promise<AxiosResponse<StatusResponse>>) => {
  if (busy.value) return false;
  busy.value = true;
  message.value = '';
  error.value = '';
  try {
    message.value = (await action()).data.message || '设置已更新';
    await load();
    return true;
  } catch (err) {
    error.value = extractApiErrorMessage(err, '操作失败，请重试');
    return false;
  } finally {
    busy.value = false;
  }
};

const sendCode = async () => {
  if (cooldown.value || !email.value.trim()) return;
  if (await perform(() => requestEmailCodeApi(email.value.trim()))) {
    cooldown.value = 60;
    window.clearInterval(cooldownTimer);
    cooldownTimer = window.setInterval(() => {
      cooldown.value -= 1;
      if (cooldown.value <= 0) window.clearInterval(cooldownTimer);
    }, 1000);
  }
};
const verify = async () => {
  if (!/^[0-9]{6}$/.test(code.value)) {
    error.value = '请输入 6 位验证码';
    return;
  }
  if (await perform(() => verifyEmailApi(code.value))) code.value = '';
};
const save = () => perform(() => saveNotificationPreferencesApi({ ...preferences }));
const unbind = () => {
  if (window.confirm('解绑邮箱并关闭提醒？')) void perform(unbindEmailApi);
};
onMounted(() => void load());
onUnmounted(() => window.clearInterval(cooldownTimer));
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-6 text-gray-800">
    <h1 class="text-2xl font-bold">邮箱与提醒设置</h1>
    <p class="text-sm leading-relaxed text-gray-500">
      验证邮箱后选择是否接收提醒；你可以随时关闭或解绑。
    </p>
    <p v-if="error" role="alert" class="rounded-xl bg-red-50 p-4 text-sm text-red-700">
      {{ error }}
    </p>
    <p v-if="message" role="status" class="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-700">
      {{ message }}
    </p>
    <p v-if="loading && !state" role="status">正在读取设置…</p>
    <button v-if="!loading && !state" class="rounded-xl border px-4 py-2" @click="load">
      重试
    </button>
    <template v-if="state">
      <p v-if="!state.mail_available" class="rounded-xl bg-amber-50 p-4 text-sm text-amber-700">
        邮箱服务尚未启用，暂时无法发送验证码或提醒。
      </p>
      <div class="space-y-4 rounded-2xl border border-gray-100 bg-white p-6">
        <h2 class="font-semibold">绑定邮箱</h2>
        <p class="break-all text-sm">
          当前邮箱：{{ state.email ?? '尚未绑定' }}
          <span v-if="state.email_verified" class="text-emerald-600">已验证</span>
        </p>
        <form class="space-y-3" @submit.prevent="sendCode">
          <label for="binding-email" class="block text-sm">邮箱地址</label>
          <input
            id="binding-email"
            v-model="email"
            type="email"
            required
            maxlength="254"
            autocomplete="email"
            placeholder="name@example.com"
            :disabled="busy"
            class="w-full rounded-xl border border-gray-200 px-3 py-3 text-sm"
          />
          <button
            type="submit"
            :disabled="busy || cooldown > 0 || !state.mail_available"
            class="rounded-xl bg-gray-800 px-4 py-3 text-sm text-white disabled:opacity-50"
          >
            {{ cooldown > 0 ? `${cooldown} 秒后可重发` : '发送验证码' }}
          </button>
        </form>
        <form
          v-if="state.pending_email"
          class="space-y-3 border-t border-gray-100 pt-4"
          @submit.prevent="verify"
        >
          <p class="break-all text-sm text-gray-500">
            验证码已发送到 {{ state.pending_email }}，10 分钟内有效。
          </p>
          <label for="email-code" class="block text-sm">6 位验证码</label>
          <input
            id="email-code"
            v-model="code"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            pattern="[0-9]{6}"
            required
            :disabled="busy"
            class="w-full rounded-xl border border-gray-200 px-3 py-3 text-sm"
          />
          <button
            type="submit"
            :disabled="busy"
            class="rounded-xl bg-rose-500 px-4 py-3 text-sm text-white disabled:opacity-50"
          >
            验证邮箱
          </button>
        </form>
        <button
          v-if="state.email || state.pending_email"
          :disabled="busy"
          class="text-sm text-gray-500 underline"
          @click="unbind"
        >
          解绑邮箱并关闭提醒
        </button>
      </div>
      <form
        class="space-y-4 rounded-2xl border border-gray-100 bg-white p-6"
        @submit.prevent="save"
      >
        <h2 class="font-semibold">预测日期提醒</h2>
        <label class="flex items-center gap-3 text-sm">
          <input
            v-model="preferences.enabled"
            type="checkbox"
            :disabled="busy || !state.email_verified || !state.mail_available"
          />
          接收邮箱提醒
        </label>
        <p v-if="!state.email_verified" class="text-sm text-gray-500">先验证邮箱，再开启提醒。</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <label for="reminder-lead" class="block text-sm">提前多久</label>
            <select
              id="reminder-lead"
              v-model="preferences.lead_days"
              :disabled="busy"
              class="w-full rounded-xl border border-gray-200 p-3 text-sm"
            >
              <option :value="1">提前 1 天</option>
              <option :value="2">提前 2 天（默认）</option>
              <option :value="3">提前 3 天</option>
            </select>
          </div>
          <div class="space-y-2">
            <label for="reminder-timezone" class="block text-sm">按哪个时区计算日期</label>
            <select
              id="reminder-timezone"
              v-model="preferences.timezone"
              :disabled="busy"
              class="w-full rounded-xl border border-gray-200 p-3 text-sm"
            >
              <option v-for="zone in timezones" :key="zone.value" :value="zone.value">
                {{ zone.label }}
              </option>
            </select>
          </div>
        </div>
        <p class="text-sm leading-relaxed text-gray-500">
          预测可能变化。邮件只提示登录查看，不包含健康日期或症状；同一周期只发送一次提醒。
        </p>
        <button
          type="submit"
          :disabled="busy"
          class="rounded-xl bg-gray-800 px-4 py-3 text-sm text-white disabled:opacity-50"
        >
          {{ busy ? '处理中…' : '保存提醒设置' }}
        </button>
      </form>
    </template>
  </section>
</template>
