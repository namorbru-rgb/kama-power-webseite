import { Suspense } from 'react';
import { api } from '@/lib/api';
import { DailySummaryView } from '@/components/DailySummaryView';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { format, subDays } from 'date-fns';

export const dynamic = 'force-dynamic';

async function SummaryData({ siteId, day }: { siteId: string; day?: string }) {
  try {
    // Fetch today's summary + hourly trend for the bar chart
    const today = day || format(new Date(), 'yyyy-MM-dd');
    const dayStart = `${today}T00:00:00Z`;
    const dayEnd = `${today}T23:59:59Z`;

    const [summary, trend] = await Promise.all([
      api.getDailySummary(siteId, today),
      api.getTrend(siteId, dayStart, dayEnd, 'hourly'),
    ]);
    return <DailySummaryView summary={summary} trend={trend} />;
  } catch {
    return (
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-6 text-center">
        <p className="text-amber-700 font-medium">Keine Tagesdaten verfügbar</p>
        <p className="text-amber-500 text-sm mt-1">Noch keine Messwerte für heute.</p>
      </div>
    );
  }
}

export default function SummaryPage({ params }: { params: { siteId: string } }) {
  const today = format(new Date(), 'dd.MM.yyyy');
  return (
    <div>
      <h1 className="text-lg font-semibold text-gray-700 mb-1">Tageszusammenfassung</h1>
      <p className="text-sm text-gray-400 mb-4">{today}</p>
      <Suspense fallback={<LoadingSpinner />}>
        <SummaryData siteId={params.siteId} />
      </Suspense>
    </div>
  );
}
