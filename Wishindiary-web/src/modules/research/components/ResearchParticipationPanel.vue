<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import type { AxiosResponse } from 'axios';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';
import type { StatusResponse } from '../../../types/api';
import {
  decideParticipationApi,
  getParticipationApi,
  saveResearchBackgroundApi,
  type ParticipationState,
  type ResearchBackground,
} from '../participationApi';

const state = ref<ParticipationState | null>(null);
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const message = ref('');
const adult = ref(false);
const accepted = ref(false);
const background = reactive<ResearchBackground>({
  age_band: null,
  pregnancy: null,
  breastfeeding: null,
  hormonal_contraception: null,
  diagnosed_pcos: null,
  diagnosed_thyroid: null,
});
const flags: { key: Exclude<keyof ResearchBackground, 'age_band'>; label: string }[] = [
  { key: 'pregnancy', label: '目前是否妊娠' },
  { key: 'breastfeeding', label: '目前是否哺乳' },
  { key: 'hormonal_contraception', label: '目前是否使用激素避孕' },
  { key: 'diagnosed_pcos', label: '是否已被医生诊断为 PCOS' },
  { key: 'diagnosed_thyroid', label: '是否已被医生诊断为甲状腺疾病' },
];
const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    state.value = (await getParticipationApi()).data;
    Object.assign(background, state.value.background.fields);
    accepted.value = false;
    adult.value = false;
  } catch (err) {
    state.value = null;
    error.value = extractApiErrorMessage(err, '研究设置加载失败，请重试');
  } finally {
    loading.value = false;
  }
};
const perform = async (action: () => Promise<AxiosResponse<StatusResponse>>) => {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  message.value = '';
  try {
    message.value = (await action()).data.message ?? '研究设置已更新';
    await load();
  } catch (err) {
    error.value = extractApiErrorMessage(err, '研究设置保存失败，请重试');
  } finally {
    busy.value = false;
  }
};
const join = () => {
  if (!state.value || !adult.value || !accepted.value || background.age_band === 'under18') return;
  return perform(() =>
    decideParticipationApi({
      participate: true,
      policy_version: state.value!.policy.version,
      adult_confirmed: true,
    }),
  );
};
const withdraw = () => perform(() => decideParticipationApi({ participate: false }));
const save = () => perform(() => saveResearchBackgroundApi({ ...background }));
onMounted(() => void load());
</script>

<template>
  <section
    aria-labelledby="research-settings-title"
    class="space-y-4 rounded-2xl border border-rose-100 bg-white p-5 sm:p-6"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 id="research-settings-title" class="font-semibold">自愿研究与医学背景</h2>
      <span v-if="state" class="rounded-full bg-rose-50 px-3 py-1 text-sm text-rose-700">
        {{ state.participating ? '已自愿参加' : '未参加研究' }}
      </span>
    </div>
    <p class="text-sm leading-relaxed text-gray-500">
      研究设置独立于邮箱提醒。医学背景可以跳过，只用于研究分组，不自动调整预测日期。
    </p>
    <p v-if="error" role="alert" class="rounded-xl bg-red-50 p-3 text-sm text-red-700">
      {{ error }}
    </p>
    <p v-if="message" role="status" class="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">
      {{ message }}
    </p>
    <p v-if="loading" role="status" class="text-sm">正在读取研究设置…</p>
    <button v-if="!loading && !state" class="rounded-xl border px-4 py-2 text-sm" @click="load">
      重试研究设置
    </button>
    <template v-if="state">
      <div class="space-y-3 rounded-xl bg-gray-50 p-4">
        <h3 class="text-sm font-semibold">{{ state.policy.title }}</h3>
        <ul class="list-disc space-y-2 pl-5 text-sm leading-relaxed text-gray-600">
          <li v-for="statement in state.policy.statements" :key="statement">{{ statement }}</li>
        </ul>
        <button
          v-if="state.participating"
          :disabled="busy || loading"
          class="rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm disabled:opacity-50"
          @click="withdraw"
        >
          撤回研究授权
        </button>
        <form v-else class="space-y-3 border-t border-gray-200 pt-4" @submit.prevent="join">
          <label class="flex items-start gap-3 text-sm">
            <input
              id="research-adult"
              v-model="adult"
              type="checkbox"
              :disabled="busy || loading"
              class="mt-1"
            />
            我确认已满 18 岁
          </label>
          <label class="flex items-start gap-3 text-sm">
            <input
              id="research-accepted"
              v-model="accepted"
              type="checkbox"
              :disabled="busy || loading"
              class="mt-1"
            />
            我已阅读以上说明，自愿授权参加
          </label>
          <p v-if="background.age_band === 'under18'" class="text-sm text-amber-700">
            本阶段研究只面向成年人。
          </p>
          <button
            type="submit"
            :disabled="busy || loading || !adult || !accepted || background.age_band === 'under18'"
            class="rounded-xl bg-rose-500 px-4 py-3 text-sm text-white disabled:opacity-50"
          >
            自愿参加研究
          </button>
        </form>
      </div>
      <form class="space-y-4" @submit.prevent="save">
        <h3 class="text-sm font-semibold">可选医学背景</h3>
        <p class="text-sm leading-relaxed text-gray-500">
          按本人已知情况填写；不确定可保留“未填写 / 不确定”。不需要自行判断疾病。保存未满 18
          岁会撤回本阶段研究授权。
        </p>
        <fieldset :disabled="busy || loading" class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <label for="research-age" class="block text-sm">年龄段</label>
            <select
              id="research-age"
              v-model="background.age_band"
              class="w-full rounded-xl border border-gray-200 p-3 text-sm"
            >
              <option :value="null">未填写</option>
              <option value="under18">未满 18 岁</option>
              <option value="18_24">18–24 岁</option>
              <option value="25_34">25–34 岁</option>
              <option value="35_44">35–44 岁</option>
              <option value="45_plus">45 岁及以上</option>
            </select>
          </div>
          <div v-for="flag in flags" :key="flag.key" class="space-y-2">
            <label :for="`research-${flag.key}`" class="block text-sm">{{ flag.label }}</label>
            <select
              :id="`research-${flag.key}`"
              v-model="background[flag.key]"
              class="w-full rounded-xl border border-gray-200 p-3 text-sm"
            >
              <option :value="null">未填写 / 不确定</option>
              <option :value="false">否</option>
              <option :value="true">是</option>
            </select>
          </div>
        </fieldset>
        <button
          type="submit"
          :disabled="busy || loading"
          class="rounded-xl bg-gray-800 px-4 py-3 text-sm text-white disabled:opacity-50"
        >
          保存可选背景
        </button>
      </form>
    </template>
  </section>
</template>
