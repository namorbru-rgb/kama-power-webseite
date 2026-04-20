import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtW(watts: number): string {
  if (Math.abs(watts) >= 1000) {
    return `${(watts / 1000).toFixed(1)} kW`;
  }
  return `${Math.round(watts)} W`;
}

export function fmtKwh(kwh: number): string {
  return `${kwh.toFixed(1)} kWh`;
}

export function fmtChf(chf: number): string {
  return `CHF ${chf.toFixed(2)}`;
}

export function fmtKg(kg: number): string {
  return `${kg.toFixed(1)} kg`;
}

export function fmtPct(pct: number): string {
  return `${pct.toFixed(0)}%`;
}

export function isStale(isoDate: string | null, thresholdMs = 300_000): boolean {
  if (!isoDate) return true;
  return Date.now() - new Date(isoDate).getTime() > thresholdMs;
}
