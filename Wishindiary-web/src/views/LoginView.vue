<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/authStore';
import { loginApi, registerApi } from '../api/authApi';

const router = useRouter();
const authStore = useAuthStore();

const isRegistering = ref(false);
const usernameInput = ref('');
const passwordInput = ref('');
const message = ref('');
const errorMsg = ref('');

const formatApiError = (err, fallback) => {
  const detail = err.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map(item => item.msg || '输入格式无效').join('；');
  }
  return detail || fallback;
};

const handleLogin = async () => {
  try {
    const res = await loginApi({ username: usernameInput.value, password: passwordInput.value });
    authStore.login(usernameInput.value);
    router.push('/calendar');
  } catch (err) {
    errorMsg.value = formatApiError(err, '登录失败');
  }
};

const handleRegister = async () => {
  try {
    await registerApi({ username: usernameInput.value, password: passwordInput.value });
    message.value = '注册成功，请直接登录！';
    isRegistering.value = false;
    errorMsg.value = '';
  } catch (err) {
    errorMsg.value = formatApiError(err, '注册失败');
  }
};
</script>

<template>
  <div class="flex flex-col items-center py-12 px-4 w-full">
    <div class="mb-10 text-center space-y-2 relative">
      <div class="inline-flex items-center justify-center p-3 bg-white rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100 mb-2"><span class="text-3xl">🌸</span></div>
      <h1 class="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-rose-500 to-pink-500 bg-clip-text text-transparent">WishinDiary</h1>
      <p class="text-sm text-gray-400 font-medium tracking-wide">AI-Powered Female Health Intelligence</p>
    </div>

    <div class="bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.06)] border border-gray-100/60 p-8 w-full max-w-md space-y-7 relative overflow-hidden">
      <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-rose-400 to-pink-500"></div>

      <div class="text-center space-y-1.5">
        <h2 class="text-2xl font-bold text-gray-800">{{ isRegistering ? '创建新账户' : '欢迎回来' }}</h2>
        <p class="text-xs text-gray-400">{{ isRegistering ? '加入智能健康追踪' : '请输入您的凭证以继续' }}</p>
      </div>

      <div class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-[11px] font-bold text-gray-500 uppercase tracking-widest">账号</label>
           <input v-model="usernameInput" type="text" minlength="3" maxlength="50" pattern="[A-Za-z0-9_.-]+" autocomplete="username" class="w-full px-4 py-3 bg-gray-50/50 border border-gray-200 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-rose-100 focus:border-rose-400 outline-none transition-all duration-300" placeholder="Username" />
        </div>
        <div class="space-y-1.5">
          <label class="text-[11px] font-bold text-gray-500 uppercase tracking-widest">密码</label>
           <input v-model="passwordInput" type="password" :minlength="isRegistering ? 8 : 1" maxlength="128" :autocomplete="isRegistering ? 'new-password' : 'current-password'" @keyup.enter="isRegistering ? handleRegister() : handleLogin()" class="w-full px-4 py-3 bg-gray-50/50 border border-gray-200 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-rose-100 focus:border-rose-400 outline-none transition-all duration-300" placeholder="••••••••" />
        </div>
      </div>

      <div v-if="message" class="p-3 bg-emerald-50 border border-emerald-100 text-emerald-600 rounded-xl text-xs font-medium text-center">{{ message }}</div>
      <div v-if="errorMsg" class="p-3 bg-red-50 border border-red-100 text-red-600 rounded-xl text-xs font-medium text-center">{{ errorMsg }}</div>

      <div class="space-y-4 pt-2">
        <button v-if="!isRegistering" @click="handleLogin" class="w-full bg-gradient-to-r from-rose-500 to-pink-500 hover:from-rose-600 hover:to-pink-600 text-white font-bold py-3.5 rounded-2xl shadow-md transition-all active:scale-[0.98]">进入系统</button>
        <button v-else @click="handleRegister" class="w-full bg-gradient-to-r from-rose-500 to-pink-500 hover:from-rose-600 hover:to-pink-600 text-white font-bold py-3.5 rounded-2xl shadow-md transition-all active:scale-[0.98]">确认注册</button>

        <button @click="isRegistering = !isRegistering; errorMsg='';" class="w-full text-gray-400 hover:text-gray-600 text-xs font-medium transition-colors">
          {{ isRegistering ? '已有账号？返回登录' : '没有账号？点击注册' }}
        </button>
      </div>
    </div>
  </div>
</template>
