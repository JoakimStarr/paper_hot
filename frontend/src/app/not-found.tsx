import Link from 'next/link';
import { FileQuestion } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4">
      <FileQuestion className="w-14 h-14 text-gray-300 mb-4" />
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">页面不存在</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">您访问的地址不存在或已被移除。</p>
      <Link
        href="/"
        className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition-colors"
      >
        返回首页
      </Link>
    </div>
  );
}
