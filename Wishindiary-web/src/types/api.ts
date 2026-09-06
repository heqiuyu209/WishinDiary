/**
 * API 契约类型 —— 与后端 wishindiary-api（FastAPI + Pydantic）对齐。
 *
 * 后端统一约定（见 app/schemas/common.py 与 app/core/errors.py）：
 * - 成功响应：{ status, message?, ...业务字段 }
 * - 错误响应：{ error: { code, message, detail? } }
 */

/** 统一错误响应结构 */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}

/** 成功响应基类 */
export interface StatusResponse {
  status: string;
  message?: string | null;
}

// ---------------------------------------------------------------------------
// Auth 模块（/api/v1/auth/*）
// ---------------------------------------------------------------------------

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  /** 可选：注册时补录最近 2~4 个经期开始日期（升序、不重复、间隔 15~60 天、不晚于今天） */
  period_start_dates?: string[];
}

export interface LoginResponse extends StatusResponse {
  user_id?: number | null;
  username?: string | null;
}

export interface RegisterResponse extends StatusResponse {
  user_id?: number | null;
  /** 本次注册补录写入的经期开始日期数量 */
  period_dates_recorded?: number | null;
}

export interface SessionResponse extends StatusResponse {
  user_id?: number | null;
  username?: string | null;
}

// ---------------------------------------------------------------------------
// Prediction 模块（/api/v1/prediction）
// ---------------------------------------------------------------------------

export interface ConfidenceInterval {
  low: number;
  high: number;
  note?: string | null;
}

export interface PredictionResponseData {
  last_period_start: string;
  predicted_cycle_length: number;
  raw_predicted_cycle_length?: number | null;
  next_period_start: string;
  next_period_end: string;
  ovulation_date: string;
  fertile_window_start: string;
  fertile_window_end: string;
  medical_guardrail_note?: string | null;
  data_quality_warnings?: string[] | null;
  features_info: string;
  model_version: string;
  confidence_interval?: ConfidenceInterval | null;
  disclaimer: string;
}

export interface PredictionResponse extends StatusResponse {
  prediction: PredictionResponseData | null;
}

// ---------------------------------------------------------------------------
// Stats 模块（/api/v1/stats）—— 日历与看板共用
// ---------------------------------------------------------------------------

export interface CycleRead {
  cycle_id: number;
  start_date: string;
  end_date?: string | null;
  cycle_length?: number | null;
  bleeding_days?: number | null;
}

export interface DailyLogSummary {
  log_date: string;
  mood_level: number;
  cramps_severity: number;
  is_exercise: boolean;
  exercise_type?: string | null;
  journal_text?: string | null;
}

export interface StatsResponse extends StatusResponse {
  cycles: CycleRead[];
  recent_logs: DailyLogSummary[];
}

// ---------------------------------------------------------------------------
// 周期写入模块（/api/v1/log_start、log_end、cycles/*）
// ---------------------------------------------------------------------------

export interface LogStartRequest {
  start_date: string;
}

export interface LogEndRequest {
  end_date: string;
  cycle_id?: number | null;
}

export interface CycleUpdateRequest {
  start_date?: string | null;
  end_date?: string | null;
}

export type CycleOperationResponse = StatusResponse;

// ---------------------------------------------------------------------------
// 每日日志模块（/api/v1/daily_log）
// ---------------------------------------------------------------------------

export interface SymptomLevels {
  headache: number;
  bloat: number;
  breast_tenderness: number;
  fatigue: number;
}

export interface DailyLogRequest {
  log_date: string;
  mood_level: number;
  cramps_severity: number;
  is_exercise: boolean;
  is_intercourse: boolean;
  exercise_type?: string | null;
  exercise_minutes: number;
  diet_tag?: string | null;
  journal_text?: string | null;
  // --- 新增自记录维度（睡眠/熬夜、用药、症状明细）---
  sleep_duration_minutes?: number;
  sleep_quality?: number;
  is_late_night?: boolean;
  is_medication?: boolean;
  medication_note?: string | null;
  symptom_levels?: SymptomLevels | null;
}

export interface DailyLogData extends DailyLogRequest {
  log_date: string;
  mood_level: number;
  cramps_severity: number;
  is_exercise: boolean;
  is_intercourse: boolean;
  exercise_minutes: number;
  sleep_duration_minutes: number;
  sleep_quality: number;
  is_late_night: boolean;
  is_medication: boolean;
  medication_note: string | null;
  symptom_levels: SymptomLevels;
}

export interface DailyLogResponse extends StatusResponse {
  ai_health_advice: string[];
}

export interface DailyLogReadResponse extends StatusResponse {
  log: DailyLogData | null;
}

// ---------------------------------------------------------------------------
// 报告模块（/api/v1/report）
// ---------------------------------------------------------------------------

export interface ReportData {
  average_cycle_length: number;
  ai_prediction_accuracy_days: number | string;
  total_recorded_cycles: number;
  cramps_evaluation: string;
  doctor_advice_summary: string;
  cycle_regularity: string;
  data_readiness: string;
  cycle_length_hint: string;
  latest_prediction_error_days: number | null;
  disclaimer: string;
}

export interface ReportResponse extends StatusResponse {
  report: ReportData;
}
