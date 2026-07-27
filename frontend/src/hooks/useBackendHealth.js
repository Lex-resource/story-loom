import { useEffect, useState } from 'react';
import { BACKEND_URL } from '../services/api';

export default function useBackendHealth(intervalMs = 5000) {
  const [status, setStatus] = useState('checking');

  useEffect(() => {
    let disposed = false;
    let controller;

    const check = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch(`${BACKEND_URL}/health`, { signal: controller.signal });
        if (!disposed) setStatus(response.ok ? 'online' : 'offline');
      } catch (error) {
        if (!disposed && error.name !== 'AbortError') setStatus('offline');
      }
    };

    check();
    const timer = window.setInterval(check, intervalMs);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return status;
}
