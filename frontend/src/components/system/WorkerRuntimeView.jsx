import { Meta } from './FormControls';
import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { workerApi } from '../../services/novelApi';
import { useWorkerStatus, WORKER_STATUS_POLL_INTERVAL_MS } from '../../hooks/useWorkerStatus';

/**
 * worker 运行时视图:展示队列深度/活跃任务/暂停领取开关与任务列表,
 * 支持单任务取消与失败任务重试。状态来自共享的 useWorkerStatus 轮询。
 *
 * 错误态约定:轮询失败不弹 toast(每个轮询周期一弹是骚扰)——静默保留最后已知
 * 状态并显示陈旧横幅;首次加载失败给重试面板;只有用户主动操作失败才弹 toast。
 */
export default function WorkerRuntimeView({ showToast }) {
  const { status, error, refresh } = useWorkerStatus();
  const [busy, setBusy] = useState(false);

  const toggleClaim = async () => {
    setBusy(true);
    try {
      if (status?.claim_paused) {
        await workerApi.resumeClaim();
        showToast('已恢复领取新任务', 'success');
      } else {
        await workerApi.pauseClaim();
        showToast('已暂停领取新任务(在跑任务继续到检查点)', 'success');
      }
      refresh();
    } catch (e) {
      showToast(`操作失败: ${e.message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async (jobId) => {
    setBusy(true);
    try {
      await workerApi.cancelJob(jobId);
      showToast('任务已取消', 'success');
      refresh();
    } catch (e) {
      showToast(`取消失败: ${e.message}`, 'error');
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async (jobId) => {
    setBusy(true);
    try {
      await workerApi.retryJob(jobId);
      showToast('任务已复位到队列,等待 worker 领取', 'success');
      refresh();
    } catch (e) {
      showToast(`重试失败: ${e.message}`, 'error');
      refresh();
    } finally {
      setBusy(false);
    }
  };

  if (!status && error) {
    return (
      <div className="glass-panel" style={{ padding: '24px', borderRadius: '12px', textAlign: 'center' }}>
        <div style={{ fontSize: '13px', color: 'var(--color-red)', marginBottom: '12px' }}>
          无法获取 worker 状态:{error}
        </div>
        <button className="btn btn-primary" onClick={refresh} style={{ padding: '5px 16px', fontSize: '13px' }}>
          重试
        </button>
      </div>
    );
  }

  if (!status) {
    return (
      <div
        className="glass-panel"
        style={{
          padding: '24px',
          borderRadius: '12px',
          display: 'flex',
          justifyContent: 'center',
          color: 'var(--ink-light)',
        }}
      >
        <Loader2 className="spin-slow" size={22} />
        <span style={{ marginLeft: '10px' }}>正在获取运行时状态...</span>
      </div>
    );
  }

  return (
    <>
      {error && (
        <div
          style={{
            border: '1px solid var(--border-muted)',
            background: 'rgba(184, 134, 11, 0.08)',
            borderRadius: '8px',
            padding: '10px 14px',
            fontSize: '12.5px',
            color: 'var(--ink-light)',
          }}
        >
          轮询失败({error}),以下为最后已知状态,每 {WORKER_STATUS_POLL_INTERVAL_MS / 1000} 秒自动重试。
        </div>
      )}

      <div className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', gap: '18px', flexWrap: 'wrap', fontSize: '13px' }}>
            <Meta label="运行模式" value={status.mode === 'in_process' ? '单进程(内嵌)' : '外部 worker'} />
            <Meta label="排队中" value={status.pending_jobs} />
            <Meta label="运行中" value={status.running_jobs} />
            <Meta
              label="活跃任务"
              value={`${status.active_tasks} / ${status.max_concurrent_jobs}`}
              hint={status.has_capacity ? '有空位' : '已满'}
            />
          </div>
          <button
            className={`btn ${status.claim_paused ? 'btn-primary' : ''}`}
            onClick={toggleClaim}
            disabled={busy}
            style={{ padding: '5px 16px', fontSize: '13px' }}
          >
            {busy ? <Loader2 size={14} className="spin-slow" /> : null}
            {status.claim_paused ? '恢复领取新任务' : '暂停领取新任务'}
          </button>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '18px', borderRadius: '12px' }}>
        <h3 style={{ marginTop: 0, fontSize: '15px' }}>运行中的任务</h3>
        {status.running_list.length === 0 ? (
          <div style={{ fontSize: '13px', color: 'var(--ink-lighter)' }}>
            {status.claim_paused ? '已暂停领取,队列中的任务不会被启动。' : '当前没有运行中的任务。'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {status.running_list.map((job) => (
              <div
                key={job.job_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '8px 12px',
                  border: '1px solid var(--border-muted)',
                  borderRadius: '8px',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', minWidth: 0 }}>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '11.5px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {job.project_id}
                  </span>
                  <span style={{ color: 'var(--ink-light)' }}>
                    第 {job.current_chapter ?? '—'} 章 · {job.current_step || '—'}
                  </span>
                </div>
                <button
                  className="btn"
                  onClick={() => handleCancel(job.job_id)}
                  disabled={busy}
                  style={{ padding: '3px 10px', fontSize: '12px', flexShrink: 0 }}
                >
                  取消任务
                </button>
              </div>
            ))}
          </div>
        )}

        <h3 style={{ marginBottom: '8px', fontSize: '14px', marginTop: '18px' }}>
          排队中的任务{' '}
          <span style={{ color: 'var(--ink-lighter)', fontWeight: 400, fontSize: '12px' }}>(最多显示 20 条)</span>
        </h3>
        {status.pending_list.length === 0 ? (
          <div style={{ fontSize: '13px', color: 'var(--ink-lighter)' }}>队列为空。</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {status.pending_list.map((job) => (
              <div
                key={job.job_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '6px 12px',
                  border: '1px solid var(--border-muted)',
                  borderRadius: '8px',
                  fontSize: '12.5px',
                }}
              >
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', minWidth: 0 }}>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '11px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {job.project_id}
                  </span>
                  <span style={{ color: 'var(--ink-light)' }}>{job.type}</span>
                </div>
                <button
                  className="btn"
                  onClick={() => handleCancel(job.job_id)}
                  disabled={busy}
                  style={{ padding: '3px 10px', fontSize: '12px', flexShrink: 0 }}
                >
                  取消
                </button>
              </div>
            ))}
          </div>
        )}

        {(status.retryable_list || []).length > 0 && (
          <>
            <h3 style={{ marginBottom: '8px', fontSize: '14px', marginTop: '18px' }}>
              可重试的任务{' '}
              <span style={{ color: 'var(--ink-lighter)', fontWeight: 400, fontSize: '12px' }}>
                (暂停/失败/已取消,最多 20 条)
              </span>
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {status.retryable_list.map((job) => (
                <div
                  key={job.job_id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '6px 12px',
                    border: '1px solid var(--border-muted)',
                    borderRadius: '8px',
                    fontSize: '12.5px',
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <span
                        style={{
                          fontFamily: 'monospace',
                          fontSize: '11px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {job.project_id}
                      </span>
                      <span style={{ color: 'var(--ink-light)' }}>
                        {job.type} · {job.status}
                        {job.current_chapter != null ? ` · 第 ${job.current_chapter} 章` : ''}
                      </span>
                    </div>
                    {job.error && (
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--ink-lighter)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {job.error}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn"
                    onClick={() => handleRetry(job.job_id)}
                    disabled={busy}
                    style={{ padding: '3px 10px', fontSize: '12px', flexShrink: 0 }}
                  >
                    重试
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}
