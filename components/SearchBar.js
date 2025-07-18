export function SearchBar() {
  return (
    <div style={{ padding: '24px 32px', background: '#fff' }}>
      <input
        type="text"
        placeholder="Search recipes and restaurants"
        style={{
          width: '100%',
          padding: '12px 16px',
          fontSize: '16px',
          borderRadius: '24px',
          border: '1px solid #ddd'
        }}
      />
    </div>
  );
}
