import { describe, expect, it } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import { extractApiErrorMessage } from '../../shared/api/httpClient';
import type { ApiErrorBody } from '../../types/api';

function makeError(
  status: number,
  body: ApiErrorBody | undefined,
  url = '/api/v1/prediction',
): AxiosError<ApiErrorBody> {
  const config = { url, headers: new AxiosHeaders() };
  return new AxiosError('Request failed', 'ERR_BAD_RESPONSE', config, undefined, {
    status,
    statusText: 'error',
    headers: {},
    config,
    data: body,
  }) as AxiosError<ApiErrorBody>;
}

describe('extractApiErrorMessage', () => {
  it('提取后端统一 error.message', () => {
    const err = makeError(422, {
      error: { code: 'VALIDATION_ERROR', message: '日志格式非法' },
    });
    expect(extractApiErrorMessage(err, 'fallback')).toBe('日志格式非法');
  });

  it('message 缺失时回退 detail 字符串', () => {
    const err = makeError(500, {
      error: { code: 'INTERNAL', message: '', detail: '数据库不可用' },
    });
    expect(extractApiErrorMessage(err, 'fallback')).toBe('数据库不可用');
  });

  it('detail 为数组时逐条取 msg 并以分号连接', () => {
    const err = makeError(422, {
      error: {
        code: 'VALIDATION_ERROR',
        message: '',
        detail: [{ msg: '用户名至少 3 位' }, { msg: '密码必填' }],
      },
    });
    expect(extractApiErrorMessage(err, 'fallback')).toBe('用户名至少 3 位；密码必填');
  });

  it('无关错误返回 fallback', () => {
    expect(extractApiErrorMessage(new Error('boom'), '网络异常')).toBe('网络异常');
    expect(extractApiErrorMessage(null, 'fallback')).toBe('fallback');
  });
});
