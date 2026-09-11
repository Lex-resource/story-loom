import { useEffect, useState } from 'react';
import { AlertTriangle, Save } from 'lucide-react';
import {
  CHARACTER_DEFAULT_IMPORTANCE,
  CHARACTER_DEFAULT_STATUS,
  CHARACTER_IMPORTANCE_LABELS,
  CHARACTER_STATUS_LABELS,
} from '../../utils/characterConstants';

const jsonText = (value) => JSON.stringify(value ?? {}, null, 2);

export default function CharacterCardEditor({ card, onSave, saving }) {
  const [draft, setDraft] = useState(null);
  const [cardDataText, setCardDataText] = useState('{}');
  const [stateText, setStateText] = useState('{}');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!card) return;
    setDraft({
      name: card.name || '',
      aliases: (card.aliases || []).join(', '),
      importance: card.importance || CHARACTER_DEFAULT_IMPORTANCE,
      status: card.status || CHARACTER_DEFAULT_STATUS,
      lastAppearance: card.last_appearance || '',
      effectiveFromChapter: '',
    });
    setCardDataText(jsonText(card.card_data));
    setStateText(jsonText(card.current_state));
    setError('');
  }, [card]);

  if (!card || !draft) {
    return <div className="character-empty">选择一个角色开始维护角色卡。</div>;
  }

  const updateDraft = (key, value) => setDraft((current) => ({ ...current, [key]: value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    let cardData;
    let currentState;
    try {
      cardData = JSON.parse(cardDataText);
      currentState = JSON.parse(stateText);
    } catch (parseError) {
      setError(`JSON 格式错误：${parseError.message}`);
      return;
    }
    if (!cardData || Array.isArray(cardData) || typeof cardData !== 'object') {
      setError('角色卡 JSON 必须是对象。');
      return;
    }
    if (!currentState || Array.isArray(currentState) || typeof currentState !== 'object') {
      setError('动态状态 JSON 必须是对象。');
      return;
    }
    setError('');
    await onSave({
      name: draft.name.trim(),
      aliases: draft.aliases
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      importance: draft.importance,
      status: draft.status,
      last_appearance: draft.lastAppearance ? Number(draft.lastAppearance) : null,
      effective_from_chapter: draft.effectiveFromChapter ? Number(draft.effectiveFromChapter) : null,
      card_data: cardData,
      current_state: currentState,
    });
  };

  return (
    <form className="character-editor" onSubmit={handleSubmit}>
      <div className="character-editor__fields">
        <label>
          <span>姓名</span>
          <input value={draft.name} onChange={(event) => updateDraft('name', event.target.value)} required />
        </label>
        <label>
          <span>别名</span>
          <input
            value={draft.aliases}
            onChange={(event) => updateDraft('aliases', event.target.value)}
            placeholder="用逗号分隔"
          />
        </label>
        <label>
          <span>重要度</span>
          <select value={draft.importance} onChange={(event) => updateDraft('importance', event.target.value)}>
            {Object.entries(CHARACTER_IMPORTANCE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>当前状态</span>
          <select value={draft.status} onChange={(event) => updateDraft('status', event.target.value)}>
            {Object.entries(CHARACTER_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>最后登场章节</span>
          <input
            type="number"
            min="1"
            value={draft.lastAppearance}
            onChange={(event) => updateDraft('lastAppearance', event.target.value)}
            placeholder="留空表示未知"
          />
        </label>
        <label>
          <span>本次修改生效章节</span>
          <input
            type="number"
            min="1"
            value={draft.effectiveFromChapter}
            onChange={(event) => updateDraft('effectiveFromChapter', event.target.value)}
            placeholder="留空表示立即生效"
          />
        </label>
      </div>

      <label className="character-editor__json">
        <span>稳定设定与角色路线 JSON</span>
        <textarea value={cardDataText} onChange={(event) => setCardDataText(event.target.value)} spellCheck="false" />
      </label>
      <label className="character-editor__json">
        <span>动态状态 JSON</span>
        <textarea value={stateText} onChange={(event) => setStateText(event.target.value)} spellCheck="false" />
      </label>

      {error ? (
        <div className="character-form-error" role="alert">
          <AlertTriangle size={15} /> {error}
        </div>
      ) : null}
      <div className="character-editor__actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          <Save size={15} /> {saving ? '保存中...' : '覆盖保存角色卡'}
        </button>
      </div>
    </form>
  );
}
