import { Header } from '../components/Header';
import { SearchBar } from '../components/SearchBar';
import { Slider } from '../components/Slider';
import { RecommendationButton } from '../components/RecommendationButton';
import { CategoryTags } from '../components/CategoryTags';
import { Footer } from '../components/Footer';

export default function Home() {
  const mainSliders = [
    { image: '/images/kimchi.jpg', title: 'Kimchi jjigae' },
    { image: '/images/shrimp.jpg', title: 'Garlic butter shrimp' },
    { image: '/images/croissant.jpg', title: 'Creamfield croissant' },
  ];
  const tags = ['Korean','Chinese','Japanese','Western','Beef','Pork','Chicken'];

  return (
    <>
      <Header />
      <SearchBar />

      {/* 메인 슬라이더 */}
      <Slider items={mainSliders} />

      {/* 추천 버튼 */}
      <section style={{
          display: 'flex',
          gap: '16px',
          padding: '24px 32px',
        }}>
        <RecommendationButton label="What to eat for lunch?" />
        <RecommendationButton label="What to eat for dinner?" />
      </section>

      {/* Top Recipes & Top Restaurants & TV Featured */}
      <Slider items={mainSliders /* 예시 동일 구조로 대체하세요 */} />
      <Slider items={mainSliders} />
      <Slider items={mainSliders} />

      {/* 카테고리 태그 */}
      <CategoryTags tags={tags} />

      <Footer />
    </>
  );
}
