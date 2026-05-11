export default function SkeletonCard() {
  return (
    <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200 animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-3/4 mb-3" />
      <div className="h-4 bg-gray-200 rounded w-full mb-2" />
      <div className="h-4 bg-gray-200 rounded w-2/3 mb-4" />
      <div className="flex gap-2 mb-3">
        <div className="h-6 bg-gray-200 rounded w-16" />
        <div className="h-6 bg-gray-200 rounded w-20" />
        <div className="h-6 bg-gray-200 rounded w-14" />
      </div>
      <div className="flex justify-between">
        <div className="h-4 bg-gray-200 rounded w-32" />
        <div className="h-4 bg-gray-200 rounded w-24" />
      </div>
    </div>
  );
}