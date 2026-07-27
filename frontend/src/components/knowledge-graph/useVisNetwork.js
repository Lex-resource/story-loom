import { useEffect, useRef, useCallback } from 'react';

/**
 * 管理 vis-network 实例生命周期：创建、更新、销毁。
 * @param {HTMLElement | null} container - 画布 DOM 节点
 * @param {{ nodes: unknown[], edges: unknown[] } | null} data - vis 数据
 * @param {object} options - vis-network 选项
 * @param {(params: object) => void} onNodeClick - 节点点击回调
 * @param {{ freezeAfterStabilization?: boolean }} config - 稳定后是否关闭物理
 */
export function useVisNetwork(container, data, options, onNodeClick, config = {}) {
  const { freezeAfterStabilization = false } = config;
  const networkRef = useRef(null);
  const onClickRef = useRef(onNodeClick);
  onClickRef.current = onNodeClick;

  // Refs to access latest values during async Network creation
  const dataRef = useRef(data);
  dataRef.current = data;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const freezeRef = useRef(freezeAfterStabilization);
  freezeRef.current = freezeAfterStabilization;
  const fittedRef = useRef(false);

  // Effect 1: Create/destroy Network — only when container changes
  useEffect(() => {
    if (!container) return undefined;

    let cancelled = false;
    fittedRef.current = false;

    (async () => {
      try {
        const { Network } = await import('vis-network/standalone');
        if (cancelled || !container) return;

        if (networkRef.current) {
          networkRef.current.destroy();
          networkRef.current = null;
        }

        // Use latest data/options from refs (may have changed during async import)
        const initialData = dataRef.current || { nodes: [], edges: [] };
        const network = new Network(container, initialData, optionsRef.current);
        networkRef.current = network;

        network.on('click', (params) => onClickRef.current?.(params));

        if (optionsRef.current?.physics?.enabled !== false) {
          network.on('stabilizationIterationsDone', () => {
            // Skip freeze/fit if there are no nodes (e.g. initial empty creation)
            const nodeCount = network.body?.nodeIds?.length || 0;
            if (nodeCount === 0) return;

            if (freezeRef.current) {
              network.setOptions({ physics: { enabled: false } });
            }
            if (!fittedRef.current) {
              fittedRef.current = true;
              network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
            }
          });
        } else {
          network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
          fittedRef.current = true;
        }
      } catch (err) {
        console.error('vis-network init error:', err);
      }
    })();

    return () => {
      cancelled = true;
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, [container]);

  // Effect 2: Incrementally update data — no destroy/recreate
  useEffect(() => {
    if (networkRef.current && data) {
      networkRef.current.setData(data);
      // Reset fitted flag so stabilization handler will fit after new data settles
      fittedRef.current = false;
      // If physics is disabled, stabilization won't fire — fit manually
      if (optionsRef.current?.physics?.enabled === false && data.nodes?.length > 0) {
        networkRef.current.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
        fittedRef.current = true;
      }
    }
  }, [data]);

  // Effect 3: Incrementally update options — no destroy/recreate
  useEffect(() => {
    if (networkRef.current && options) {
      networkRef.current.setOptions(options);
    }
  }, [options]);

  const fit = useCallback(() => {
    networkRef.current?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
  }, []);

  const zoomIn = useCallback(() => {
    const scale = networkRef.current?.getScale() ?? 1;
    networkRef.current?.moveTo({ scale: scale * 1.25, animation: true });
  }, []);

  const zoomOut = useCallback(() => {
    const scale = networkRef.current?.getScale() ?? 1;
    networkRef.current?.moveTo({ scale: scale / 1.25, animation: true });
  }, []);

  return { networkRef, fit, zoomIn, zoomOut };
}
