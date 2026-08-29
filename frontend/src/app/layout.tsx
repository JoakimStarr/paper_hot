import type { Metadata } from 'next';
import '../styles/globals.css';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { ThemeProvider } from '@/contexts/ThemeContext';
import ToastProvider from '@/components/Toast';

export const metadata: Metadata = {
  title: 'PaperPulse',
  description: 'A platform to discover and understand trending research papers',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <head>
        {/* 在首帧渲染前应用暗色主题与已保存语言，避免闪烁/语言错位（FOUC） */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}try{var l=localStorage.getItem('language');if(l==='en'||l==='zh'){document.documentElement.lang=l}}catch(e2){}})();`,
          }}
        />
      </head>
      <body>
        <ThemeProvider>
          <LanguageProvider>
            <ToastProvider>
              {children}
            </ToastProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
