import { Suspense } from 'react';
import { api } from '@/lib/api';
import { TrendChart } from '@/components/TrendChart';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { subDays, format } from 'date-fns';

export const dynamic = 'force-dynamic';

async function TrendData({
  siteId,
  from,
  to,
  resolution,
}: {
  siteId: string;
  from: string;
  to: string;
  resolution: '15m' | 'hourly' | 'daily';
}) {
  try {
    const trend = await api.getTrend(siteId, from, to, resolution);
    return <TrendChart trend={trend} from={from} to={to} siteId={siteId} />;
  } catch {
    return (
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-6 text-center">
        <p className="text-amber-700 font-medium">Keine Verlaufsdaten verfügbar</p>
      </div>
    );
  }
}

export default function TrendPage({
  params,
  searchParams,
}: {
  params: { siteId: string };
  searchParams: { from?: string; to?: string; resolution?: string };
}) {
  const to = searchParams.to || format(new Date(), "yyyy-MM-dd'T'HH:mm:ss'Z'");
  const from = searchParams.from || format(subDays(new Date(), 7), "yyyy-MM-dd'T'00:00:00'Z'");
  const resolution = (searchParams.resolution as '15m' | 'hourly' | 'daily') || 'daily';

  return (
    <div>
      <h1 className="text-lg font-semibold text-gray-700 mb-4">Energieverlauf</h1>
      <Suspense fallback={<LoadingSpinner />}>
        <TrendData
          siteId={params.siteId}
          from={from}
          to={to}
          resolution={resolution}
        />
      </Suspense>
    </div>
  );
}
