import Layout from '@/components/Layout';
import PageSkeleton from '@/components/PageSkeleton';

/** 路由加载骨架：先进入页面壳，内容随后懒加载。 */
export default function Loading() {
  return (
    <Layout>
      <PageSkeleton />
    </Layout>
  );
}
