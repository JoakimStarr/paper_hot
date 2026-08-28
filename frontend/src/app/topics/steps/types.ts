import type { TopicProject } from '@/types/paper';

/** 每个向导步骤共享的 props。 */
export interface StepProps {
  project: TopicProject;
  onRefresh: () => Promise<void>;
  onPatch: (patch: Record<string, unknown>) => Promise<void>;
  runAi: (action: string, ideaText?: string) => Promise<void>;
}
