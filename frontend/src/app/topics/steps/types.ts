import type { TopicProject } from '@/types/paper';

/** 每个向导步骤共享的 props。goStep 由 ProjectDetail 提供（跳步骤并持久化 current_step）。 */
export interface StepProps {
  project: TopicProject;
  onRefresh: () => Promise<void>;
  onPatch: (patch: Record<string, unknown>) => Promise<void>;
  runAi: (action: string, ideaText?: string, model?: string) => Promise<void>;
  goStep: (n: number) => void;
}
