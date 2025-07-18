import { Header } from '../components/Header';
import { SearchBar } from '../components/SearchBar';
import { Slider } from '../components/Slider';
import { RecommendationButton } from '../components/RecommendationButton';
import { CategoryTags } from '../components/CategoryTags';
import { Footer } from '../components/Footer';

export default function Home() {
  // 한글 타이틀로만 구성
  const mainSliders = [
    { image: '/images/kimchi.jpg', title: '김치찌개' },
    { image: '/images/shrimp.jpg', title: '마늘버터새우' },
    { image: '/images/croissant.jpg', title: '크림필드 크루아상' },
  ];
  const tags = ['한식','중식','일식','양식','소고기','돼지고기','치킨'];

  return (
    <>
      <Header />
      <SearchBar />
      <Slider items={mainSliders} />

      <section style={{ display:'flex', gap:16, padding:'24px 32px' }}>
        <RecommendationButton label="점심 메뉴 추천" />
        <RecommendationButton label="저녁 메뉴 추천" />
      </section>

      {/* 아래 슬라이더들도 동일 데이터 또는 분류별 데이터로 교체 */}
      <Slider items={mainSliders} />
      <Slider items={mainSliders} />
      <Slider items={mainSliders} />

      <CategoryTags tags={tags} />
      <Footer />
    </>
  );
}
