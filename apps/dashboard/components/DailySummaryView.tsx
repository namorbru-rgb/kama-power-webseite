'use client';

import ReactECharts from 'echarts-for-react';
import type { DailySummary, TrendResponse } from '@/lib/api';
import { fmtKwh, fmtChf, fmtKg, fmtPct } from '@/lib/utils';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

function KpiCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="stat-card">
      <p className="stat-label">{label}</p>
      <p className={`stat-value mt-1 ${accent ? '' : ''}`} style={accent ? { color: '#f5a623' } : undefined}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

export function DailySummaryView({
  summary,
  trend,
}: {
  summary: DailySummary;
  trend: TrendResponse;
}) {
  const hours = trend.points.map((p) => {
    const d = new Date(p.bucket);
    return `${d.getUTCHours().toString().padStart(2, '0')}:00`;
  });

  const barOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown[]) => {
        const items = (params as { seriesName: string; value: number }[]);
        return items.map((p) => `${p.seriesName}: ${p.value.toFixed(2)} kWh`).join('<br/>');
      },
    },
    legend: {
      data: ['Produktion', 'Verbrauch', 'Einspeisung', 'Bezug'],
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: { top: 16, bottom: 56, left: 48, right: 16 },
    xAxis: {
      type: 'category',
      data: hours,
      axisLabel: { fontSize: 10, interval: 3 },
    },
    yAxis: {
      type: 'value',
      name: 'kWh',
      nameTextStyle: { fontSize: 10 },
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        name: 'Produktion',
        type: 'bar',
        stack: 'gen',
        itemStyle: { color: '#f5a623' },
        data: trend.points.map((p) => p.production_kwh),
      },
      {
        name: 'Einspeisung',
        type: 'bar',
        stack: 'gen',
        itemStyle: { color: '#fbbf24' },
        data: trend.points.map((p) => p.feed_in_kwh),
      },
      {
        name: 'Verbrauch',
        type: 'bar',
        stack: 'cons',
        itemStyle: { color: '#1a2d5a' },
        data: trend.points.map((p) => p.consumption_kwh),
      },
      {
        name: 'Bezug',
        type: 'bar',
        stack: 'cons',
        itemStyle: { color: '#2d4a8a' },
        data: trend.points.map((p) => p.draw_kwh),
      },
    ],
  };

  return (
    <div className="space-y-4">
      {/* KPI grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Produktion" value={fmtKwh(summary.production_kwh)} accent />
        <KpiCard label="Verbrauch" value={fmtKwh(summary.consumption_kwh)} />
        <KpiCard
          label="Eigenversorgung"
          value={fmtPct(summary.self_sufficiency_pct)}
          sub="Lokale Produktion / Verbrauch"
        />
        <KpiCard
          label="CO₂ vermieden"
          value={fmtKg(summary.co2_avoided_kg)}
          sub="Swiss Grid Faktor"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          label="Netz-Einspeisung"
          value={fmtKwh(summary.feed_in_kwh)}
          sub={`Vergütung: ${fmtChf(summary.feed_in_revenue_chf)}`}
          accent
        />
        <KpiCard label="Netz-Bezug" value={fmtKwh(summary.draw_kwh)} />
      </div>

      {/* Hourly bar chart */}
      <div className="stat-card">
        <p className="stat-label mb-3">Stündliche Energie (kWh)</p>
        {trend.points.length > 0 ? (
          <ReactECharts option={barOption} style={{ height: 260 }} />
        ) : (
          <p className="text-sm text-gray-400 py-8 text-center">Noch keine Stundendaten.</p>
        )}
      </div>
    </div>
  );
}
