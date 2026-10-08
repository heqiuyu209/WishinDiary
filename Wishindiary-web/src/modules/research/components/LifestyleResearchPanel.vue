<script setup lang="ts">
import { computed, ref } from 'vue';
import type { LifestyleCoverage, LifestyleEvaluation, LifestyleScore } from '../../../types/api';
import PersonalHistoryPanel from './PersonalHistoryPanel.vue';
import TrackingProbabilityPanel from './TrackingProbabilityPanel.vue';
const props = defineProps<{ evaluation?: LifestyleEvaluation; coverage?: LifestyleCoverage }>();
const stage = ref('0');
const protocol = ref('unseen_users');
const mode = ref('direct');
const selected = computed(() => props.evaluation?.stages?.[stage.value]?.protocols[protocol.value]);
const rows = computed(() => [
  { key: `base_${mode.value}`, label: '周期历史' },
  { key: `sleep_${mode.value}`, label: '历史 + 睡眠' },
  { key: `sleep_stress_${mode.value}`, label: '再加压力' },
  { key: `sleep_stress_exercise_${mode.value}`, label: '再加运动' },
  { key: 'mean3', label: '最近三次均值' },
  { key: 'median3', label: '最近三次中位数' },
  { key: 'ewma', label: '指数平滑' },
  { key: 'personal_mean', label: '全历史个人均值' },
  { key: 'recent6', label: '最近六次均值' },
  { key: 'decay3', label: '时间衰减（半衰期三次）' },
  { key: 'conditional_history', label: '条件等待分布' },
]);
const metric = (value: number | undefined, suffix = '') =>
  value == null ? '不可用' : `${value.toFixed(2)}${suffix}`;
const pairedInterval = (score?: LifestyleScore) => {
  const ci = score?.delta_mae_ci95;
  if (!ci) return '未计算';
  if (!ci.available) return `用户不足（${ci.n_users}/${ci.min_users}）`;
  return `[${metric(ci.lower)}, ${metric(ci.upper)}]`;
};
const isPrimary = (method: string) => {
  const primary = props.evaluation?.primary_comparison;
  return (
    primary?.stage === stage.value &&
    primary.protocol === protocol.value &&
    primary.method === method
  );
};
const primaryScore = computed(() => {
  const primary = props.evaluation?.primary_comparison;
  return primary && isPrimary(primary.method) && primary.method.endsWith(`_${mode.value}`)
    ? selected.value?.metrics[primary.method]
    : undefined;
});
const coverageRows = computed(
  () =>
    [
      ['睡眠时长', props.coverage?.sleep ?? 0],
      ['压力', props.coverage?.stress ?? 0],
      ['运动时长', props.coverage?.exercise ?? 0],
      ['运动强度', props.coverage?.intensity ?? 0],
    ] as const,
);
</script>

<template>
  <section
    aria-label="生活因素研究"
    class="rounded-3xl bg-white border border-gray-100 p-5 space-y-4"
  >
    <h2 class="font-bold text-gray-800">生活因素与动态预测 · 离线实验</h2>
    <p class="text-xs text-gray-500 leading-relaxed">
      睡眠、压力和运动是候选特征，论文相关性不能换算为固定的延后天数。这里比较相同测试样本上的模型；生活因素模型尚未接入线上，结果不能作为医学结论。
    </p>
    <div v-if="coverage" class="rounded-xl bg-slate-50 p-3 text-xs">
      <p>新版日志 {{ coverage.recorded }} 条；旧版默认值待核对 {{ coverage.legacy }} 条。</p>
      <div class="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
        <p v-for="[label, count] in coverageRows" :key="label">
          {{ label }}已填写 {{ count }}/{{ coverage.recorded }}
        </p>
      </div>
      <p class="mt-2 text-gray-500">
        这是日志填写量；实验特征覆盖率按完整的 28 个日历日计算，未记录日仍视为缺失。
      </p>
    </div>
    <p v-if="!evaluation?.available" class="text-sm text-gray-500">
      {{ evaluation?.message || '尚未生成生活因素离线对照报告' }}
    </p>
    <template v-else>
      <p
        v-if="evaluation.dataset?.source === 'synthetic'"
        class="rounded-xl bg-amber-50 p-3 text-xs text-amber-800"
      >
        当前使用合成数据验证流程，不能代表真实预测准确率或医学因果关系。
      </p>
      <p
        v-if="evaluation.pipeline_matches_report === false"
        class="rounded-xl bg-red-50 p-3 text-xs text-red-700"
      >
        报告与当前算法代码不匹配，请重新生成后比较。
      </p>
      <p class="text-xs text-gray-500">
        契约 {{ evaluation.feature_version }} · {{ evaluation.dataset?.n_users }} 位用户 · 测试自
        {{ evaluation.test_cutoff }}
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        <label>
          预测时点
          <select v-model="stage" class="mt-1 w-full border rounded-xl p-2">
            <option value="0">开始日：下一周期长度</option>
            <option value="7">第 7 天：剩余等待</option>
            <option value="14">第 14 天：剩余等待</option>
            <option value="21">第 21 天：剩余等待</option>
          </select>
        </label>
        <label>
          验证人群
          <select v-model="protocol" class="mt-1 w-full border rounded-xl p-2">
            <option value="unseen_users">模型未见用户</option>
            <option value="existing_users">既有用户</option>
          </select>
        </label>
        <label>
          模型与个人历史的结合
          <select v-model="mode" class="mt-1 w-full border rounded-xl p-2">
            <option value="direct">直接模型输出</option>
            <option value="shrinkage">现有个人历史收缩</option>
            <option value="adaptive">训练段学习融合权重</option>
          </select>
        </label>
      </div>
      <p class="text-xs text-gray-500">
        共同测试 {{ selected?.samples ?? 0 }} / 候选
        {{ selected?.candidate_samples ?? 0 }} 条；空训练折
        {{ selected?.skipped_empty_folds ?? 0 }}。ΔMAE 相对{{
          mode === 'shrinkage' ? '现有收缩历史模型（统计基线除外）' : '直接历史模型'
        }}，负数表示误差减少；统计基线始终相对直接历史模型。
      </p>
      <p v-if="stage !== '0'" class="text-xs text-indigo-700">
        只评估在该日及时确认尚未开始的用户。未打卡不等于尚未开始；不同预测时点的人群不同，不能直接比较误差大小。
      </p>
      <p
        v-if="primaryScore"
        class="rounded-xl bg-rose-50 p-3 text-xs leading-relaxed text-rose-800"
      >
        固定主对照：ΔMAE {{ metric(primaryScore.delta_mae_vs_base, ' 天') }}；配对 95% 区间
        {{ pairedInterval(primaryScore) }}。测试用户
        {{ primaryScore.delta_mae_ci95?.n_users ?? '未知' }} 位。
      </p>
      <p v-if="selected?.samples" class="text-xs text-gray-500 sm:hidden">
        横向滑动表格查看区间与覆盖率。
      </p>
      <p v-if="!selected?.samples" class="text-sm text-gray-500">
        该时点或人群暂无可用共同测试样本。
      </p>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[780px] text-xs text-left">
          <thead class="text-gray-500">
            <tr>
              <th class="p-2">模型</th>
              <th>MAE（天）</th>
              <th>±2 天命中</th>
              <th>ΔMAE</th>
              <th>配对 95% 区间</th>
              <th>校准覆盖</th>
              <th>区间宽度</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key" class="border-t border-gray-100">
              <td class="p-2">
                {{ row.label }}
                <span v-if="isPrimary(row.key)" class="block text-rose-700">固定主对照</span>
              </td>
              <td>{{ metric(selected.metrics[row.key]?.mae) }}</td>
              <td>{{ metric(selected.metrics[row.key]?.hit_rate_within_2d, '%') }}</td>
              <td>{{ metric(selected.metrics[row.key]?.delta_mae_vs_base) }}</td>
              <td>{{ pairedInterval(selected.metrics[row.key]) }}</td>
              <td>
                {{ metric(selected.metrics[row.key]?.coverage_pct, '%') }}（{{
                  selected.metrics[row.key]?.interval_samples ?? 0
                }}/{{ selected.samples }}）
              </td>
              <td>{{ metric(selected.metrics[row.key]?.mean_width_days, ' 天') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs leading-relaxed text-gray-500">
        配对区间对整位用户重采样，条件于本次已拟合模型；少于 10
        位测试用户不计算。固定主对照是否为前瞻方案以实验登记为准，其余比较为探索且未做多重比较校正。跨过零表示当前数据仍不能明确区分误差方向。
      </p>
      <p class="text-xs text-gray-500">
        校准目标
        {{
          evaluation.target_coverage_pct
        }}%，使用独立时间校准段；校准不足时不输出有限区间，经验覆盖率不是临床保证。
      </p>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <div
          v-for="[key, label] in [
            ['none', '未填写生活因素'],
            ['sparse', '平均覆盖不足 50%'],
            ['covered', '平均覆盖至少 50%'],
          ]"
          :key="key"
          class="rounded-xl bg-slate-50 p-3"
        >
          <p class="font-semibold">{{ label }}</p>
          <p v-for="row in rows.slice(0, 4)" :key="row.key" class="mt-1">
            {{ row.label }}：{{
              selected?.coverage_groups?.[key!]?.[row.key]?.samples ?? 0
            }}
            条，MAE {{ metric(selected?.coverage_groups?.[key!]?.[row.key]?.mae) }}
          </p>
        </div>
      </div>
      <div v-if="selected?.background_groups" class="grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
        <div
          v-for="[key, label] in [
            ['unknown', '背景未知'],
            ['explicit_none', '各项背景明确否定'],
            ['reported_context', '报告至少一种背景'],
          ]"
          :key="key"
          class="rounded-xl bg-rose-50 p-3"
        >
          <p class="font-semibold">{{ label }}</p>
          <p v-for="row in rows.slice(0, 4)" :key="row.key" class="mt-1">
            {{ row.label }}：{{ selected.background_groups[key!]?.[row.key]?.samples ?? 0 }} 条，MAE
            {{ metric(selected.background_groups[key!]?.[row.key]?.mae) }}
          </p>
        </div>
      </div>
      <p v-if="selected?.background_groups" class="text-xs leading-relaxed text-gray-500">
        医学背景使用预测前已知版本，只作分组误差描述；不同背景并不代表同一种机制，小组结果不能解释为原因。
      </p>
      <PersonalHistoryPanel :protocol="selected" :stage="stage" />
      <TrackingProbabilityPanel
        v-if="evaluation.tracking_probability"
        :evaluation="evaluation.tracking_probability"
      />
      <p class="text-xs text-gray-500">
        事后补录或未知签发
        {{ evaluation.exclusions?.late_or_unknown_issuance ?? 0 }} 个间隔；缺少及时未开始确认
        {{ evaluation.exclusions?.dynamic_without_timely_confirmation ?? 0 }}
        个动态候选；其余排除原因保留在离线汇总报告中。
      </p>
    </template>
  </section>
</template>
