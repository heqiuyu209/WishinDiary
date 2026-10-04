<script setup lang="ts">
import { computed, ref } from 'vue';
import type { TrackingProbabilityEvaluation } from '../../../types/api';
const props = defineProps<{ evaluation: TrackingProbabilityEvaluation }>();
const protocol = ref('unseen_users');
const selected = computed(() => props.evaluation.protocols[protocol.value]);
const score = computed(() => selected.value?.scores);
const interval = computed(() => score.value?.delta_brier_ci95);
const fits = computed(() => selected.value?.fits.filter((fit) => fit.available) ?? []);
const calibrated = computed(() => fits.value.filter((fit) => fit.probability_calibrated).length);
const metric = (value?: number | null, percent = false) =>
  value == null ? '不可用' : percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(4);
</script>

<template>
  <section
    aria-label="漏记概率研究"
    class="space-y-3 rounded-2xl border border-amber-100 bg-amber-50 p-4 text-xs"
  >
    <h3 class="font-semibold text-amber-900">漏记概率 · 已结束间隔的核对实验</h3>
    <p class="leading-relaxed text-gray-600">
      估计目标是用户之后是否明确核对为漏记，不是判断实际经期何时发生。长间隔本身不能当作漏记标签；未知和未核对记录保持无标签，不补造日期。
      当前结果只用于研究管理，尚未生成个人提醒或接入线上预测。
    </p>
    <label class="block">
      核对实验人群
      <select v-model="protocol" class="ml-2 rounded-xl border bg-white p-2">
        <option value="unseen_users">模型未见用户</option>
        <option value="existing_users">既有用户</option>
      </select>
    </label>
    <p>
      候选 {{ selected?.candidate_samples ?? 0 }} 条 · 明确核对
      {{ selected?.reviewed_samples ?? 0 }} 条 · 未核对/未知
      {{ selected?.unreviewed_samples ?? 0 }} 条 · 因训练不足跳过的核对样本
      {{ selected?.skipped_reviewed_samples ?? 0 }} 条。
    </p>
    <p v-if="!score?.samples" class="text-amber-900">
      明确核对标签、正反类别或测试样本不足，暂无可用漏记概率评估；未核对不等于没有漏记。
    </p>
    <template v-else>
      <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <p>共同测试：{{ score.samples }} 条</p>
        <p>模型 Brier：{{ metric(score.brier) }}</p>
        <p>训练频率基线：{{ metric(score.baseline_brier) }}</p>
        <p>ΔBrier：{{ metric(score.delta_brier) }}</p>
      </div>
      <p>
        配对 95% 区间：{{
          interval?.available
            ? `[${metric(interval.lower)}, ${metric(interval.upper)}]`
            : `用户不足（${interval?.n_users ?? 0}/${interval?.min_users ?? 10}）`
        }}。Brier 是概率误差，范围 0–1，越小越好；Δ 相对仅使用训练段核对频率的常数基线。
      </p>
      <p>
        {{ calibrated }}/{{ fits.length }}
        个可用折完成独立时间段概率校准；其余折为未经独立校准的模型分数。
      </p>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[430px] text-left">
          <caption class="pb-2 text-left text-gray-600">
            概率分箱 · 前四组不含上界，最后一组包含 100%
          </caption>
          <thead>
            <tr>
              <th class="p-2">概率范围</th>
              <th>样本</th>
              <th>平均估计</th>
              <th>之后核对为漏记</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="bucket in score.reliability_bins"
              :key="bucket.lower"
              class="border-t border-amber-100"
            >
              <td class="p-2">
                {{ Math.round(bucket.lower * 100) }}–{{ Math.round(bucket.upper * 100) }}%
              </td>
              <td>{{ bucket.samples }}</td>
              <td>{{ metric(bucket.mean_probability, true) }}</td>
              <td>{{ metric(bucket.observed_review_rate, true) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <p class="leading-relaxed text-gray-600">
      核对人群存在选择偏差，用户核对也不等于医学真值。整位用户的配对区间条件于已拟合模型，比较属于探索且未做多重比较校正；少于
      10 位测试用户不计算。这里的队列和目标与周期长度预测不同，不能横向比较分数。
    </p>
  </section>
</template>
