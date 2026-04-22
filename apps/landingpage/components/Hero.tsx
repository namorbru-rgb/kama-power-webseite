export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center bg-primary overflow-hidden">
      {/* Background pattern */}
      <div
        className="absolute inset-0 opacity-10"
        style={{
          backgroundImage:
            'repeating-linear-gradient(45deg, #f5a623 0, #f5a623 1px, transparent 0, transparent 50%)',
          backgroundSize: '24px 24px',
        }}
      />

      {/* Gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary via-primary/95 to-blue-900/80" />

      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-32 pt-40">
        <div className="max-w-3xl">
          {/* Badge */}
          <span className="inline-block bg-accent/20 text-accent text-xs font-semibold uppercase tracking-widest px-3 py-1 rounded-full mb-6">
            Schweizer Energielösungen
          </span>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6">
            Solaranlage +{' '}
            <span className="text-accent">Batteriespeicher</span>{' '}
            für Ihr Unternehmen
          </h1>

          {/* Sub-headline */}
          <p className="text-lg sm:text-xl text-white/80 mb-10 leading-relaxed max-w-2xl">
            Wir planen, bauen und bewirtschaften Ihre Energieanlage — von der
            Analyse bis zum Betrieb.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4">
            <a
              href="#kontakt"
              className="inline-block bg-accent text-white font-bold text-lg px-8 py-4 rounded-lg hover:bg-amber-500 transition-colors text-center shadow-lg"
            >
              Kostenlose Beratung anfragen
            </a>
            <a
              href="#leistungen"
              className="inline-block border-2 border-white/40 text-white font-semibold text-lg px-8 py-4 rounded-lg hover:border-white hover:bg-white/10 transition-colors text-center"
            >
              Leistungen entdecken
            </a>
          </div>

          {/* Key figures */}
          <div className="mt-16 grid grid-cols-3 gap-6 border-t border-white/20 pt-10">
            {[
              { value: '64–208 kWh', label: 'BESS-Kapazität' },
              { value: '100%', label: 'Schweizer Qualität' },
              { value: 'LEG', label: 'Eigenverbrauch optimiert' },
            ].map((stat) => (
              <div key={stat.label}>
                <div className="text-2xl font-bold text-accent">{stat.value}</div>
                <div className="text-sm text-white/60 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom wave */}
      <div className="absolute bottom-0 left-0 right-0">
        <svg
          viewBox="0 0 1440 80"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="w-full"
        >
          <path
            d="M0 80H1440V40C1200 80 960 0 720 20C480 40 240 60 0 40V80Z"
            fill="#f8f9fa"
          />
        </svg>
      </div>
    </section>
  )
}
