import SkeletonCard from '@/components/SkeletonCard';

/** 页面级骨架屏：进入路由时壳子立即渲染，内容随后懒加载。 */
export default function PageSkeleton() {
  return (
    <div>
      <div className="mb-6">
        <div className="h-7 sm:h-8 bg-gray-200 dark:bg-gray-700 rounded w-48 mb-2 animate-pulse" />
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-72 animate-pulse" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:gap-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  );
}
