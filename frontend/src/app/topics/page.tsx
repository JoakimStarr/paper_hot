'use client';

import { usePageTitle } from '@/lib/usePageTitle';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Layout from '@/components/Layout';
import { Loader2 } from 'lucide-react';
import ProjectList from './ProjectList';
import ProjectDetail from './ProjectDetail';

// 研究工作台：项目列表（默认）+ 项目详情（?project={id}，&step=1..5 深链）
export default function TopicsPage() {
  usePageTitle('选题中心');
  return (
    <Suspense fallback={
      <Layout>
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    }>
      <TopicsInner />
    </Suspense>
  );
}

function TopicsInner() {
  const searchParams = useSearchParams();
  const projectParam = searchParams.get('project');
  const pid = projectParam && /^\d+$/.test(projectParam) ? Number(projectParam) : null;
  const stepParam = searchParams.get('step');

  if (pid) {
    return <ProjectDetail projectId={pid} initialStep={stepParam && /^[1-5]$/.test(stepParam) ? Number(stepParam) : undefined} />;
  }
  return <ProjectList />;
}
