import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'KAMA GmbH — Solaranlagen & Batteriespeicher für Unternehmen',
  description:
    'KAMA plant, baut und bewirtschaftet gewerbliche Solaranlagen, Batteriespeicher (BESS) und lokale Elektrizitätsgemeinschaften (LEG) in der Schweiz.',
  openGraph: {
    title: 'KAMA GmbH — Solaranlagen & Batteriespeicher für Unternehmen',
    description:
      'Wir planen, bauen und bewirtschaften Ihre Energieanlage — von der Analyse bis zum Betrieb.',
    images: ['/og-image.jpg'],
    locale: 'de_CH',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  )
}
