import { Search } from 'lucide-react';

export default function GraphToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder = '搜索…',
  filters = [],
  activeFilter,
  onFilterChange,
  children,
}) {
  return (
    <div className="kg-toolbar">
      <div className="kg-search-wrap">
        <Search size={14} className="kg-search-icon" />
        <input
          type="text"
          className="form-input kg-search-input"
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      {filters.length > 0 && (
        <div className="kg-filter-group">
          {filters.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`btn ${activeFilter === f.id ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => onFilterChange(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}
