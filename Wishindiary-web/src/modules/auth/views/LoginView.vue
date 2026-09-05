<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../store';
import { getSessionApi, loginApi, registerApi } from '../api';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';

const router = useRouter();
const authStore = useAuthStore();

const isRegistering = ref(false);
const usernameInput = ref('');
const passwordInput = ref('');
const message = ref('');
const errorMsg = ref('');
const isSubmitting = ref(false);

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
    await registerApi({
      username: usernameInput.value,
      password: passwordInput.value,
    });
    message.value = '注册成功，请直接登录！';
    isRegistering.value = false;
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
