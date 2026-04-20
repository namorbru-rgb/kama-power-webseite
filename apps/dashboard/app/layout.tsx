import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'KAMA Energie Dashboard',
  description: 'Energiemonitoring für Schweizer Landwirtschaft und KMU',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
