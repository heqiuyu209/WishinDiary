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
  email?: string;
  /** 可选：注册时补录最近 2~4 个经期开始日期（升序、不重复、间隔 15~60 天、不晚于今天） */
  period_start_dates?: string[];
}

export interface LoginResponse extends StatusResponse {
  user_id?: number | null;
  username?: string | null;
}

export interface RegisterResponse extends StatusResponse {
  email_verification_required?: boolean;
  email_verification_sent?: boolean;
  user_id?: number | null;
  /** 本次注册补录写入的经期开始日期数量 */
  period_dates_recorded?: number | null;
}

export interface SessionResponse extends StatusResponse {
  user_id?: number | null;
  username?: string | null;
  is_admin?: boolean;
  email?: string | null;
}

export interface NotificationSettings extends StatusResponse {
  email: string | null;
  email_verified: boolean;
  pending_email: string | null;
  enabled: boolean;
  lead_days: 1 | 2 | 3;
  timezone: string;
  mail_available: boolean;
  last_delivery_state: string | null;
}

export interface NotificationPreferences {
  enabled: boolean;
  lead_days: 1 | 2 | 3;
  timezone: string;
}

export interface ResearchSummary extends StatusResponse {
  data: {
    reminder_states?: { state: string; count: number }[];
    users: number;
    total: number;
    completed: number;
    outside_range: number;
    missing_bleeding: number;
    users_with_ml_history: number;
    feature_samples: number;
    cycle_distribution: { days: number; count: number }[];
    history_distribution: { label: string; count: number }[];
  };
  evaluation: {
    available: boolean;
    message?: string;
    generated_at?: string;
    git_commit?: string;
    model_version?: string;
    model_matches_report?: boolean | null;
    temporal_holdout_status?: 'available' | 'unavailable' | 'not_applicable';
    dataset?: {
      source: string;
      total_samples: number;
      real_samples: number;
      synthetic_samples: number;
      n_users: number;
      calendar_provenance?: string[];
      calendar_features_enabled?: boolean | null;
    };
    metrics?: Record<string, Record<string, number>>;
  };
  forecast_evaluation?: ForecastEvaluation;
  recommendations: string[];
}

export type ForecastProtocol = 'existing_users' | 'unseen_users';
export type ForecastMethod = 'online_pipeline' | 'mean3' | 'median3' | 'ewma';
export type ForecastGroup = 'history' | 'volatility' | 'missing_bleeding';
export type ForecastIntervalMethod = 'rf_personalized' | 'basic_stats';

export interface ForecastIntervalScores {
  samples: number;
  coverage_pct?: number;
  mean_width_days?: number;
}

export interface ForecastIntervalComparison {
  test_samples: number;
  unavailable_samples: number;
  calibrated: ForecastIntervalScores;
  comparison: {
    samples: number;
    original: ForecastIntervalScores;
    calibrated: ForecastIntervalScores;
  };
}

export interface ForecastCalibrationMethod extends ForecastIntervalComparison {
  fits: { samples: number; rank: number; available: boolean; radius_days?: number }[];
}

export interface ForecastScores {
  samples: number;
  models: Partial<
    Record<
      ForecastMethod,
      {
        mae?: number;
        rmse?: number;
        bias_days?: number;
        hit_rate_within_2d?: number;
        hit_rate_within_3d?: number;
      }
    >
  >;
}

export interface ForecastEvaluation {
  available: boolean;
  message?: string;
  pipeline_matches_report?: boolean;
  generated_at?: string;
  git_commit?: string;
  cutoff?: string;
  time_windows?: {
    window_days: number;
    date_basis: 'forecast_anchor';
    last_candidate_date: string;
    end_exclusive: string;
  };
  dataset?: { source: string; total_cycles: number; n_users: number };
  calibration?: {
    method: 'absolute_residual_split';
    cutoff: string;
    target_coverage_pct: number;
    candidate_samples: number;
    labels_available_through: string | null;
    training_labels_available_through: string;
  };
  protocols?: Partial<
    Record<
      ForecastProtocol,
      ForecastScores & {
        n_splits?: number;
        training_samples?: number;
        excluded_unseen_cases?: number;
        candidate_samples?: number;
        abstained_samples?: number;
        skipped_empty_folds?: number;
        intervals?: Partial<
          Record<
            'rf_personalized' | 'basic_stats',
            { samples: number; coverage_pct?: number; mean_width_days?: number }
          >
        >;
        groups?: Partial<Record<ForecastGroup, ForecastBreakdownRow[]>>;
        time_windows?: (ForecastScores & {
          start: string;
          end_exclusive: string;
          interval_comparison: Record<ForecastIntervalMethod, ForecastIntervalComparison>;
        })[];
        calibration?: {
          target_coverage_pct: number;
          methods: Record<ForecastIntervalMethod, ForecastCalibrationMethod>;
        };
      }
    >
  >;
}

export interface ForecastBreakdownRow extends ForecastScores {
  label: string;
  interval_comparison?: Record<ForecastIntervalMethod, ForecastIntervalComparison>;
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
  data_quality_warnings?: string[] | null;
}

// ---------------------------------------------------------------------------
// Stats 模块（/api/v1/stats）—— 日历与看板共用
// ---------------------------------------------------------------------------

export type TrackingKind = 'unknown' | 'missed_tracking' | 'true_long_interval' | 'no_onset';

export interface CycleRead {
  cycle_id: number;
  start_date: string;
  end_date?: string | null;
  cycle_length?: number | null;
  bleeding_days?: number | null;
  tracking_kind?: TrackingKind | null;
  tracking_as_of_date?: string | null;
}

export interface DailyLogSummary {
  log_date: string;
  mood_level: number | null;
  cramps_severity: number | null;
  is_exercise: boolean | null;
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
  headache: number | null;
  bloat: number | null;
  breast_tenderness: number | null;
  fatigue: number | null;
}

export interface DailyLogRequest {
  log_date: string;
  mood_level?: number | null;
  cramps_severity?: number | null;
  is_exercise?: boolean | null;
  is_intercourse?: boolean | null;
  exercise_type?: string | null;
  exercise_minutes?: number | null;
  exercise_intensity?: number | null;
  stress_level?: number | null;
  diet_tag?: string | null;
  journal_text?: string | null;
  sleep_duration_minutes?: number | null;
  sleep_quality?: number | null;
  sleep_start_minutes?: number | null;
  is_late_night?: boolean | null;
  is_night_shift?: boolean | null;
  is_medication?: boolean | null;
  medication_note?: string | null;
  symptom_levels?: SymptomLevels | null;
}

export interface DailyLogData extends DailyLogRequest {
  log_date: string;
  mood_level: number | null;
  cramps_severity: number | null;
  is_exercise: boolean | null;
  is_intercourse: boolean | null;
  exercise_minutes: number | null;
  sleep_duration_minutes: number | null;
  sleep_quality: number | null;
  is_late_night: boolean | null;
  is_medication: boolean | null;
  medication_note: string | null;
  symptom_levels: SymptomLevels;
  recording_version?: number;
  recorded_at?: string | null;
  updated_at?: string | null;
}

export interface DailyLogResponse extends StatusResponse {
  ai_health_advice: string[];
  advice_source?: string;
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
