'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

const tabs = [
  { label: 'Live', href: '' },
  { label: 'Heute', href: '/summary' },
  { label: 'Verlauf', href: '/trend' },
  { label: 'Geräte', href: '/devices' },
];

export function SiteNav({ siteId }: { siteId: string }) {
  const pathname = usePathname();

  return (
    <nav className="flex border-t border-blue-800">
      {tabs.map((tab) => {
        const href = `/sites/${siteId}${tab.href}`;
        const isActive = tab.href === ''
          ? pathname === `/sites/${siteId}`
          : pathname.startsWith(href);

        return (
          <Link
            key={tab.href}
            href={href}
            className={cn(
              'flex-1 text-center py-2.5 text-sm font-medium transition-colors',
              isActive
                ? 'text-white border-b-2 border-yellow-400'
                : 'text-blue-300 hover:text-white'
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
