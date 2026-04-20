'use client';

import { useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { useRouter } from 'next/navigation';
import type { TrendResponse } from '@/lib/api';
import { format, subDays, subWeeks, subMonths } from 'date-fns';

const PRESETS = [
  { label: '7 Tage', days: 7, resolution: 'daily' as const },
  { label: '30 Tage', days: 30, resolution: 'daily' as const },
  { label: '90 Tage', days: 90, resolution: 'daily' as const },
];

function exportCsv(trend: TrendResponse) {
  const header = 'Zeit,Produktion kWh,Verbrauch kWh,Einspeisung kWh,Bezug kWh';
  const rows = trend.points.map(
    (p) => `${p.bucket},${p.production_kwh},${p.consumption_kwh},${p.feed_in_kwh},${p.draw_kwh}`
  );
  const csv = [header, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `kama-energie-${trend.site_id}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function TrendChart({
  trend,
  from,
  to,
  siteId,
}: {
  trend: TrendResponse;
  from: string;
  to: string;
  siteId: string;
}) {
  const router = useRouter();

  function applyPreset(days: number, resolution: 'daily' | 'hourly') {
    const toDate = format(new Date(), "yyyy-MM-dd'T'HH:mm:ss'Z'");
    const fromDate = format(subDays(new Date(), days), "yyyy-MM-dd'T'00:00:00'Z'");
    router.push(`/sites/${siteId}/trend?from=${fromDate}&to=${toDate}&resolution=${resolution}`);
  }

  const labels = trend.points.map((p) => {
    const d = new Date(p.bucket);
    return trend.resolution === 'daily'
      ? d.toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit' })
      : d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
  });

  const areaOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown[]) => {
        const items = params as { seriesName: string; value: number; axisValue: string }[];
        if (!items.length) return '';
        return `<b>${items[0].axisValue}</b><br/>` +
          items.map((p) => `${p.seriesName}: ${p.value.toFixed(2)} kWh`).join('<br/>');
      },
    },
    legend: {
      data: ['Produktion', 'Verbrauch', 'Einspeisung', 'Bezug'],
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: { top: 16, bottom: 60, left: 52, right: 16 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        fontSize: 10,
        interval: Math.max(0, Math.floor(labels.length / 10) - 1),
        rotate: labels.length > 20 ? 30 : 0,
      },
      boundaryGap: false,
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
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.3, color: '#f5a623' },
        itemStyle: { color: '#f5a623' },
        lineStyle: { color: '#f5a623', width: 2 },
        data: trend.points.map((p) => p.production_kwh),
        symbol: 'none',
      },
      {
        name: 'Verbrauch',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.15, color: '#1a2d5a' },
        itemStyle: { color: '#1a2d5a' },
        lineStyle: { color: '#1a2d5a', width: 2 },
        data: trend.points.map((p) => p.consumption_kwh),
        symbol: 'none',
      },
      {
        name: 'Einspeisung',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#22c55e' },
        lineStyle: { color: '#22c55e', width: 1.5, type: 'dashed' },
        data: trend.points.map((p) => p.feed_in_kwh),
        symbol: 'none',
      },
      {
        name: 'Bezug',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#ef4444' },
        lineStyle: { color: '#ef4444', width: 1.5, type: 'dashed' },
        data: trend.points.map((p) => p.draw_kwh),
        symbol: 'none',
      },
    ],
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => applyPreset(p.days, p.resolution)}
            className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 transition-colors"
          >
            {p.label}
          </button>
        ))}
        <button
          onClick={() => exportCsv(trend)}
          className="ml-auto px-3 py-1.5 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 transition-colors flex items-center gap-1"
        >
          ↓ CSV
        </button>
      </div>

      {/* Chart */}
      <div className="stat-card">
        {trend.points.length > 0 ? (
          <ReactECharts option={areaOption} style={{ height: 320 }} />
        ) : (
          <p className="text-sm text-gray-400 py-12 text-center">
            Keine Daten für den gewählten Zeitraum.
          </p>
        )}
      </div>

      <p className="text-xs text-gray-400 text-right">
        {trend.points.length} Datenpunkte · Auflösung: {trend.resolution}
      </p>
    </div>
  );
}
