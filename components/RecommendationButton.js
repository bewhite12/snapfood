export function RecommendationButton({ label }) {
  return (
    <button style={{
      flex: 1,
      margin: '0 8px',
      padding: '16px',
      background: '#FF6A00',
      color: '#fff',
      border: 'none',
      borderRadius: '4px',
      fontSize: '16px',
      cursor: 'pointer'
    }}>
      {label /* “점심 메뉴 추천” / “저녁 메뉴 추천” */}
    </button>
  );
}
