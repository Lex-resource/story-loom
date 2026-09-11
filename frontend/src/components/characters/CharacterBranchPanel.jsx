import { useEffect, useMemo, useRef, useState } from 'react';
import { Archive, BookOpen, GitBranch, Loader2, Play, Save } from 'lucide-react';
import { characterApi } from '../../services/novelApi';
import { createRequestGuard } from '../../utils/requestLifecycle';

const STATUS_LABELS = {
  pending: '待生成',
  generating: '生成中',
  draft: '草稿',
  ready: '可阅读',
  failed: '失败',
  archived: '已归档',
};

const chapterContent = (chapter) => chapter?.content || chapter?.edited_content || chapter?.draft_content || '';

export default function CharacterBranchPanel({ projectId, characterId, showToast }) {
  const [arcs, setArcs] = useState([]);
  const [branches, setBranches] = useState([]);
  const [selectedBranchId, setSelectedBranchId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({ arcId: '', title: '', anchor: '', target: 1, request: '' });
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autoDiscoveryEnabled, setAutoDiscoveryEnabled] = useState(false);
  const listGuardRef = useRef(null);
  const detailGuardRef = useRef(null);
  if (!listGuardRef.current) listGuardRef.current = createRequestGuard();
  if (!detailGuardRef.current) detailGuardRef.current = createRequestGuard();
  const contextRef = useRef({ projectId, characterId });
  contextRef.current = { projectId, characterId };
  const selectedBranchRef = useRef(selectedBranchId);
  selectedBranchRef.current = selectedBranchId;

  const isCurrentContext = () =>
    contextRef.current.projectId === projectId && contextRef.current.characterId === characterId;

  const selectedBranch = useMemo(
    () => branches.find((branch) => branch.id === selectedBranchId) || null,
    [branches, selectedBranchId],
  );

  const load = async () => {
    if (!projectId || !characterId) return;
    const request = listGuardRef.current.start();
    setLoading(true);
    try {
      const [arcResponse, branchResponse, settingsResponse] = await Promise.all([
        characterApi.arcs(projectId, characterId, { signal: request.signal }),
        characterApi.branches(projectId, characterId, { signal: request.signal }),
        characterApi.branchSettings(projectId, { signal: request.signal }),
      ]);
      if (!request.isCurrent() || !isCurrentContext()) return;
      setArcs(arcResponse.arcs || []);
      setAutoDiscoveryEnabled(Boolean(settingsResponse.auto_discovery_enabled));
      const nextBranches = branchResponse.branches || [];
      setBranches(nextBranches);
      setSelectedBranchId((current) =>
        current && nextBranches.some((item) => item.id === current) ? current : nextBranches[0]?.id || null,
      );
      if (!form.anchor && nextBranches[0]) {
        setForm((current) => ({ ...current, anchor: String(nextBranches[0].anchor_main_chapter) }));
      }
    } catch (error) {
      if (request.isCurrent() && error.name !== 'AbortError' && isCurrentContext()) showToast(error.message);
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  };

  useEffect(() => {
    listGuardRef.current.cancel();
    detailGuardRef.current.cancel();
    selectedBranchRef.current = null;
    setArcs([]);
    setBranches([]);
    setSelectedBranchId(null);
    setDetail(null);
    setEditing(null);
    setSaving(false);
    setAutoDiscoveryEnabled(false);
    load();
    return () => {
      listGuardRef.current.cancel();
      detailGuardRef.current.cancel();
    };
  }, [projectId, characterId]);

  useEffect(() => {
    if (!selectedBranchId || selectedBranchRef.current !== selectedBranchId) {
      setDetail(null);
      return undefined;
    }
    const request = detailGuardRef.current.start();
    characterApi
      .branchDetail(projectId, characterId, selectedBranchId, { signal: request.signal })
      .then((value) => {
        if (request.isCurrent() && isCurrentContext()) setDetail(value);
      })
      .catch((error) => {
        if (request.isCurrent() && error.name !== 'AbortError' && isCurrentContext()) showToast(error.message);
      });
    return () => detailGuardRef.current.cancel();
  }, [projectId, characterId, selectedBranchId]);

  const create = async (event) => {
    event.preventDefault();
    const targetProjectId = projectId;
    const targetCharacterId = characterId;
    try {
      const branch = await characterApi.createBranch(targetProjectId, targetCharacterId, {
        arc_id: form.arcId || null,
        title: form.title || null,
        anchor_main_chapter: form.anchor ? Number(form.anchor) : null,
        target_chapters: Number(form.target),
        user_request: form.request,
      });
      if (!isCurrentContext()) return;
      showToast('支线已创建，可以开始生成。', 'success');
      await load();
      setSelectedBranchId(branch.id);
    } catch (error) {
      if (isCurrentContext()) showToast(error.message);
    }
  };

  const generate = async (branch) => {
    const targetProjectId = projectId;
    const targetCharacterId = characterId;
    try {
      await characterApi.generateBranch(targetProjectId, targetCharacterId, branch.id, {
        chapters: 1,
        continue_generation: true,
      });
      if (!isCurrentContext()) return;
      showToast('支线生成任务已提交。', 'success');
      await load();
    } catch (error) {
      if (isCurrentContext()) showToast(error.message);
    }
  };

  const saveChapter = async (chapter) => {
    const targetProjectId = projectId;
    const targetCharacterId = characterId;
    const targetBranchId = selectedBranchId;
    setSaving(true);
    try {
      await characterApi.editBranchChapter(targetProjectId, targetCharacterId, targetBranchId, chapter.chapter_index, {
        title: editing.title,
        content: editing.content,
      });
      if (!isCurrentContext() || selectedBranchRef.current !== targetBranchId) return;
      showToast('支线章节已保存。', 'success');
      setEditing(null);
      const refreshed = await characterApi.branchDetail(targetProjectId, targetCharacterId, targetBranchId);
      if (isCurrentContext() && selectedBranchRef.current === targetBranchId) setDetail(refreshed);
    } catch (error) {
      if (isCurrentContext() && selectedBranchRef.current === targetBranchId) showToast(error.message);
    } finally {
      if (isCurrentContext() && selectedBranchRef.current === targetBranchId) setSaving(false);
    }
  };

  const archive = async (branch) => {
    if (!window.confirm('确认归档这条支线吗？归档后不能继续生成或编辑。')) return;
    const targetProjectId = projectId;
    const targetCharacterId = characterId;
    try {
      await characterApi.archiveBranch(targetProjectId, targetCharacterId, branch.id);
      if (!isCurrentContext()) return;
      showToast('支线已归档。', 'success');
      await load();
    } catch (error) {
      if (isCurrentContext()) showToast(error.message);
    }
  };

  const toggleAutoDiscovery = async (event) => {
    const nextValue = event.target.checked;
    const targetProjectId = projectId;
    setAutoDiscoveryEnabled(nextValue);
    try {
      await characterApi.updateBranchSettings(targetProjectId, { auto_discovery_enabled: nextValue });
      if (!isCurrentContext()) return;
      showToast(nextValue ? '已开启支线候选自动发现。' : '已关闭支线候选自动发现。', 'success');
    } catch (error) {
      if (isCurrentContext()) {
        setAutoDiscoveryEnabled(!nextValue);
        showToast(error.message);
      }
    }
  };

  return (
    <section className="character-panel branch-panel">
      <header className="character-panel__header">
        <div>
          <p className="page-eyebrow">ISOLATED CHARACTER STORY</p>
          <h2>
            <GitBranch size={17} /> 角色支线
          </h2>
        </div>
        <label className="branch-auto-toggle">
          <input type="checkbox" checked={autoDiscoveryEnabled} onChange={toggleAutoDiscovery} />
          <span>自动发现候选</span>
        </label>
      </header>
      <form className="branch-create-form" onSubmit={create}>
        <div className="branch-form-grid">
          <label>
            <span>成长路线</span>
            <select value={form.arcId} onChange={(event) => setForm({ ...form, arcId: event.target.value })}>
              <option value="">默认路线</option>
              {arcs.map((arc) => (
                <option key={arc.id} value={arc.id}>
                  {arc.name} · {arc.arc_type}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>主线锚点章节</span>
            <input
              type="number"
              min="1"
              value={form.anchor}
              onChange={(event) => setForm({ ...form, anchor: event.target.value })}
              placeholder="默认最后登场章"
            />
          </label>
          <label>
            <span>目标章节数</span>
            <input
              type="number"
              min="1"
              max="20"
              value={form.target}
              onChange={(event) => setForm({ ...form, target: event.target.value })}
            />
          </label>
          <label>
            <span>支线标题</span>
            <input
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="角色名支线"
            />
          </label>
        </div>
        <label>
          <span>生成要求</span>
          <textarea
            value={form.request}
            onChange={(event) => setForm({ ...form, request: event.target.value })}
            placeholder="例如：从角色离开主线后的调查开始。"
          />
        </label>
        <button type="submit" className="btn btn-primary">
          <GitBranch size={15} /> 创建支线
        </button>
      </form>

      <div className="branch-list" aria-busy={loading}>
        {branches.length ? (
          <div className="branch-list__header">
            <strong>已有支线</strong>
          </div>
        ) : null}
        {!branches.length && loading ? (
          <div className="branch-list__header">
            <strong>支线列表</strong>
            <Loader2 size={15} className="animate-spin" />
          </div>
        ) : null}
        {!branches.length && !loading ? <p className="character-muted">当前角色暂无支线。</p> : null}
        {branches.map((branch) => (
          <button
            type="button"
            key={branch.id}
            className={`branch-list-item ${selectedBranchId === branch.id ? 'active' : ''}`}
            onClick={() => setSelectedBranchId(branch.id)}
          >
            <BookOpen size={16} />
            <span>
              <strong>{branch.title}</strong>
              <small>
                锚点第 {branch.anchor_main_chapter} 章 · {branch.current_chapter_index}/{branch.target_chapters} 章
              </small>
            </span>
            <em>{STATUS_LABELS[branch.status] || branch.status}</em>
          </button>
        ))}
      </div>

      {selectedBranch && detail ? (
        <div className="branch-detail">
          <div className="branch-detail__header">
            <div>
              <h3>{detail.title}</h3>
              <small>主线第 {detail.anchor_main_chapter} 章之后的独立故事</small>
            </div>
            <div className="branch-detail__actions">
              {detail.status !== 'archived' &&
              detail.status !== 'generating' &&
              detail.current_chapter_index < detail.target_chapters ? (
                <button type="button" className="btn btn-secondary" onClick={() => generate(detail)}>
                  <Play size={14} /> 继续生成
                </button>
              ) : null}
              {detail.status !== 'archived' ? (
                <button
                  type="button"
                  className="icon-btn"
                  title="归档支线"
                  aria-label="归档支线"
                  onClick={() => archive(detail)}
                >
                  <Archive size={15} />
                </button>
              ) : null}
            </div>
          </div>
          {(detail.chapters || []).map((chapter) => (
            <article className="branch-chapter" key={chapter.id}>
              <div className="branch-chapter__header">
                <strong>
                  支线第 {chapter.chapter_index} 章 · {chapter.title || '未命名'}
                </strong>
                <span>{STATUS_LABELS[chapter.status] || chapter.status}</span>
              </div>
              {editing?.id === chapter.id ? (
                <>
                  <input
                    value={editing.title}
                    onChange={(event) => setEditing({ ...editing, title: event.target.value })}
                  />
                  <textarea
                    value={editing.content}
                    onChange={(event) => setEditing({ ...editing, content: event.target.value })}
                  />
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={saving}
                    onClick={() => saveChapter(chapter)}
                  >
                    <Save size={14} /> 保存支线章节
                  </button>
                </>
              ) : (
                <>
                  <p className="branch-chapter__content">{chapterContent(chapter) || '尚未生成正文。'}</p>
                  {detail.status !== 'archived' && chapterContent(chapter) ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() =>
                        setEditing({ id: chapter.id, title: chapter.title, content: chapterContent(chapter) })
                      }
                    >
                      编辑正文
                    </button>
                  ) : null}
                </>
              )}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
