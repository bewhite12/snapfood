// 환경 변수 설정 (대표님의 실제 값으로 변경)
const SUPABASE_URL = "https://qhlhxcedibkxotaeuygd.supabase.co"; 
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFobGh4Y2VkaWJreG90YWV1eWdkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mzc5MDY4NiwiZXhwIjoyMDc5MzY2Njg2fQ.Gourmb3YQwQod6W8Li2DfwpjRwEjIrQAj2dWHE5NkqE"; 

// Supabase 클라이언트 초기화
// window.supabase를 사용하여 전역으로 불러온 라이브러리 객체를 사용합니다.
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY); 

// 레시피 목록을 화면에 렌더링하는 함수
function displayRecipes(recipes) {
    const listContainer = document.getElementById('recipe-list');
    listContainer.innerHTML = ''; // '로딩 중...' 메시지 삭제

    if (recipes.length === 0) {
        listContainer.innerHTML = '<p>아직 등록된 레시피가 없습니다.</p>';
        return;
    }

    recipes.forEach(recipe => {
        // 재료 목록을 HTML로 변환 (쿠팡 링크 포함)
        let ingredientsHtml = '<p><strong>필요 재료:</strong></p><ul>';
        // ingredients_json이 유효한 배열인지 확인
        if (Array.isArray(recipe.ingredients_json)) {
            recipe.ingredients_json.forEach(item => {
                // ⭐ 핵심 수익화 로직: 재료 이름과 쿠팡 링크를 함께 표시
                const purchaseLink = item.purchase_link || '#'; // 링크가 없으면 #으로 대체
                ingredientsHtml += `
                    <li>
                        ${item.name} (${item.amount || '적당량'}) 
                        <a href="${purchaseLink}" target="_blank" style="color: #ff6600; font-weight: bold;">[재료 구매 🛒]</a>
                    </li>
                `;
            });
        }
        ingredientsHtml += '</ul>';

        // 레시피 카드 생성
        const recipeCard = document.createElement('div');
        recipeCard.className = 'recipe-card';
        recipeCard.innerHTML = `
            <h3>${recipe.title || '제목 없음'}</h3>
            <p>${recipe.summary || '요약 없음'}</p>
            ${ingredientsHtml}
            <p><strong>조리 순서:</strong> ${recipe.method_text ? recipe.method_text.substring(0, 100) + '...' : '순서 없음'}</p>
            <p style="color: green; font-style: italic;">⭐ 팁: ${recipe.tips || '별도 팁 없음'}</p>
            <a href="${recipe.video_url || '#'}" target="_blank">원본 유튜브 영상 보기 ▶️</a>
        `;
        listContainer.appendChild(recipeCard);
    });
}

async function fetchAndDisplayRecipes() {
    console.log("레시피 목록을 불러오는 중...");
    
    // Supabase DB에서 레시피 데이터 가져오기
    const { data, error } = await supabaseClient
        .from('recipes')
        .select('*')
        .limit(20); // 20개로 늘려서 표시

    if (error) {
        console.error("데이터 로딩 실패 (RLS 또는 DB 접근 오류):", error);
        document.getElementById('recipe-list').innerHTML = '<p style="color: red;">데이터 로딩 실패. Supabase RLS 설정 또는 API 키를 확인해주세요.</p>';
    } else {
        console.log(`로딩된 레시피 수: ${data.length}`);
        displayRecipes(data); // 데이터가 성공하면 화면에 표시
    }
}

fetchAndDisplayRecipes(); // 함수 실행