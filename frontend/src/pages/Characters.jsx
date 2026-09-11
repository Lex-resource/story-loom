import { useEffect, useRef, useState } from 'react';
import { Bot, History, RefreshCw, RotateCcw, UserRound } from 'lucide-react';
import { characterApi } from '../services/novelApi';
import CharacterCardEditor from '../components/characters/CharacterCardEditor';
import CharacterManifestPanel from '../components/characters/CharacterManifestPanel';
import CharacterStateTimeline from '../components/characters/CharacterStateTimeline';
import CharacterBranchPanel from '../components/characters/CharacterBranchPanel';
import {
  CHARACTER_IMPORTANCE_LABELS,
  CHARACTER_STATUS_LABELS,
  CHARACTER_STATUS_ACTIVE,
} from '../utils/characterConstants';
import { createRequestGuard } from '../utils/requestLifecycle';

const formatTime = (value) => (value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未知时间');

export default function Characters({ activeProject, showToast }) {
  const [characters, setCharacters] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [states, setStates] = useState([]);
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState('idle');
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const projectId = activeProject?.id;
  const listGuardRef = useRef(null);
  const detailGuardRef = useRef(null);
  const mutationGuardRef = useRef(null);
  if (!listGuardRef.current) listGuardRef.current = createRequestGuard();
  if (!detailGuardRef.current) detailGuardRef.current = createRequestGuard();
  if (!mutationGuardRef.current) mutationGuardRef.current = createRequestGuard();
  const activeSelectionRef = useRef({ projectId, selectedId });
  activeSelectionRef.current = { projectId, selectedId };

  const isCurrentSelection = (targetProjectId, targetCharacterId) =>
    activeSelectionRef.current.projectId === targetProjectId &&
    activeSelectionRef.current.selectedId === targetCharacterId;

  const loadCharacters = async () => {
    if (!projectId) return;
    const request = listGuardRef.current.start();
    setLoading('loading');
    try {
      const response = await characterApi.list(projectId, { signal: request.signal });
      if (!request.isCurrent()) return;
      setCharacters(response.characters || []);
      setSelectedId((current) =>
        current && response.characters?.some((item) => item.id === current)
          ? current
          : response.characters?.[0]?.id || null,
      );
      setLoading('success');
    } catch (error) {
      if (request.isCurrent() && error.name !== 'AbortError') {
        setLoading('error');
        showToast(error.message);
      }
    } finally {
      if (request.isCurrent()) setLoading((current) => (current === 'loading' ? 'idle' : current));
    }
  };

  useEffect(() => {
    activeSelectionRef.current = { projectId, selectedId: null };
    setCharacters([]);
    setSelectedId(null);
    setDetail(null);
    setStates([]);
    setChanges([]);
    loadCharacters();
    return () => listGuardRef.current.cancel();
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedId || activeSelectionRef.current.selectedId !== selectedId) {
      setDetail(null);
      setStates([]);
      setChanges([]);
      return undefined;
    }
    const request = detailGuardRef.current.start();
    setTimelineLoading(true);
    Promise.all([
      characterApi.detail(projectId, selectedId, { signal: request.signal }),
      characterApi.states(projectId, selectedId, { signal: request.signal }),
      characterApi.changes(projectId, selectedId, { signal: request.signal }),
    ])
      .then(([card, stateResponse, changeResponse]) => {
        if (!request.isCurrent()) return;
        setDetail(card);
        setStates(stateResponse.states || []);
        setChanges(changeResponse.changes || []);
      })
      .catch((error) => {
        if (request.isCurrent() && error.name !== 'AbortError') showToast(error.message);
      })
      .finally(() => {
        if (request.isCurrent()) setTimelineLoading(false);
      });
    return () => detailGuardRef.current.cancel();
  }, [projectId, selectedId]);

  useEffect(() => () => mutationGuardRef.current.cancel(), [projectId, selectedId]);

  const refresh = async () => loadCharacters();

  const handleSave = async (payload) => {
    if (!projectId || !selectedId) return;
    const targetProjectId = projectId;
    const targetCharacterId = selectedId;
    const request = mutationGuardRef.current.start();
    setSaving(true);
    try {
      await characterApi.update(targetProjectId, targetCharacterId, payload, { signal: request.signal });
      if (!request.isCurrent()) return;
      showToast('角色卡已覆盖保存，人物志已同步。', 'success');
      await loadCharacters();
      if (!request.isCurrent() || !isCurrentSelection(targetProjectId, targetCharacterId)) return;
      const updated = await characterApi.detail(targetProjectId, targetCharacterId, { signal: request.signal });
      if (!request.isCurrent()) return;
      setDetail(updated);
      const [stateResponse, changeResponse] = await Promise.all([
        characterApi.states(targetProjectId, targetCharacterId, { signal: request.signal }),
        characterApi.changes(targetProjectId, targetCharacterId, { signal: request.signal }),
      ]);
      if (!request.isCurrent()) return;
      setStates(stateResponse.states || []);
      setChanges(changeResponse.changes || []);
    } catch (error) {
      if (request.isCurrent() && error.name !== 'AbortError') showToast(error.message);
    } finally {
      if (request.isCurrent()) setSaving(false);
    }
  };

  const handleRollback = async (changeId) => {
    if (!window.confirm('确认回滚到这条记录对应的修改前快照吗？当前角色卡会再次产生一条修改记录。')) return;
    if (!projectId || !selectedId) return;
    const targetProjectId = projectId;
    const targetCharacterId = selectedId;
    const request = mutationGuardRef.current.start();
    try {
      await characterApi.rollback(targetProjectId, targetCharacterId, changeId, { signal: request.signal });
      if (!request.isCurrent()) return;
      showToast('角色卡已回滚，人物志已同步。', 'success');
      await loadCharacters();
      if (!request.isCurrent() || !isCurrentSelection(targetProjectId, targetCharacterId)) return;
      const updated = await characterApi.detail(targetProjectId, targetCharacterId, { signal: request.signal });
      if (!request.isCurrent()) return;
      setDetail(updated);
      const response = await characterApi.changes(targetProjectId, targetCharacterId, { signal: request.signal });
      if (!request.isCurrent()) return;
      setChanges(response.changes || []);
    } catch (error) {
      if (request.isCurrent() && error.name !== 'AbortError') showToast(error.message);
    }
  };

  const filteredCharacters = characters.filter((character) => {
    const query = search.trim().toLowerCase();
    if (!query) return true;
    return [character.name, ...(character.aliases || [])].some((value) => String(value).toLowerCase().includes(query));
  });

  return (
    <div className="characters-page">
      <header className="characters-hero">
        <div>
          <p className="page-eyebrow">CHARACTER AUTHORITY</p>
          <h1>角色卡</h1>
          <p>维护每个角色的稳定设定、动态状态与关系。人物志由这里自动投影，Planner 读取摘要，Writer 读取完整卡片。</p>
        </div>
        <div className="characters-hero__actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            disabled={loading === 'loading'}
            title="刷新角色卡"
          >
            <RefreshCw size={15} className={loading === 'loading' ? 'animate-spin' : ''} /> 刷新
          </button>
        </div>
      </header>

      <div className="characters-toolbar">
        <div className="characters-stat">
          <strong>{characters.length}</strong>
          <span>个角色</span>
        </div>
        <div className="characters-stat">
          <strong>{characters.filter((item) => item.status === CHARACTER_STATUS_ACTIVE).length}</strong>
          <span>活跃角色</span>
        </div>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索姓名或别名"
          aria-label="搜索姓名或别名"
        />
      </div>

      <div className="characters-layout">
        <aside className="characters-index">
          <div className="characters-index__header">
            <span>人物索引</span>
            <small>
              {filteredCharacters.length} / {characters.length}
            </small>
          </div>
          {loading === 'loading' && !characters.length ? (
            <div className="character-empty">正在读取角色卡...</div>
          ) : null}
          {loading === 'error' ? <div className="character-empty">角色卡读取失败，请刷新重试。</div> : null}
          {!characters.length && loading === 'success' ? (
            <div className="character-empty">
              <Bot size={21} />
              <span>章节生成时会自动建立角色卡。</span>
            </div>
          ) : null}
          <div className="characters-list">
            {filteredCharacters.map((character) => {
              const manifest = character.manifest?.data || {};
              return (
                <button
                  type="button"
                  key={character.id}
                  className={`character-list-item ${selectedId === character.id ? 'active' : ''}`}
                  onClick={() => setSelectedId(character.id)}
                >
                  <span className="character-avatar">
                    <UserRound size={17} />
                  </span>
                  <span className="character-list-item__body">
                    <strong>{character.name}</strong>
                    <small>
                      {manifest.role_summary || CHARACTER_IMPORTANCE_LABELS[character.importance] || '角色'}
                    </small>
                  </span>
                  <span
                    className={`character-status-dot character-status-dot--${character.status}`}
                    title={CHARACTER_STATUS_LABELS[character.status] || character.status}
                  />
                </button>
              );
            })}
          </div>
        </aside>

        <main className="characters-main">
          {detail ? (
            <>
              <div className="character-detail-heading">
                <div>
                  <p className="page-eyebrow">
                    {CHARACTER_IMPORTANCE_LABELS[detail.importance] || '角色'} ·{' '}
                    {CHARACTER_STATUS_LABELS[detail.status] || detail.status}
                  </p>
                  <h2>{detail.name}</h2>
                  <span>最后登场：{detail.last_appearance ? `第 ${detail.last_appearance} 章` : '未知'}</span>
                </div>
                <div className="character-detail-heading__badge">
                  <Bot size={16} /> AI 维护 · 可人工编辑
                </div>
              </div>
              <div className="characters-content-grid">
                <CharacterCardEditor card={detail} onSave={handleSave} saving={saving} />
                <CharacterManifestPanel manifest={detail.manifest} />
                <CharacterStateTimeline states={states} loading={timelineLoading} />
                <section className="character-panel changes-panel">
                  <header className="character-panel__header">
                    <div>
                      <p className="page-eyebrow">AUDIT TRAIL</p>
                      <h2>修改记录</h2>
                    </div>
                    <History size={17} className="character-panel__icon" />
                  </header>
                  {changes.length ? (
                    changes.map((change) => (
                      <article className="change-record" key={change.id}>
                        <div>
                          <strong>{formatTime(change.created_at)}</strong>
                          <span>{change.changed_fields?.join('、') || '角色卡内容变化'}</span>
                        </div>
                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleRollback(change.id)}
                          title="回滚到修改前快照"
                          aria-label="回滚到修改前快照"
                        >
                          <RotateCcw size={15} />
                        </button>
                      </article>
                    ))
                  ) : (
                    <p className="character-muted">暂无修改记录。第一次覆盖修改后会出现修改前快照。</p>
                  )}
                </section>
                <CharacterBranchPanel projectId={projectId} characterId={selectedId} showToast={showToast} />
              </div>
            </>
          ) : (
            <div className="characters-main-empty">
              <Bot size={34} />
              <h2>角色卡工作台</h2>
              <p>角色卡会在章节生成时自动建立。</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
