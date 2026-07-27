import {
  Activity,
  ArrowLeft,
  BookOpen,
  Database,
  Settings,
  SlidersHorizontal,
  WifiOff,
} from 'lucide-react';

const PAGE_TITLES = {
  shelf: '作品书架',
  workspace: '创作现场',
  docs: '设定编译库',
  settings: '系统设置',
  system: '流程与提示词',
};

export default function AppShell({
  activeTab,
  activeProject,
  backendStatus,
  onNavigate,
  onLeaveProject,
  headerActions,
  children,
}) {
  const destinations = [
    { id: 'shelf', label: '作品', icon: BookOpen },
    ...(activeProject ? [
      { id: 'workspace', label: '创作', icon: Activity },
      { id: 'docs', label: '设定', icon: Database },
    ] : []),
    { id: 'settings', label: '设置', icon: Settings },
    { id: 'system', label: '流程', icon: SlidersHorizontal },
  ];
  const title = PAGE_TITLES[activeTab] || PAGE_TITLES.shelf;

  return (
    <div className="app-container">
      <aside className="sidebar" aria-label="主导航">
        <div className="sidebar-header">
          <span className="brand-mark" aria-hidden="true"><BookOpen size={22} /></span>
          <div className="brand-copy">
            <strong>墨韵书坊</strong>
            <span>小说创作工作台</span>
          </div>
        </div>
        <nav className="nav-links">
          {destinations.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={`nav-item ${activeTab === id ? 'active' : ''}`}
              onClick={() => onNavigate(id)}
              aria-current={activeTab === id ? 'page' : undefined}
              title={label}
            >
              <Icon size={19} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        {activeProject ? (
          <div className="sidebar-footer">
            <div className="sidebar-project">
              <span>当前作品</span>
              <strong title={activeProject.title}>{activeProject.title}</strong>
              <small>{activeProject.current_chapter || 0} / {activeProject.target_chapters || 0} 章</small>
            </div>
            <button className="icon-btn sidebar-leave" onClick={onLeaveProject} title="退出当前作品" aria-label="退出当前作品">
              <ArrowLeft size={17} />
            </button>
          </div>
        ) : null}
      </aside>

      <main className="main-content">
        <header className="top-bar">
          <div className="top-bar__title">
            <span>{title}</span>
            {activeProject && activeTab !== 'shelf' ? <strong>{activeProject.title}</strong> : null}
          </div>
          <div className="top-bar__actions">{headerActions}</div>
        </header>
        {backendStatus === 'offline' ? (
          <div className="connection-banner" role="alert">
            <WifiOff size={17} />
            <span>后端服务暂时不可用，保存与生成操作已受影响。</span>
            <button type="button" onClick={() => onNavigate('settings')}>检查连接</button>
          </div>
        ) : null}
        <div className="content-pane">{children}</div>
      </main>
    </div>
  );
}
