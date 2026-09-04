<script setup lang="ts">
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { ECharts } from 'echarts/core';
import { nextTick, onMounted, onUnmounted, ref } from 'vue';
import { getStatsApi } from '../api';
import type { DailyLogSummary } from '../../../types/api';

echarts.use([LineChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer]);

const cycleChartRef = ref<HTMLElement | null>(null);
let chartInstance: ECharts | null = null;
const recentLogs = ref<DailyLogSummary[]>([]);

const moodTextMap: Record<number, string> = { 0: '平静', 1: '开心', 2: '烦躁', 3: '低落' };
const crampsTextMap: Record<number, string> = {
  0: '无腹痛',
  1: '轻度隐痛',
  2: '中度疼痛',
  3: '重度剧痛',
};

onMounted(async () => {
  try {
    const res = await getStatsApi();
    const cycles = res.data.cycles || [];
    recentLogs.value = res.data.recent_logs || [];

    await nextTick();
    if (cycleChartRef.value) {
      chartInstance = echarts.init(cycleChartRef.value);
      const dates = cycles.map((c) => c.start_date);
      const lengths = cycles.map((c) => Number(c.cycle_length));

      // y 轴范围随用户实际周期动态调整：上下留 4 天缓冲并按 5 的倍数取整
      const validLengths = lengths.filter((n) => Number.isFinite(n) && n > 0);
      let yMin = 20;
      let yMax = 45;
      if (validLengths.length >= 2) {
        const dataMin = Math.min(...validLengths);
        const dataMax = Math.max(...validLengths);
        const paddedMin = Math.max(14, Math.floor((dataMin - 4) / 5) * 5);
        const paddedMax = Math.ceil((dataMax + 4) / 5) * 5;
        if (paddedMax - paddedMin >= 10) {
          yMin = paddedMin;
          yMax = paddedMax;
        }
      }

      chartInstance.setOption({
        title: {
          text: '历史周期长度趋势',
          textStyle: { fontSize: 14, color: '#4b5563', fontWeight: 'bold' },
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(255,255,255,0.9)',
          borderColor: '#f43f5e',
        },
        grid: { top: 40, bottom: 20, left: 30, right: 20 },
        xAxis: {
          type: 'category',
          data: dates,
          axisLabel: { fontSize: 10, color: '#9ca3af' },
        },
        yAxis: {
          type: 'value',
          min: yMin,
          max: yMax,
          axisLabel: { fontSize: 10, color: '#9ca3af' },
        },
        series: [
          {
            data: lengths,
            type: 'line',
            smooth: true,
            symbolSize: 6,
            itemStyle: { color: '#f43f5e' },
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(244, 63, 94, 0.2)' },
                { offset: 1, color: 'rgba(244, 63, 94, 0)' },
              ]),
            },
            lineStyle: {
              width: 3,
              shadowColor: 'rgba(244, 63, 94, 0.3)',
              shadowBlur: 10,
              shadowOffsetY: 5,
            },
          },
        ],
      });
    }
  } catch (err) {
    console.error('看板加载失败', err);
  }
});

onUnmounted(() => {
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
});
</script>

<template>
  <div class="space-y-6 w-full">
    <!-- 趋势图卡片：玫瑰渐变背景 + 柔和辉光 -->
    <div
      class="relative bg-gradient-to-br from-rose-50 via-white to-pink-50 border border-rose-100/60 rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.15)] p-6 overflow-hidden"
    >
      <div
        class="absolute -top-12 -right-12 w-40 h-40 rounded-full bg-gradient-to-br from-rose-200/30 to-pink-200/30 blur-2xl pointer-events-none"
      ></div>
      <div ref="cycleChartRef" class="relative w-full h-64"></div>
    </div>

    <div
      class="relative bg-white rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.10)] border border-gray-100 p-6 overflow-hidden"
    >
      <div class="mb-4 flex items-center justify-between border-b border-rose-100/50 pb-4">
        <h2 class="text-sm font-bold text-gray-800">历史打卡记录</h2>
        <span class="text-xs font-medium text-gray-400">最近 30 天</span>
      </div>

      <div v-if="recentLogs.length === 0" class="text-center py-10 flex flex-col items-center">
        <span class="text-xs text-gray-400 font-medium">暂无数据，快去记录第一天吧</span>
      </div>

      <div
        class="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[28rem] overflow-y-auto pr-2 custom-scrollbar"
      >
        <div
          v-for="log in recentLogs"
          :key="log.log_date"
          class="bg-gradient-to-br from-white to-rose-50/40 border border-rose-100/50 p-4 rounded-2xl flex flex-col space-y-3 hover:shadow-[0_8px_30px_rgb(244,63,94,0.08)] hover:border-rose-200/70 transition-all duration-300"
        >
          <div class="flex justify-between items-center">
            <span class="text-xs font-extrabold text-gray-700">{{ log.log_date }}</span>
            <span
              class="text-[10px] px-2.5 py-1 bg-white border border-rose-100 text-rose-600 rounded-md font-bold shadow-sm"
            >
              {{ moodTextMap[log.mood_level] || '平静' }}
            </span>
          </div>
          <div class="flex flex-wrap gap-2 text-[10px] font-bold text-gray-600">
            <span class="bg-rose-50 text-rose-600 px-2 py-1 rounded-md">
              {{ crampsTextMap[log.cramps_severity] || '无腹痛' }}
            </span>
            <span v-if="log.is_exercise" class="bg-indigo-50 text-indigo-600 px-2 py-1 rounded-md">
              🏃 {{ log.exercise_type || '已运动' }}
            </span>
          </div>
          <p
            v-if="log.journal_text"
            class="text-[11px] text-gray-500 leading-relaxed pt-2 border-t border-rose-100/40 line-clamp-2"
          >
            "{{ log.journal_text }}"
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
