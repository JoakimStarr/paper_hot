'use client';

import { useEffect } from 'react';
import { logClientError } from '@/lib/api';

/** 全局前端错误上报（日志系统）：
 *  捕获 window error 与未捕获 Promise 拒绝，上报到后端 error_logs（source=frontend）。
 *  仅注册监听器、不渲染任何 UI，挂在 Layout 根部即可全站生效。 */
export default function ClientErrorReporter() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      logClientError(event.message || 'window error', event.error?.stack || '');
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const message = reason instanceof Error ? reason.message : String(reason || 'Unhandled promise rejection');
      const stack = reason instanceof Error ? reason.stack : '';
      logClientError(message, stack);
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);
  return null;
}
