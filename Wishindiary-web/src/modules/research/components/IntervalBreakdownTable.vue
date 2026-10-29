<script setup lang="ts">
import { ref } from 'vue';
import type { ForecastBreakdownRow, ForecastIntervalMethod } from '../../../types/api';

withDefaults(
  defineProps<{ rows: ForecastBreakdownRow[]; selectorLabel: string; includePoint?: boolean }>(),
  { includePoint: true },
);
const method = ref<ForecastIntervalMethod>('rf_personalized');
const metric = (value: number | undefined, suffix = '') =>
  value === undefined ? '暂无结果' : `${value.toFixed(2)}${suffix}`;
</script>

<template>
  <div class="min-w-0">
    <label class="mt-3 flex flex-wrap items-center gap-3 text-sm">
      {{ selectorLabel }}
      <select v-model="method" class="rounded-lg border bg-white px-3 py-2">
        <option value="rf_personalized">RF 个性化路径</option>
        <option value="basic_stats">基础统计路径</option>
      </select>
    </label>
    <p class="mt-3 text-sm text-gray-500">
      覆盖率和宽度只比较同一批配对样本。缺少原始区间或校准历史时单独注明。
    </p>
    <p class="mt-2 text-xs text-gray-500 sm:hidden">左右滑动表格查看覆盖率和区间宽度。</p>
    <div class="mt-3 overflow-x-auto">
      <table class="w-full min-w-140 text-left text-sm">
        <caption class="sr-only">{{ selectorLabel }}的配对覆盖率与区间宽度</caption>
        <thead>
          <tr>
            <th class="py-2 font-medium">范围</th>
            <th class="px-2 py-2 font-medium">全部 / 所选路径</th>
            <th v-if="includePoint" class="px-2 py-2 font-medium">完整算法 MAE</th>
            <th v-if="includePoint" class="px-2 py-2 font-medium">均值 MAE</th>
            <th class="px-2 py-2 font-medium">配对样本</th>
            <th class="px-2 py-2 font-medium">覆盖率 原始 → 校准</th>
            <th class="px-2 py-2 font-medium">宽度 原始 → 校准</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.label">
            <tr class="border-t border-gray-100">
              <td class="whitespace-pre-line py-3">{{ row.label }}</td>
              <td class="px-2">
                {{ row.samples }} / {{ row.interval_comparison?.[method].test_samples ?? 0 }}
              </td>
              <td v-if="includePoint" class="px-2">
                {{ metric(row.models.online_pipeline?.mae) }}
              </td>
              <td v-if="includePoint" class="px-2">{{ metric(row.models.mean3?.mae) }}</td>
              <td class="px-2">{{ row.interval_comparison?.[method].comparison.samples ?? 0 }}</td>
              <template v-if="row.interval_comparison?.[method].comparison.samples">
                <td class="px-2">
                  {{
                    metric(row.interval_comparison[method].comparison.original.coverage_pct, '%')
                  }}
                  →
                  {{
                    metric(row.interval_comparison[method].comparison.calibrated.coverage_pct, '%')
                  }}
                </td>
                <td class="px-2">
                  {{ metric(row.interval_comparison[method].comparison.original.mean_width_days) }}
                  →
                  {{
                    metric(
                      row.interval_comparison[method].comparison.calibrated.mean_width_days,
                      ' 天',
                    )
                  }}
                </td>
              </template>
              <td v-else colspan="2" class="px-2 text-gray-500">
                {{
                  row.interval_comparison?.[method].test_samples
                    ? '暂无配对区间样本'
                    : '该路径暂无样本'
                }}
              </td>
            </tr>
            <tr
              v-if="
                row.interval_comparison?.[method].unavailable_samples ||
                row.interval_comparison?.[method].calibrated.samples !==
                  row.interval_comparison?.[method].comparison.samples
              "
            >
              <td
                :colspan="includePoint ? 7 : 5"
                class="pb-3 text-xs leading-relaxed text-gray-500"
              >
                <span
                  v-if="row.interval_comparison?.[method].unavailable_samples"
                  class="text-amber-700"
                >
                  {{ row.interval_comparison[method].unavailable_samples }}
                  条样本因校准历史不足而无法校准。
                </span>
                <span
                  v-if="
                    row.interval_comparison?.[method].calibrated.samples &&
                    row.interval_comparison[method].calibrated.samples !==
                      row.interval_comparison[method].comparison.samples
                  "
                >
                  全部可校准 {{ row.interval_comparison[method].calibrated.samples }} 条：覆盖率
                  {{ metric(row.interval_comparison[method].calibrated.coverage_pct, '%') }}，宽度
                  {{ metric(row.interval_comparison[method].calibrated.mean_width_days, ' 天') }}。
                </span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <p v-if="includePoint" class="mt-3 text-xs text-gray-500">
      MAE 使用该行全部预测；区间比较使用所选路径的配对样本。空窗不生成指标。
    </p>
  </div>
</template>
