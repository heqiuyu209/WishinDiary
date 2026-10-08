/**
 * 日期工具函数 —— 从 CalendarView 抽出的纯函数，便于单元测试与复用。
 * 日期用设备本地午夜表示；账户日期先按指定时区提取年月日。
 */

export const addDays = (date: Date, days: number): Date => {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
};

export type DateLike = Date | string | null | undefined;

export const toLocalDate = (value: DateLike): Date | null => {
  if (!value) return null;

  if (value instanceof Date) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  if (typeof value === 'string') {
    const [year, month, day] = value.slice(0, 10).split('-').map(Number);
    if (!year || !month || !day) return null;
    return new Date(year, month - 1, day);
  }

  return null;
};

export const formatDate = (date: Date): string => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

export const isOnOrAfter = (
  left: Date | null | undefined,
  right: Date | null | undefined,
): boolean => !!left && !!right && left.getTime() >= right.getTime();

export const isAfter = (left: Date | null | undefined, right: Date | null | undefined): boolean =>
  !!left && !!right && left.getTime() > right.getTime();

export const today = (timezone?: string, now = new Date()): Date => {
  if (timezone) {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(now);
    const part = (type: string) => Number(parts.find((value) => value.type === type)!.value);
    return new Date(part('year'), part('month') - 1, part('day'));
  }
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};
