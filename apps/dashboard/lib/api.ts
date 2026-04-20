const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface CurrentReading {
  site_id: string;
  recorded_at: string;
  production_w: number;
  consumption_w: number;
  feed_in_w: number;
  draw_w: number;
  bess_power_w: number;
  bess_soc_pct: number | null;
  self_sufficiency_pct: number;
}

export interface DailySummary {
  site_id: string;
  date: string;
  production_kwh: number;
  consumption_kwh: number;
  feed_in_kwh: number;
  draw_kwh: number;
  self_sufficiency_pct: number;
  co2_avoided_kg: number;
  feed_in_revenue_chf: number;
}

export interface TrendPoint {
  bucket: string;
  production_kwh: number;
  consumption_kwh: number;
  feed_in_kwh: number;
  draw_kwh: number;
}

export interface TrendResponse {
  site_id: string;
  resolution: '15m' | 'hourly' | 'daily';
  points: TrendPoint[];
}

export interface Device {
  id: string;
  site_id: string;
  name: string;
  device_type: string;
  protocol: string;
  last_seen: string | null;
  active: boolean;
}

export interface GridStats {
  site_id: string;
  period: string;
  feed_in_kwh: number;
  draw_kwh: number;
  net_kwh: number;
  feed_in_revenue_chf: number;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    next: { revalidate: 30 },
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json();
}

export const api = {
  getCurrentReading: (siteId: string) =>
    fetchApi<CurrentReading>(`/sites/${siteId}/current`),

  getDailySummary: (siteId: string, day?: string) =>
    fetchApi<DailySummary>(`/sites/${siteId}/summary${day ? `?day=${day}` : ''}`),

  getTrend: (
    siteId: string,
    from: string,
    to?: string,
    resolution: '15m' | 'hourly' | 'daily' = 'hourly'
  ) => {
    const params = new URLSearchParams({ from, resolution });
    if (to) params.set('to', to);
    return fetchApi<TrendResponse>(`/sites/${siteId}/trend?${params}`);
  },

  getDevices: (siteId: string) =>
    fetchApi<Device[]>(`/sites/${siteId}/devices`),

  getGridStats: (siteId: string, period: 'today' | 'week' | 'month' = 'today') =>
    fetchApi<GridStats>(`/sites/${siteId}/grid?period=${period}`),
};
