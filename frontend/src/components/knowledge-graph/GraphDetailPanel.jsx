export default function GraphDetailPanel({ title, content, placeholder }) {
  return (
    <aside className="kg-detail-panel">
      {title ? (
        <>
          <h4 className="kg-detail-title">{title}</h4>
          <div className="kg-detail-content">{content}</div>
        </>
      ) : (
        <div className="kg-detail-placeholder">{placeholder}</div>
      )}
    </aside>
  );
}
