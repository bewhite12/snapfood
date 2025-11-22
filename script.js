// 환경 변수 설정 (대표님의 실제 값으로 변경)
const SUPABASE_URL = "https://qhlhxcedibkxotaeuygd.supabase.co"; 
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFobGh4Y2VkaWJreG90YWV1eWdkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mzc5MDY4NiwiZXhwIjoyMDc5MzY2Njg2fQ.Gourmb3YQwQod6W8Li2DfwpjRwEjIrQAj2dWHE5NkqE"; 

// Supabase 클라이언트 초기화
const { createClient } = supabase;
const supabaseClient = createClient(SUPABASE_URL, SUPABASE_KEY);

async function fetchRecipes() {
    console.log("레시피 목록을 불러오는 중...");
    
    // Supabase DB에서 레시피 데이터 가져오기
    const { data, error } = await supabaseClient
        .from('recipes')
        .select('*')
        .limit(10); 

    if (error) {
        console.error("데이터 로딩 실패:", error);
    } else {
        console.log("로딩된 레시피 수:", data.length);
        console.log(data); // 데이터가 콘솔에 찍히는지 확인용
    }
}

fetchRecipes();