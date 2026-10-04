<script setup lang="ts">
import type { ResearchExperiment } from '../../../types/api';
defineProps<{ experiments: ResearchExperiment[] }>();
const statusLabels: Record<ResearchExperiment['status'], string> = {
  registered: '方案已登记',
  frozen: '数据已冻结',
  complete: '结果已生成',
  authorization_changed: '授权或删除状态变化，结果停止使用',
  invalid: '文件无效，请核对',
};
</script>
<template>
  <section
    class="space-y-4 rounded-2xl border border-gray-100 bg-white p-5"
    aria-labelledby="research-experiments-title"
  >
    <h2 id="research-experiments-title" class="font-semibold">固定方案与实验登记</h2>
    <p class="text-sm leading-relaxed text-gray-500">
      最近 20
      个实验。方案固定时间截点、主要比较、随机种子和版本；部署者在离线环境冻结数据、运行和重放。这里展示汇总状态。
    </p>
    <p v-if="!experiments.length" class="text-sm text-gray-500">
      尚未登记实验，先固定独立未来测试段再收集研究样本。
    </p>
    <article
      v-for="experiment in experiments"
      :key="experiment.run_id"
      class="space-y-2 rounded-xl bg-gray-50 p-4 text-sm"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="font-medium">实验 {{ experiment.run_id.slice(0, 8) }}</p>
        <span class="text-rose-700">{{ statusLabels[experiment.status] }}</span>
      </div>
      <p v-if="experiment.kind" class="text-gray-600">
        {{
          experiment.kind === 'prospective_plan'
            ? '测试截点前登记的方案'
            : '回顾性探索：使用历史测试段'
        }}
      </p>
      <p v-if="experiment.test_cutoff" class="break-words text-xs text-gray-500">
        校准自 {{ experiment.calibration_cutoff }} · 测试自 {{ experiment.test_cutoff }} · 观察截至
        {{ experiment.data_as_of }}
      </p>
      <p v-if="experiment.status === 'complete'">
        {{ experiment.source === 'synthetic' ? '合成演示' : '授权研究数据' }} ·
        {{ experiment.n_users }} 位用户 · {{ experiment.eligible_cases }} 个阶段样本
      </p>
      <p v-if="experiment.pipeline_matches === false" class="text-xs text-amber-700">
        算法版本已变化，需登记新实验或恢复原环境重放。
      </p>
    </article>
    <p class="text-xs leading-relaxed text-gray-500">
      本地提前登记不证明数据未被看过；回顾性比较不能作为前瞻验证。合成结果不能代表真实效果。
    </p>
  </section>
</template>
