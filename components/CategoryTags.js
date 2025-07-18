export function CategoryTags({ tags }) {
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px',
      padding: '16px 32px',
      background: '#fff'
    }}>
      {tags.map((tag, idx) => (
        <span key={idx} style={{
          padding: '6px 12px',
          background: '#E3FCEF',
          borderRadius: '16px',
          fontSize: '14px'
        }}>
          {tag}
        </span>
      ))}
    </div>
  );
}
