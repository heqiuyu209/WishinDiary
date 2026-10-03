<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { getResearchSummaryApi } from '../api';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';
import IntervalBreakdownTable from '../components/IntervalBreakdownTable.vue';
import type {
  ForecastGroup,
  ForecastIntervalMethod,
  ForecastMethod,
  ForecastProtocol,
  ResearchSummary,
} from '../../../types/api';

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
  ].map((row) => ({
    ...row,
    notApplicable:
      row.label.startsWith('时间留出') &&
      summary.value?.evaluation.temporal_holdout_status === 'not_applicable',
  }));
});
const forecastProtocol = ref<ForecastProtocol>('existing_users');
const forecastGroup = ref<ForecastGroup>('history');
const forecast = computed(() => summary.value?.forecast_evaluation);
const forecastResult = computed(() => forecast.value?.protocols?.[forecastProtocol.value]);
const timeWindowRows = computed(() =>
  (forecastResult.value?.time_windows ?? []).map((row) => ({
    ...row,
    label: `${row.start}\n至 ${row.end_exclusive}（不含）`,
  })),
);
const calibrationResult = computed(() => forecastResult.value?.calibration);
const calibrationLabels: Record<ForecastIntervalMethod, string> = {
  rf_personalized: 'RF 个性化路径',
  basic_stats: '基础统计路径',
};
const calibrationFitText = (method: ForecastIntervalMethod) => {
  const fits = calibrationResult.value?.methods[method].fits ?? [];
  if (!fits.length) return '暂无校准折';
  const counts = fits.map((fit) => fit.samples);
  const low = Math.min(...counts);
  const high = Math.max(...counts);
  return `每折校准 ${low === high ? low : `${low}–${high}`} 条 · ${fits.filter((fit) => fit.available).length}/${fits.length} 折可用`;
};
const protocolLabels: Record<ForecastProtocol, string> = {
  existing_users: '既有用户',
  unseen_users: '模型未见用户',
};
const methodLabels: Record<ForecastMethod, string> = {
  online_pipeline: '线上完整算法',
  mean3: '最近三次均值',
  median3: '最近三次中位数',
  ewma: '指数平滑（α=0.5）',
};
const sourceLabels: Record<string, string> = {
  synthetic: '合成数据演示',
  authorized_csv: '授权 CSV 数据',
  authorized_database: '授权数据库数据',
};
const metric = (value: number | undefined, suffix = '') =>
  value === undefined ? '暂无结果' : `${value.toFixed(2)}${suffix}`;
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
              输入 {{ summary.evaluation.dataset?.real_samples ?? 0 }} / 合成
              {{ summary.evaluation.dataset?.synthetic_samples ?? 0 }} 样本
            </span>
          </div>
          <p
            v-if="summary.evaluation.temporal_holdout_status === 'not_applicable'"
            role="status"
            class="mt-3 text-sm text-amber-700"
          >
            当前 CSV 只有周期顺序，月份特征已停用；真实日历时间留出不适用。
          </p>
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
                <td>
                  {{
                    row.notApplicable
                      ? '不适用'
                      : row.mae === undefined
                        ? '暂无结果'
                        : row.mae.toFixed(2)
                  }}
                </td>
              </tr>
            </tbody>
          </table>
          <p class="mt-3 break-all text-xs text-gray-500">
            生成时间 {{ summary.evaluation.generated_at || '未记录' }} · 代码
            {{ summary.evaluation.git_commit?.slice(0, 8) || '未记录' }}
          </p>
        </template>
      </div>
      <div class="min-w-0 rounded-2xl border border-gray-100 bg-white p-5">
        <h2 class="font-semibold">完整流程前瞻回测</h2>
        <p v-if="!forecast?.available" class="mt-3 text-sm text-gray-500">
          {{ forecast?.message || '尚未生成完整流程回测报告' }}
        </p>
        <template v-else>
          <div class="mt-3 flex flex-wrap gap-2 text-sm">
            <span class="rounded-lg bg-indigo-50 px-3 py-2">
              {{ sourceLabels[forecast.dataset?.source || ''] || '未标注来源' }}
            </span>
            <span class="rounded-lg bg-gray-50 px-3 py-2">
              {{ forecast.dataset?.total_cycles }} 条周期 · {{ forecast.dataset?.n_users }} 个用户
            </span>
            <span class="rounded-lg bg-gray-50 px-3 py-2">
              {{ forecast.calibration ? '未来测试起点' : '日历截点' }} {{ forecast.cutoff }}
            </span>
          </div>
          <p v-if="forecast.calibration" class="mt-3 text-sm leading-relaxed text-gray-500">
            校准开始 {{ forecast.calibration.cutoff }} · 训练标签截至
            {{ forecast.calibration.training_labels_available_through }} · 校准标签截至
            {{ forecast.calibration.labels_available_through || '暂无已完成标签' }}
          </p>
          <p
            v-if="forecast.pipeline_matches_report === false"
            role="alert"
            class="mt-3 text-sm text-amber-700"
          >
            算法代码与回测报告不匹配，请重新生成报告后再解读结果。
          </p>
          <p class="mt-3 text-sm leading-relaxed text-gray-500">
            <template v-if="forecast.calibration">
              模型在校准开始前冻结，校准标签必须在未来测试开始前完成。模型未见用户同时从全局训练与校准中留出。
            </template>
            <template v-else>截点前训练全局模型，之后保持冻结。</template>
            个人历史逐周期更新，模型未见用户仍可以使用当时已知的个人记录。
            本报告评估完整算法及折内模型，当前部署权重的实际效果需要后续观测。
          </p>
          <div class="mt-4 flex flex-wrap gap-2" aria-label="回测验证协议">
            <button
              v-for="(label, name) in protocolLabels"
              :key="name"
              type="button"
              :aria-pressed="forecastProtocol === name"
              class="rounded-lg border px-3 py-2 text-sm"
              :class="
                forecastProtocol === name
                  ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                  : 'bg-white'
              "
              @click="forecastProtocol = name"
            >
              {{ label }}
            </button>
          </div>
          <p class="mt-3 text-sm">共同评估样本：{{ forecastResult?.samples ?? 0 }} 条</p>
          <p v-if="forecastResult?.candidate_samples != null" class="mt-1 text-xs text-gray-500">
            候选 {{ forecastResult.candidate_samples }} 条，因适用范围暂停预测
            {{ forecastResult.abstained_samples ?? 0 }} 条；误差指标只针对实际提供预测的共同样本。
          </p>
          <p v-if="!forecastResult?.samples" class="mt-3 text-sm text-gray-500">
            该协议暂无可用评估样本，不能据此判断模型优劣。
          </p>
          <template v-else>
            <div class="mt-3 overflow-x-auto">
              <table class="w-full min-w-100 text-left text-sm">
                <caption class="pb-2 text-left text-gray-500">
                  同一批未来周期 · 误差越小越好 · 正偏差表示预测偏晚
                </caption>
                <thead>
                  <tr>
                    <th class="py-2 font-medium">方法</th>
                    <th class="px-2 py-2 font-medium">MAE（天）</th>
                    <th class="px-2 py-2 font-medium">±3 天命中</th>
                    <th class="px-2 py-2 font-medium">偏差（天）</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(label, method) in methodLabels"
                    :key="method"
                    class="border-t border-gray-100"
                  >
                    <td class="py-3">{{ label }}</td>
                    <td class="px-2">{{ metric(forecastResult.models[method]?.mae) }}</td>
                    <td class="px-2">
                      {{ metric(forecastResult.models[method]?.hit_rate_within_3d, '%') }}
                    </td>
                    <td class="px-2">{{ metric(forecastResult.models[method]?.bias_days) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <h3 class="mt-5 text-sm font-semibold">区间覆盖与宽度</h3>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              <div
                v-for="(label, method) in {
                  rf_personalized: 'RF 个性化树分位区间',
                  basic_stats: '基础统计区间',
                }"
                :key="method"
                class="rounded-xl bg-gray-50 p-4 text-sm"
              >
                <p>{{ label }}</p>
                <template v-if="forecastResult.intervals?.[method]?.samples">
                  <p class="mt-2">
                    实际覆盖率 {{ metric(forecastResult.intervals[method]?.coverage_pct, '%') }}
                  </p>
                  <p class="mt-1">
                    平均宽度 {{ metric(forecastResult.intervals[method]?.mean_width_days, ' 天') }}
                  </p>
                  <p class="mt-1 text-gray-500">
                    {{ forecastResult.intervals[method]?.samples }} 条样本
                  </p>
                </template>
                <p v-else class="mt-2 text-gray-500">暂无区间样本</p>
              </div>
            </div>
            <p class="mt-3 text-sm leading-relaxed text-gray-500">
              树分位区间和基础统计区间分别统计。覆盖率反映实际落入范围的比例；两种区间都未经校准，不能当作
              90% 可靠保证。
            </p>
            <template v-if="calibrationResult">
              <h3 class="mt-5 text-sm font-semibold">时间校准实验</h3>
              <p class="mt-3 text-sm leading-relaxed text-gray-500">
                预设目标
                {{
                  metric(calibrationResult.target_coverage_pct, '%')
                }}。分别用两条路径的点预测绝对误差校准，
                比较覆盖率与区间宽度。时间相关性与用户差异会影响覆盖，目标不代表可靠保证。
              </p>
              <div class="mt-3 grid gap-3 lg:grid-cols-2">
                <div
                  v-for="(label, method) in calibrationLabels"
                  :key="method"
                  class="min-w-0 rounded-xl border border-indigo-100 bg-indigo-50/30 p-4 text-sm"
                >
                  <h4 class="font-medium">{{ label }}</h4>
                  <p class="mt-2 text-gray-500">{{ calibrationFitText(method) }}</p>
                  <p
                    v-if="!calibrationResult.methods[method].fits.some((fit) => fit.available)"
                    class="mt-2 text-amber-700"
                  >
                    校准样本不足，未生成有限区间。
                  </p>
                  <p class="mt-2">
                    校准区间可用 {{ calibrationResult.methods[method].calibrated.samples }} /
                    {{ calibrationResult.methods[method].test_samples }} 条未来样本
                  </p>
                  <div
                    v-if="calibrationResult.methods[method].comparison.samples"
                    class="mt-3 overflow-x-auto"
                  >
                    <table class="w-full min-w-80 text-left">
                      <caption class="pb-2 text-left text-gray-500">
                        同一批未来样本：{{ calibrationResult.methods[method].comparison.samples }}
                        条
                      </caption>
                      <thead>
                        <tr>
                          <th class="py-2 font-medium">区间</th>
                          <th class="px-2 py-2 font-medium">覆盖率</th>
                          <th class="px-2 py-2 font-medium">平均宽度</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(rowLabel, key) in { original: '原始', calibrated: '校准后' }"
                          :key="key"
                          class="border-t border-indigo-100"
                        >
                          <td class="py-3">{{ rowLabel }}</td>
                          <td class="px-2">
                            {{
                              metric(
                                calibrationResult.methods[method].comparison[key].coverage_pct,
                                '%',
                              )
                            }}
                          </td>
                          <td class="px-2">
                            {{
                              metric(
                                calibrationResult.methods[method].comparison[key].mean_width_days,
                                ' 天',
                              )
                            }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-else class="mt-3 text-gray-500">暂无配对区间样本</p>
                  <p
                    v-if="
                      calibrationResult.methods[method].calibrated.samples &&
                      calibrationResult.methods[method].calibrated.samples !==
                        calibrationResult.methods[method].comparison.samples
                    "
                    class="mt-3 text-gray-500"
                  >
                    全部可校准样本的覆盖率
                    {{
                      metric(calibrationResult.methods[method].calibrated.coverage_pct, '%')
                    }}，平均宽度
                    {{
                      metric(calibrationResult.methods[method].calibrated.mean_width_days, ' 天')
                    }}； 缺少原始区间的样本不参与配对比较。
                  </p>
                  <p
                    v-if="calibrationResult.methods[method].unavailable_samples"
                    class="mt-3 text-amber-700"
                  >
                    {{ calibrationResult.methods[method].unavailable_samples }}
                    条测试样本因校准历史不足而无法校准。
                  </p>
                </div>
              </div>
            </template>
            <div v-if="forecast.time_windows" class="mt-5 min-w-0">
              <h3 class="text-sm font-semibold">后续时间窗口</h3>
              <p class="mt-3 text-sm leading-relaxed text-gray-500">
                按预测发起日每 {{ forecast.time_windows.window_days }} 天分窗。
                同一冻结模型与校准参数用于所有窗口，观察覆盖率和误差随时间的变化。 最后候选发起日
                {{ forecast.time_windows.last_candidate_date }}；末窗仅包含报告已有样本。
              </p>
              <IntervalBreakdownTable :rows="timeWindowRows" selector-label="分窗区间路径" />
            </div>
            <div class="mt-5 flex flex-wrap items-center gap-3 text-sm">
              <label for="forecast-group" class="font-semibold">分组误差</label>
              <select
                id="forecast-group"
                v-model="forecastGroup"
                class="rounded-lg border bg-white px-3 py-2"
              >
                <option value="history">有效历史条数</option>
                <option value="volatility">历史波动程度</option>
                <option value="missing_bleeding">出血天数缺失比例</option>
              </select>
            </div>
            <div class="mt-3 overflow-x-auto">
              <table class="w-full min-w-90 text-left text-sm">
                <thead>
                  <tr>
                    <th class="py-2 font-medium">分组</th>
                    <th class="px-2 py-2 font-medium">样本</th>
                    <th class="px-2 py-2 font-medium">完整算法 MAE</th>
                    <th class="px-2 py-2 font-medium">均值 MAE</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in forecastResult.groups?.[forecastGroup] ?? []"
                    :key="row.label"
                    class="border-t border-gray-100"
                  >
                    <td class="py-3">{{ row.label }}</td>
                    <td class="px-2">{{ row.samples }}</td>
                    <td class="px-2">{{ metric(row.models.online_pipeline?.mae) }}</td>
                    <td class="px-2">{{ metric(row.models.mean3?.mae) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="mt-3 text-sm text-gray-500">小样本分组仅供探索，空组不生成误差指标。</p>
            <div v-if="forecast.time_windows" class="mt-5 min-w-0">
              <h3 class="text-sm font-semibold">分组区间对比</h3>
              <IntervalBreakdownTable
                :rows="forecastResult.groups?.[forecastGroup] ?? []"
                selector-label="分组区间路径"
                :include-point="false"
              />
            </div>
          </template>
          <p class="mt-3 break-all text-xs text-gray-500">
            生成时间 {{ forecast.generated_at || '未记录' }} · 代码
            {{ forecast.git_commit?.slice(0, 8) || '未记录' }}
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
