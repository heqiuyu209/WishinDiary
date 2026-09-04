import { describe, expect, it } from 'vitest';
import {
  addDays,
  formatDate,
  isAfter,
  isOnOrAfter,
  toLocalDate,
  today,
} from '../../shared/utils/date';

describe('shared/utils/date', () => {
  it('addDays 正确处理跨月与跨年', () => {
    const base = new Date(2026, 0, 31); // 2026-01-31
    const next = addDays(base, 1);
    expect(formatDate(next)).toBe('2026-02-01');

    const yearEnd = new Date(2026, 11, 31); // 2026-12-31
    expect(formatDate(addDays(yearEnd, 1))).toBe('2027-01-01');
  });

  it('toLocalDate 解析 ISO 字符串并剥离时间', () => {
    const parsed = toLocalDate('2026-09-02T08:00:00');
    expect(parsed).not.toBeNull();
    expect(formatDate(parsed!)).toBe('2026-09-02');

    const parsedDateOnly = toLocalDate('2026-09-02');
    expect(formatDate(parsedDateOnly!)).toBe('2026-09-02');

    expect(toLocalDate('')).toBeNull();
    expect(toLocalDate(null)).toBeNull();
    expect(toLocalDate(undefined)).toBeNull();
  });

  it('toLocalDate 处理 Date 时仅保留年月日', () => {
    const input = new Date(2026, 8, 2, 23, 59, 59);
    const result = toLocalDate(input);
    expect(result?.getHours()).toBe(0);
    expect(result?.getMinutes()).toBe(0);
    expect(formatDate(result!)).toBe('2026-09-02');
  });

  it('formatDate 输出 YYYY-MM-DD 并补零', () => {
    expect(formatDate(new Date(2026, 0, 5))).toBe('2026-01-05');
    expect(formatDate(new Date(2026, 11, 31))).toBe('2026-12-31');
  });

  it('isOnOrAfter / isAfter 正确处理边界', () => {
    const a = new Date(2026, 8, 2);
    const b = new Date(2026, 8, 2);
    expect(isOnOrAfter(a, b)).toBe(true);
    expect(isAfter(a, b)).toBe(false);
    expect(isAfter(new Date(2026, 8, 3), b)).toBe(true);
    expect(isOnOrAfter(null, b)).toBe(false);
    expect(isAfter(a, undefined)).toBe(false);
  });

  it('today 返回本地当日且时间归零', () => {
    const result = today();
    expect(result.getHours()).toBe(0);
    expect(formatDate(result)).toBe(formatDate(new Date()));
  });
});
