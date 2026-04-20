import { Suspense } from 'react';
import { api } from '@/lib/api';
import { DeviceTable } from '@/components/DeviceTable';
import { LoadingSpinner } from '@/components/LoadingSpinner';

export const dynamic = 'force-dynamic';

async function DevicesData({ siteId }: { siteId: string }) {
  try {
    const devices = await api.getDevices(siteId);
    return <DeviceTable devices={devices} />;
  } catch {
    return (
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-6 text-center">
        <p className="text-amber-700 font-medium">Gerätedaten nicht verfügbar</p>
      </div>
    );
  }
}

export default function DevicesPage({ params }: { params: { siteId: string } }) {
  return (
    <div>
      <h1 className="text-lg font-semibold text-gray-700 mb-4">Gerätestatus</h1>
      <Suspense fallback={<LoadingSpinner />}>
        <DevicesData siteId={params.siteId} />
      </Suspense>
    </div>
  );
}
