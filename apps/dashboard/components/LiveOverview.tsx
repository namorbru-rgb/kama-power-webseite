'use client';

import ReactECharts from 'echarts-for-react';
import type { CurrentReading, GridStats } from '@/lib/api';
import { fmtW, fmtKwh, fmtChf, fmtPct, isStale } from '@/lib/utils';

function GaugeCard({
  label,
  value,
  max,
  color,
  unit,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
  unit: string;
}) {
  const option = {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max,
        radius: '85%',
        progress: { show: true, width: 14, itemStyle: { color } },
        axisLine: { lineStyle: { width: 14, color: [[1, '#e5e7eb']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        detail: {
          valueAnimation: true,
          formatter: (v: number) => `${(v / 1000).toFixed(1)}\n${unit}`,
          fontSize: 18,
          fontWeight: 'bold',
          color: '#111827',
          offsetCenter: [0, '10%'],
          lineHeight: 22,
        },
        data: [{ value: Math.max(0, value) }],
      },
    ],
  };

  return (
    <div className="stat-card flex flex-col items-center">
      <ReactECharts option={option} style={{ height: 160, width: '100%' }} />
      <p className="stat-label -mt-2">{label}</p>
    </div>
  );
}

function StatRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span
        className={`text-sm font-semibold ${accent ? 'text-kama-yellow' : 'text-gray-800'}`}
      >
        {value}
      </span>
    </div>
  );
}

export function LiveOverview({
  reading,
  gridToday,
}: {
  reading: CurrentReading;
  gridToday: GridStats;
}) {
  const stale = isStale(reading.recorded_at);
  const maxW = Math.max(reading.production_w, reading.consumption_w, 10000);

  return (
    <div className="space-y-4">
      {stale && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-2 text-sm text-amber-700">
          ⚠ Daten sind älter als 5 Minuten — Verbindung prüfen.
        </div>
      )}

      {/* Gauges */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <GaugeCard
          label="Produktion"
          value={reading.production_w}
          max={maxW}
          color="#f5a623"
          unit="kW"
        />
        <GaugeCard
          label="Verbrauch"
          value={reading.consumption_w}
          max={maxW}
          color="#1a2d5a"
          unit="kW"
        />
        <div className="stat-card flex flex-col justify-center col-span-2 sm:col-span-1">
          <p className="stat-label">Eigenversorgung</p>
          <p className="stat-value" style={{ color: '#f5a623' }}>
            {fmtPct(reading.self_sufficiency_pct)}
          </p>
          {reading.bess_soc_pct !== null && (
            <div className="mt-3">
              <p className="stat-label text-xs">Batterie</p>
              <div className="relative h-3 bg-gray-100 rounded-full mt-1 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${reading.bess_soc_pct}%`,
                    backgroundColor:
                      reading.bess_soc_pct > 50
                        ? '#22c55e'
                        : reading.bess_soc_pct > 20
                        ? '#f5a623'
                        : '#ef4444',
                  }}
                />
              </div>
              <p className="text-xs text-gray-400 mt-0.5 text-right">
                {reading.bess_soc_pct.toFixed(0)}% SOC
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Flow details */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="stat-card">
          <p className="stat-label mb-2">Netz</p>
          <StatRow label="Einspeisung" value={fmtW(reading.feed_in_w)} accent />
          <StatRow label="Bezug" value={fmtW(reading.draw_w)} />
          {reading.bess_power_w !== 0 && (
            <StatRow
              label={reading.bess_power_w > 0 ? 'Batterie lädt' : 'Batterie entlädt'}
              value={fmtW(Math.abs(reading.bess_power_w))}
            />
          )}
        </div>
        <div className="stat-card">
          <p className="stat-label mb-2">Heute (Bilanz)</p>
          <StatRow label="Einspeisung" value={fmtKwh(gridToday.feed_in_kwh)} accent />
          <StatRow label="Bezug" value={fmtKwh(gridToday.draw_kwh)} />
          <StatRow label="Einspeisevergütung" value={fmtChf(gridToday.feed_in_revenue_chf)} />
        </div>
      </div>
    </div>
  );
}
