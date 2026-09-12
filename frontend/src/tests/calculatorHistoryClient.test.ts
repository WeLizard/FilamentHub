import { afterEach, describe, expect, it, vi } from 'vitest';
import { CanceledError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios';

import api, { calculatorAPI } from '../api/client';

const originalAdapter = api.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = originalAdapter;
});

describe('calculator history client', () => {
  it('passes cursor parameters and AbortSignal to the transport', async () => {
    const captured: { config?: InternalAxiosRequestConfig } = {};
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      captured.config = config;
      return new Promise((_resolve, reject) => {
        config.signal?.addEventListener?.('abort', () => reject(new CanceledError()), { once: true });
      });
    }) as AxiosAdapter;
    const controller = new AbortController();

    const request = calculatorAPI.listHistory(
      { size: 20, cursor: 'opaque-cursor' },
      controller.signal,
    );

    await vi.waitFor(() => expect(captured.config).toBeDefined());
    expect(captured.config?.params).toEqual({ size: 20, cursor: 'opaque-cursor' });
    expect(captured.config?.signal).toBeDefined();
    controller.abort();
    expect(captured.config?.signal?.aborted).toBe(true);
    await expect(request).rejects.toBeInstanceOf(CanceledError);
  });
});
