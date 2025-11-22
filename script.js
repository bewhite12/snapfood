// 환경 변수 설정 (대표님의 실제 값으로 변경)
const SUPABASE_URL = "https://qhlhxcedibkxotaeuygd.supabase.co"; 
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFobGh4Y2VkaWJreG90YWV1eWdkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mzc5MDY4NiwiZXhwIjoyMDc5MzY2Njg2fQ.Gourmb3YQwQod6W8Li2DfwpjRwEjIrQAj2dWHE5NkqE"; 

// Supabase 클라이언트 초기화
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY); 

// 레시피 목록을 화면에 렌더링하는 함수
function displayRecipes(recipes) {
    const listContainer = document.getElementById('recipe-list');
    listContainer.innerHTML = ''; 

    if (recipes.length === 0) {
        listContainer.innerHTML = '<div class="col-12"><p class="text-center text-muted">아직 등록된 레시피가 없습니다. 크롤러를 실행해 주세요.</p></div>';
        return;
    }

    recipes.forEach(recipe => {
        // 재료 목록 HTML 생성 (수익화 링크 포함)
        let ingredientsHtml = '<ul class="list-unstyled small mt-2">';
        if (Array.isArray(recipe.ingredients_json)) {
            recipe.ingredients_json.slice(0, 3).forEach(item => { // 상위 3개 재료만 표시
                const purchaseLink = item.purchase_link || '#';
                ingredientsHtml += `
                    <li>
                        ${item.name} 
                        <a href="${purchaseLink}" target="_blank" class="text-warning text-decoration-none">[구매 🛒]</a>
                    </li>
                `;
            });
        }
        ingredientsHtml += '</ul>';

        const col = document.createElement('div');
        col.className = 'col';

        const recipeCard = document.createElement('div');
        recipeCard.className = 'card h-100 shadow-sm border-0'; // 부트스트랩 카드 디자인

        // 썸네일 이미지 표시 로직 추가: thumbnail_url이 없으면 대체 이미지 사용
        // DB에 저장된 1x1 투명 이미지가 로드될 것입니다.
        const imageUrl = recipe.thumbnail_url || 'https://via.placeholder.com/600x400?text=SnapFood'; 
        
        recipeCard.innerHTML = `
            <img src="${imageUrl}" class="card-img-top recipe-image" alt="${recipe.title || '레시피 이미지'}">
            <div class="card-body">
                <span class="badge bg-danger mb-2">${recipe.tags ? recipe.tags[0] : '미분류'}</span>
                <h5 class="card-title text-primary">${recipe.title || '제목 없음'}</h5>
                <p class="card-text small text-muted">${recipe.summary || '요약 없음'}</p>
                
                ${ingredientsHtml}
            </div>
            <div class="card-footer bg-white border-top-0">
                <a href="${recipe.video_url || '#'}" target="_blank" class="btn btn-outline-dark btn-sm w-100">원본 영상 보기 ▶️</a>
                
                <p class="mt-2 small text-muted">🎨 AI Prompt: ${recipe.image_prompt ? recipe.image_prompt.substring(0, 50) + '...' : '프롬프트 없음'}</p>
            </div>
        `;
        
        col.appendChild(recipeCard);
        listContainer.appendChild(col);
    });
}

async function fetchAndDisplayRecipes() {
    const { data, error } = await supabaseClient
        .from('recipes')
        .select('*')
        .limit(20); 

    if (error) {
        document.getElementById('recipe-list').innerHTML = '<div class="col-12"><p style="color: red;" class="text-center">데이터 로딩 실패. RLS/API 키를 확인해주세요.</p></div>';
    } else {
        displayRecipes(data); 
    }
}

fetchAndDisplayRecipes();