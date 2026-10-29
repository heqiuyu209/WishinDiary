<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { getResearchSummaryApi } from '../api';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';
import type { ResearchSummary } from '../../../types/api';

const summary = ref<ResearchSummary | null>(null);
const loading = ref(false);
const error = ref('');
const load = async () => {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  try {
    summary.value = (await getResearchSummaryApi()).data;
  } catch (err) {
    error.value = extractApiErrorMessage(err, '研究汇总加载失败，请重试');
  } finally {
    loading.value = false;
  }
};
const maximum = computed(() =>
  Math.max(1, ...(summary.value?.data.cycle_distribution.map((r) => r.count) ?? [])),
);
const metricRows = computed(() => {
  const metrics = summary.value?.evaluation.metrics ?? {};
  return [
    { label: '分用户留出 · 随机森林', mae: metrics.holdout?.mae },
    { label: '分用户五折 · 随机森林', mae: metrics.group_kfold?.mae },
    { label: '同五折 · 最近三次均值', mae: metrics.group_kfold?.baseline_mean3_mae },
    { label: '时间留出 · 随机森林', mae: metrics.temporal_holdout?.mae },
  ];
});
const deliveryLabels: Record<string, string> = {
  sent: 'SMTP 已受理',
  sending: '发送中／待核查',
  unknown: '结果不确定',
  canceled: '发送前取消',
};
onMounted(() => void load());
</script>

<template>
  <section class="space-y-6 text-gray-800">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold">研究管理</h1>
        <p class="mt-2 text-sm text-gray-500">查看数据质量、基线表现与下一步实验依据</p>
      </div>
      <button
        class="rounded-xl border bg-white px-4 py-2 text-sm disabled:opacity-50"
        :disabled="loading"
        @click="load"
      >
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>
    <p v-if="error" role="alert" class="rounded-xl bg-red-50 p-4 text-sm text-red-700">
      {{ error }}
    </p>
    <p v-if="loading && !summary" role="status">正在汇总研究数据…</p>
    <template v-if="summary">
      <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div
          v-for="card in [
            { label: '账号数', value: summary.data.users },
            { label: '已知完整周期', value: summary.data.completed },
            { label: '具有 4 次历史的账号', value: summary.data.users_with_ml_history },
            { label: '当前特征范围内的样本', value: summary.data.feature_samples },
          ]"
          :key="card.label"
          class="rounded-2xl border border-gray-100 bg-white p-5"
        >
          <p class="text-sm text-gray-500">{{ card.label }}</p>
          <p class="mt-2 text-2xl font-semibold">{{ card.value }}</p>
        </div>
      </div>
      <div class="grid gap-6 md:grid-cols-2">
        <div class="rounded-2xl border border-gray-100 bg-white p-5">
          <h2 class="font-semibold">周期长度分布</h2>
          <p v-if="!summary.data.cycle_distribution.length" class="mt-4 text-sm text-gray-500">
            尚无完整周期记录
          </p>
          <div class="mt-4 max-h-64 space-y-2 overflow-y-auto">
            <div
              v-for="row in summary.data.cycle_distribution"
              :key="row.days"
              class="flex items-center gap-3 text-sm"
            >
              <span class="w-12 shrink-0">{{ row.days }} 天</span>
              <div class="h-3 flex-1 rounded bg-gray-100">
                <div
                  class="h-3 rounded bg-rose-400"
                  :style="{ width: `${(row.count / maximum) * 100}%` }"
                ></div>
              </div>
              <span class="w-12 text-right">{{ row.count }} 条</span>
            </div>
          </div>
        </div>
        <div class="rounded-2xl border border-gray-100 bg-white p-5">
          <h2 class="font-semibold">记录质量与历史充分度</h2>
          <p class="mt-3 text-sm">当前特征范围外周期：{{ summary.data.outside_range }} 条</p>
          <p class="mt-2 text-sm">缺失出血天数：{{ summary.data.missing_bleeding }} 条</p>
          <div class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="bucket in summary.data.history_distribution"
              :key="bucket.label"
              class="rounded-lg bg-gray-50 px-3 py-2 text-sm"
            >
              {{ bucket.label }}：{{ bucket.count }} 人
            </span>
          </div>
          <p class="mt-4 text-sm leading-relaxed text-gray-500">
            范围外记录保留原值。汇总不展示个人身份、日记或同房记录，也不会自动用于训练。
          </p>
        </div>
      </div>
      <div class="rounded-2xl border border-gray-100 bg-white p-5">
        <h2 class="font-semibold">离线实验与基线</h2>
        <p v-if="!summary.evaluation.available" class="mt-4 text-sm text-gray-500">
          {{ summary.evaluation.message }}
        </p>
        <template v-else>
          <div class="mt-3 flex flex-wrap gap-2 text-sm">
            <span class="rounded-lg bg-indigo-50 px-3 py-2">
              {{ summary.evaluation.model_version }}
            </span>
            <span class="rounded-lg bg-gray-50 px-3 py-2">
              {{
                summary.evaluation.dataset?.source === 'synthetic'
                  ? '合成数据演示'
                  : summary.evaluation.dataset?.source
              }}
            </span>
            <span class="rounded-lg bg-gray-50 px-3 py-2">
              真实 {{ summary.evaluation.dataset?.real_samples ?? 0 }} / 合成
              {{ summary.evaluation.dataset?.synthetic_samples ?? 0 }} 样本
            </span>
          </div>
          <p
            v-if="summary.evaluation.model_matches_report === false"
            role="alert"
            class="mt-3 text-sm text-amber-700"
          >
            模型文件与报告不匹配，指标可能已过期。
          </p>
          <table class="mt-4 w-full text-left text-sm">
            <caption class="pb-2 text-left text-gray-500">
              平均绝对误差越小越好；不同验证协议分开解读
            </caption>
            <thead>
              <tr>
                <th class="py-2 font-medium">验证协议</th>
                <th class="py-2 font-medium">MAE（天）</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in metricRows" :key="row.label" class="border-t border-gray-100">
                <td class="py-3">{{ row.label }}</td>
                <td>{{ row.mae === undefined ? '暂无结果' : row.mae.toFixed(2) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-3 break-all text-xs text-gray-500">
            生成时间 {{ summary.evaluation.generated_at || '未记录' }} · 代码
            {{ summary.evaluation.git_commit?.slice(0, 8) || '未记录' }}
          </p>
        </template>
      </div>
      <div class="rounded-2xl border border-gray-100 bg-white p-5">
        <h2 class="font-semibold">提醒运行状态</h2>
        <p v-if="!summary.data.reminder_states?.length" class="mt-3 text-sm text-gray-500">
          暂无提醒发送记录
        </p>
        <div class="mt-3 flex flex-wrap gap-2 text-sm">
          <span
            v-for="row in summary.data.reminder_states"
            :key="row.state"
            class="rounded-lg bg-gray-50 px-3 py-2"
          >
            {{ deliveryLabels[row.state] ?? row.state }}：{{ row.count }} 次
          </span>
        </div>
        <p class="mt-3 text-sm leading-relaxed text-gray-500">
          SMTP
          受理不代表已到达收件箱。结果不确定或长时间发送中的记录需核查邮件服务日志，不自动重发。
        </p>
      </div>
      <div class="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-5">
        <h2 class="font-semibold">下一步实验方向</h2>
        <ul class="mt-3 list-disc space-y-3 pl-5 text-sm leading-relaxed">
          <li v-for="item in summary.recommendations" :key="item">{{ item }}</li>
        </ul>
      </div>
    </template>
  </section>
</template>
