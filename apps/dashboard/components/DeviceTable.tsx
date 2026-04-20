import type { Device } from '@/lib/api';
import { isStale } from '@/lib/utils';

const DEVICE_TYPE_LABELS: Record<string, string> = {
  inverter: 'Wechselrichter',
  bess: 'Batteriespeicher',
  grid_meter: 'Netzzähler',
  smart_meter: 'Smartmeter',
  weather_station: 'Wetterstation',
};

const PROTOCOL_LABELS: Record<string, string> = {
  solarman_v5: 'SolarmanV5',
  modbus_tcp: 'Modbus TCP',
  modbus_rtu: 'Modbus RTU',
  mqtt: 'MQTT',
  http: 'HTTP',
};

function StatusBadge({ lastSeen }: { lastSeen: string | null }) {
  const offline = isStale(lastSeen, 5 * 60_000);
  return (
    <span className={offline ? 'badge-offline' : 'badge-online'}>
      <span className={`w-1.5 h-1.5 rounded-full ${offline ? 'bg-red-500' : 'bg-green-500'}`} />
      {offline ? 'Offline' : 'Online'}
    </span>
  );
}

export function DeviceTable({ devices }: { devices: Device[] }) {
  if (devices.length === 0) {
    return (
      <div className="stat-card text-center py-12">
        <p className="text-gray-400">Keine Geräte konfiguriert.</p>
        <p className="text-xs text-gray-300 mt-1">
          Geräte werden beim Edge Agent registriert.
        </p>
      </div>
    );
  }

  return (
    <div className="stat-card overflow-x-auto p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-left">
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Gerät</th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide hidden sm:table-cell">Typ</th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide hidden md:table-cell">Protokoll</th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide hidden sm:table-cell">Zuletzt gesehen</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((device) => (
            <tr key={device.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 font-medium text-gray-800">
                {device.name}
                <p className="text-xs text-gray-400 sm:hidden">
                  {DEVICE_TYPE_LABELS[device.device_type] || device.device_type}
                </p>
              </td>
              <td className="px-4 py-3 text-gray-600 hidden sm:table-cell">
                {DEVICE_TYPE_LABELS[device.device_type] || device.device_type}
              </td>
              <td className="px-4 py-3 text-gray-500 text-xs font-mono hidden md:table-cell">
                {PROTOCOL_LABELS[device.protocol] || device.protocol}
              </td>
              <td className="px-4 py-3">
                <StatusBadge lastSeen={device.last_seen} />
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs hidden sm:table-cell">
                {device.last_seen
                  ? new Date(device.last_seen).toLocaleString('de-CH', {
                      day: '2-digit',
                      month: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
