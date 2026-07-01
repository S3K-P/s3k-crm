import { redirect } from 'next/navigation';
import { BRAND } from '@/config/site';

export default function Home() {
  redirect(BRAND.homeHref);
}
