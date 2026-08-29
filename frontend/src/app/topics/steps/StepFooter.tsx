import { ArrowRight } from 'lucide-react';

interface StepFooterProps {
  /** 当前步产出物是否已完成（决定提示语气） */
  stepDone: boolean;
  /** 未完成时展示的完成条件提示 */
  doneHint: string;
  /** 主按钮文案：非最后一步为「下一步：XXX」，最后一步由调用方直接传文案 */
  primaryLabel: string;
  onPrimary: () => void;
}

/**
 * 五步向导的统一底部主线引导：提示本步完成条件 + 「下一步」主按钮。
 * 由 ProjectDetail 挂在每步内容下方，步骤内部不感知导航。
 */
export default function StepFooter({ stepDone, doneHint, primaryLabel, onPrimary }: StepFooterProps) {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border p-3 ${
        stepDone
          ? 'border-green-200 dark:border-green-800/60 bg-green-50/60 dark:bg-green-900/10'
          : 'border-amber-200 dark:border-amber-800/60 bg-amber-50/60 dark:bg-amber-900/10'
      }`}
    >
      <p className={`text-xs flex-1 ${stepDone ? 'text-green-700 dark:text-green-300' : 'text-amber-700 dark:text-amber-300'}`}>
        {stepDone ? (
          <>本步产出已就绪，可以继续推进。</>
        ) : (
          <>未完成：{doneHint}。可以先跳过，稍后回来补。</>
        )}
      </p>
      <button
        onClick={onPrimary}
        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg transition-colors shrink-0"
      >
        {primaryLabel}
        <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  );
}
