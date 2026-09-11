import { Clock3, FileClock } from 'lucide-react';

export default function CharacterStateTimeline({ states, loading }) {
  return (
    <section className="character-panel state-panel">
      <header className="character-panel__header">
        <div>
          <p className="page-eyebrow">SPARSE CHAPTER HISTORY</p>
          <h2>角色状态时间线</h2>
        </div>
        <Clock3 size={17} className="character-panel__icon" />
      </header>
      {loading ? <p className="character-muted">正在读取状态时间线...</p> : null}
      {!loading && !states.length ? (
        <div className="character-empty character-empty--small">
          <FileClock size={19} />
          <span>还没有记录到状态变化。只有本章状态真正变化时才会新增一条。</span>
        </div>
      ) : null}
      <div className="state-timeline">
        {states.map((state) => (
          <article className="state-timeline__item" key={state.id}>
            <div className="state-timeline__marker" />
            <div className="state-timeline__body">
              <div className="state-timeline__meta">
                <strong>第 {state.chapter_index} 章</strong>
                <span>{state.storyline_id}</span>
              </div>
              <pre>{JSON.stringify(state.state_data || {}, null, 2)}</pre>
              {state.changed_fields?.length ? <small>变化：{state.changed_fields.join('、')}</small> : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
