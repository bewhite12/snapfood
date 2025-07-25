export function Header() {
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '16px 32px',
      background: '#fff',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
    }}>
      <h1 style={{ margin: 0, color: '#FF6A00' }}>Snap Food</h1>
      <nav>
        <button style={{
          marginRight: '16px',
          background: '#FF6A00',
          color: '#fff',
          padding: '8px 16px',
          border: 'none',
          borderRadius: '4px'
        }}>인기 검색어</button>
        <button style={{
          background: 'transparent',
          border: 'none',
          color: '#333'
        }}>회원가입</button>
      </nav>
    </header>
  );
}
