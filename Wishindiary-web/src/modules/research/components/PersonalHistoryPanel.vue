<script setup lang="ts">
import { computed, ref } from 'vue';
import type { LifestyleProtocol } from '../../../types/api';

const props = defineProps<{ protocol?: LifestyleProtocol; stage: string }>();
const grouping = ref('history');
const groups = computed(() =>
  grouping.value === 'history'
    ? [
        { key: 'short', label: '3–5 次历史' },
        { key: 'medium', label: '6–11 次历史' },
        { key: 'long', label: '至少 12 次历史' },
      ]
    : [
        { key: 'low', label: '近期波动 ≤2 天' },
        { key: 'high', label: '近期波动 >2 天' },
      ],
);
const partition = computed(() =>
  grouping.value === 'history'
    ? props.protocol?.history_groups
    : props.protocol?.variability_groups,
);
const gates = computed(() =>
  (props.protocol?.fits ?? []).flatMap((fit) => fit.adaptive_blend?.base ?? []),
);
const learned = computed(() => gates.value.filter((gate) => gate.available).length);
const metric = (value?: number, suffix = '') =>
  value == null ? '不可用' : `${value.toFixed(2)}${suffix}`;
</script>

<template>
  <section aria-label="个体化历史研究" class="space-y-3 rounded-2xl bg-indigo-50 p-4 text-xs">
    <h3 class="font-semibold text-indigo-900">个体化历史 · 分组对照</h3>
    <p class="leading-relaxed text-gray-600">
      融合权重在训练段内按时间先后学习，参考历史充分度、近期波动和生活因素填写覆盖；不足的小组使用全局权重，全局也不足时使用固定
      0.5。校准段只用于预测区间，测试结果不参与权重选择。
    </p>
    <p v-if="gates.length">
      历史模型融合：{{ learned }}/{{ gates.length }} 个训练折学习到权重；{{
        gates.length - learned
      }}
      个折回退到固定 0.5。全局模型权重：{{
        gates.map((gate) => `${Math.round(gate.global_model_weight * 100)}%`).join(' / ')
      }}。
    </p>
    <label class="block">
      个人历史分组
      <select v-model="grouping" class="ml-2 rounded-xl border bg-white p-2">
        <option value="history">历史长度</option>
        <option value="variability">近期波动</option>
      </select>
    </label>
    <p v-if="!partition" class="text-gray-500">暂无个人历史分组报告，请重新生成实验。</p>
    <div v-else class="grid grid-cols-1 gap-3 md:grid-cols-3">
      <div v-for="group in groups" :key="group.key" class="rounded-xl bg-white p-3 space-y-1">
        <p class="font-semibold">{{ group.label }}</p>
        <p>{{ partition[group.key]?.base_adaptive?.samples ?? 0 }} 条共同样本</p>
        <p>直接历史模型 MAE：{{ metric(partition[group.key]?.base_direct?.mae) }} 天</p>
        <p>学习融合 MAE：{{ metric(partition[group.key]?.base_adaptive?.mae) }} 天</p>
        <p>时间衰减 MAE：{{ metric(partition[group.key]?.decay3?.mae) }} 天</p>
        <p>
          融合区间覆盖：{{ metric(partition[group.key]?.base_adaptive?.coverage_pct, '%') }}（{{
            partition[group.key]?.base_adaptive?.interval_samples ?? 0
          }}/{{ partition[group.key]?.base_adaptive?.samples ?? 0 }}）
        </p>
      </div>
    </div>
    <p class="leading-relaxed text-gray-600">
      波动按预测前最近最多六次历史的标准差分组，2
      天是固定研究分界。分组只描述当前队列，不作为医学分类。
      {{
        stage === '0'
          ? '条件等待分布在开始日使用完整分布。'
          : '条件等待分布仅在及时确认尚未开始后，保留等待超过当天的概率质量。'
      }}
      所有新增方法仍为离线候选。
    </p>
  </section>
</template>
