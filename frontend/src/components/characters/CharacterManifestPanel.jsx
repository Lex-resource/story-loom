import { BookOpen, GitBranch, Link2, LockKeyhole } from 'lucide-react';

const display = (value) => (value === undefined || value === null || value === '' ? '暂无' : String(value));

export default function CharacterManifestPanel({ manifest }) {
  const data = manifest?.data || {};
  const relationships = Array.isArray(data.relationships) ? data.relationships : [];
  const arcs = Array.isArray(data.arcs) ? data.arcs : [];
  const threads = Array.isArray(data.open_threads) ? data.open_threads : [];
  const constraints = Array.isArray(data.constraints) ? data.constraints : [];

  return (
    <section className="character-panel manifest-panel">
      <header className="character-panel__header">
        <div>
          <p className="page-eyebrow">READ ONLY PROJECTION</p>
          <h2>人物志摘要</h2>
        </div>
        <span className="character-lock">
          <LockKeyhole size={14} /> 只读
        </span>
      </header>
      <div className="manifest-facts">
        <div>
          <span>身份</span>
          <strong>{display(data.role_summary)}</strong>
        </div>
        <div>
          <span>性格</span>
          <strong>{display(data.personality_summary)}</strong>
        </div>
        <div>
          <span>成长阶段</span>
          <strong>{display(data.current_stage)}</strong>
        </div>
        <div>
          <span>当前位置</span>
          <strong>{display(data.current_location)}</strong>
        </div>
        <div>
          <span>当前情绪</span>
          <strong>{display(data.current_emotion)}</strong>
        </div>
        <div>
          <span>当前目标</span>
          <strong>{display(data.current_goal)}</strong>
        </div>
      </div>
      <div className="manifest-section">
        <h3>
          <Link2 size={15} /> 关系
        </h3>
        {relationships.length ? (
          relationships.map((item, index) => (
            <div className="manifest-list-item" key={`${item.target_character_id || item.target_name}-${index}`}>
              <strong>{display(item.target_name || item.target_character_id)}</strong>
              <span>
                {display(item.relation_type)}
                {item.summary ? ` · ${item.summary}` : ''}
              </span>
            </div>
          ))
        ) : (
          <p className="character-muted">暂无结构化关系</p>
        )}
      </div>
      <div className="manifest-section">
        <h3>
          <GitBranch size={15} /> 成长路线
        </h3>
        {arcs.length ? (
          arcs.map((arc) => (
            <div className="manifest-list-item" key={arc.id || arc.name}>
              <strong>{display(arc.name)}</strong>
              <span>
                {display(arc.arc_type)} · {display(arc.status)}
              </span>
            </div>
          ))
        ) : (
          <p className="character-muted">当前只有角色卡中的路线设定</p>
        )}
      </div>
      <div className="manifest-columns">
        <div className="manifest-section">
          <h3>
            <BookOpen size={15} /> 未完成事项
          </h3>
          {threads.length ? (
            <ul>
              {threads.map((item, index) => (
                <li key={`${item}-${index}`}>{display(item)}</li>
              ))}
            </ul>
          ) : (
            <p className="character-muted">暂无</p>
          )}
        </div>
        <div className="manifest-section">
          <h3>写作约束</h3>
          {constraints.length ? (
            <ul>
              {constraints.map((item, index) => (
                <li key={`${item}-${index}`}>{display(item)}</li>
              ))}
            </ul>
          ) : (
            <p className="character-muted">暂无</p>
          )}
        </div>
      </div>
    </section>
  );
}
