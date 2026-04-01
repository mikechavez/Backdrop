import { useState, useEffect } from 'react';
import { cn } from '../lib/cn';

type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

interface HealthResponse {
  status: HealthStatus;
  timestamp: string;
  checks: Record<string, { status: string }>;
}

const STATUS_CONFIG: Record<HealthStatus, { color: string; label: string }> = {
  healthy:   { color: 'bg-green-500',  label: 'All systems live' },
  degraded:  { color: 'bg-yellow-500', label: 'Degraded' },
  unhealthy: { color: 'bg-red-500',    label: 'Issues detected' },
  unknown:   { color: 'bg-gray-400',   label: 'Status unknown' },
};

export function StatusIndicator() {
  const [status, setStatus] = useState<HealthStatus>('unknown');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL;
    if (!apiUrl) {
      setLoading(false);
      return;
    }

    fetch(`${apiUrl}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: HealthResponse) => {
        setStatus(data.status);
      })
      .catch(() => {
        setStatus('unknown');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []); // Poll once on mount -- not continuously

  const config = STATUS_CONFIG[status];

  if (loading) {
    return (
      <div className="flex items-center gap-1.5" title="Checking system status...">
        <span className="w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5" title={config.label}>
      <span
        className={cn(
          'w-2 h-2 rounded-full',
          config.color,
          status === 'healthy' && 'animate-[pulse_3s_ease-in-out_infinite]'
        )}
      />
      <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline">
        {status === 'healthy' ? 'Live' : config.label}
      </span>
    </div>
  );
}
