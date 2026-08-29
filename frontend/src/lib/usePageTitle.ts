'use client';

import { useEffect } from 'react';

const APP_NAME = 'PaperPulse';

/**
 * 设置浏览器标签页标题：每个页面按自身内容命名（而非全局统一标题）。
 * title 传 undefined 时回落为应用名；动态页面（论文详情/项目详情）传实体标题。
 */
export function usePageTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}
