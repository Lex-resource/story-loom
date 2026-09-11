import { useEffect, useState } from 'react';
import { workerApi } from '../services/novelApi';
import { createRequestGuard } from '../utils/requestLifecycle';

/**
 * 共享的 worker 状态轮询:多个组件(生成日志徽标、系统配置的运行时视图)
 * 订阅同一个轮询循环,而不是各自开定时器打同一接口。
 *
 * - 单一 interval:首个订阅者启动,最后一个离开时停止。间隔是全模块共享的
 *   常量而不是各消费方传参——定时器先到先得,若允许传不同间隔,后挂载的
 *   视图实际会跑在先来者的节拍上,而它的"每 N 秒自动重试"文案就成了假话;
 * - 最新值缓存:新订阅者立即拿到最近一次结果,不用等下一拍;
 * - seq 守卫:慢响应乱序返回时丢弃(seq 不等于最新请求序号就不应用),
 *   避免旧数据覆盖新数据;
 * - 错误不在这里弹 toast:通过 error 字段交给订阅方决定展示方式
 *   (轮询失败静默保旧值,由 UI 呈现陈旧标记;操作失败才弹 toast)。
 */

export const WORKER_STATUS_POLL_INTERVAL_MS = 5000;

let latestStatus = null;
let latestError = null;
let timer = null;
const subscribers = new Set();
const requestGuard = createRequestGuard();

async function fetchOnce() {
  const request = requestGuard.start();
  try {
    const status = await workerApi.status({ signal: request.signal });
    if (!request.isCurrent()) return;
    latestStatus = status;
    latestError = null;
  } catch (e) {
    if (!request.isCurrent() || e.name === 'AbortError') return;
    latestError = e?.message || String(e);
  }
  if (!request.isCurrent()) return;
  for (const notify of subscribers) notify();
}

function startPolling() {
  stopPolling();
  timer = setInterval(fetchOnce, WORKER_STATUS_POLL_INTERVAL_MS);
  fetchOnce();
}

function stopPolling() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
  requestGuard.cancel();
}

export function useWorkerStatus() {
  const [state, setState] = useState({ status: latestStatus, error: latestError });

  useEffect(() => {
    const notify = () => setState({ status: latestStatus, error: latestError });
    subscribers.add(notify);
    if (!timer) startPolling();
    else setState({ status: latestStatus, error: latestError });
    return () => {
      subscribers.delete(notify);
      if (subscribers.size === 0) stopPolling();
    };
  }, []);

  const refresh = () => fetchOnce();

  return { status: state.status, error: state.error, refresh };
}
