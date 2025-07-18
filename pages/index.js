import { Header } from '../components/Header';
import { SearchBar } from '../components/SearchBar';
import { Slider } from '../components/Slider';
import { RecommendationButton } from '../components/RecommendationButton';
import { CategoryTags } from '../components/CategoryTags';
import { Footer } from '../components/Footer';

export default function Home() {
  // 예시 데이터: 실제 자동화에서는 스크립트가 items 및 tags 배열을 채워 줍니다.
  const sliderItems = [
    { image: '/images/kimchi.jpg', title: 'Kimchi jjigae' },
    { image: '/images/shrimp.jpg', title: 'Garlic butter shrimp' },
    { image: '/images/croissant.jpg', title: 'Creamfield croissant' },
  ];
  const tags = ['Korean','Chinese','Japanese','Western','Beef','Pork','Chicken'];

  return (
    <>
      <Header />
      <SearchBar />
      <Slider items={sliderItems} />
      <section style={{ display: 'flex', padding: '0 32px', margin: '24px 0' }}>
        <RecommendationButton label="What to eat for lunch?" />
        <RecommendationButton label="What to eat for dinner?" />
      </section>
      <Slider items={[
        // Top Recipes 예시
        { image: '/images/recipe1.jpg', title: '' },
        { image: '/images/recipe2.jpg', title: '' },
        // … 나머지 5개
      ]} />
      <Slider items={[
        // Top Restaurants 예시
        { image: '/images/rest1.jpg', title: '' },
        // … 나머지
      ]} />
      <Slider items={[
        // TV Featured
        { image: '/images/tv1.jpg', title: '' },
        // … 나머지
      ]} />
      <CategoryTags tags={tags} />
      <Footer />
    </>
  );
}
