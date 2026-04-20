import { redirect } from 'next/navigation';

// In production, fetch the site list and redirect to the first site.
// For MVP, use a fixed default site ID from env or redirect to /sites.
export default function Home() {
  const defaultSite = process.env.DEFAULT_SITE_ID;
  if (defaultSite) {
    redirect(`/sites/${defaultSite}`);
  }
  redirect('/sites');
}
