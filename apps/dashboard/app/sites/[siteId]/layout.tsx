import Link from 'next/link';
import { SiteNav } from '@/components/SiteNav';

export default function SiteLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { siteId: string };
}) {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-10" style={{ backgroundColor: '#1a2d5a' }}>
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-white">⚡ KAMA</span>
            <span className="text-blue-300 text-sm hidden sm:block">Energie Dashboard</span>
          </div>
          <div className="text-xs text-blue-300 font-mono truncate max-w-[160px]">
            {params.siteId}
          </div>
        </div>
        <SiteNav siteId={params.siteId} />
      </header>

      {/* Content */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
        {children}
      </main>

      <footer className="text-center py-3 text-xs text-gray-400 border-t border-gray-100">
        KAMA GmbH · kama-power.ch
      </footer>
    </div>
  );
}
