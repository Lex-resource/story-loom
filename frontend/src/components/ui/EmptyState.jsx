import { BookOpen, Plus } from 'lucide-react';

export default function EmptyState({ onCreate }) {
  return (
    <div className="empty-state">
      <div className="empty-state__mark" aria-hidden="true"><BookOpen size={26} /></div>
      <h2>书架还是空的</h2>
      <p>建立第一部作品后，章节、大纲与设定会集中在同一个创作空间。</p>
      <button className="btn btn-primary" onClick={onCreate}>
        <Plus size={16} /> 新建作品
      </button>
    </div>
  );
}
