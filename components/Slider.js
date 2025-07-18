export function Slider({ items }) {
  return (
    <div style={{
      display: 'flex',
      overflowX: 'auto',
      gap: '16px',
      padding: '16px 32px',
      background: '#fff'
    }}>
      {items.map((item, idx) => (
        <div key={idx} style={{
          minWidth: '300px',
          borderRadius: '8px',
          overflow: 'hidden',
          boxShadow: '0 2px 6px rgba(0,0,0,0.1)'
        }}>
          <img
            src={item.image}
            alt={item.title}
            style={{ width: '100%', display: 'block' }}
          />
          <div style={{ padding: '8px', fontWeight: 'bold' }}>
            {item.title}
          </div>
        </div>
      ))}
    </div>
  );
}
