import { Suspense } from 'react';
import { api } from '@/lib/api';
import { LiveOverview } from '@/components/LiveOverview';
import { LoadingSpinner } from '@/components/LoadingSpinner';

export const dynamic = 'force-dynamic';

async function LiveData({ siteId }: { siteId: string }) {
  try {
    const [reading, grid] = await Promise.all([
      api.getCurrentReading(siteId),
      api.getGridStats(siteId, 'today'),
    ]);
    return <LiveOverview reading={reading} gridToday={grid} />;
  } catch {
    return (
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-6 text-center">
        <p className="text-amber-700 font-medium">Keine aktuellen Daten verfügbar</p>
        <p className="text-amber-500 text-sm mt-1">
          Der Standort liefert gerade keine Messwerte. Letzte bekannte Werte werden angezeigt,
          sobald Verbindung besteht.
        </p>
      </div>
    );
  }
}

export default function LivePage({ params }: { params: { siteId: string } }) {
  return (
    <div>
      <h1 className="text-lg font-semibold text-gray-700 mb-4">Live-Übersicht</h1>
      <Suspense fallback={<LoadingSpinner />}>
        <LiveData siteId={params.siteId} />
      </Suspense>
      <p className="text-xs text-gray-400 mt-4 text-right">
        Aktualisiert alle 30 Sekunden · {new Date().toLocaleTimeString('de-CH')}
      </p>
    </div>
  );
}
