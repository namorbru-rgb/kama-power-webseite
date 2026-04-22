const services = [
  {
    icon: '☀️',
    title: 'Photovoltaik / Solar',
    subtitle: 'Planung, Lieferung, Montage',
    description:
      'Von der Potenzialanalyse über die Dimensionierung bis zur schlüsselfertigen Montage. Wir setzen massgeschneiderte PV-Anlagen für Gewerbe und Landwirtschaft um.',
    bullets: [
      'Standortanalyse & Ertragsprognose',
      'Behördliche Bewilligungen',
      'Installation & Inbetriebnahme',
      'Monitoring & Wartung',
    ],
  },
  {
    icon: '🔋',
    title: 'Batteriespeicher (BESS)',
    subtitle: 'AgroPower-Systeme, 64–208 kWh',
    description:
      'Unsere AgroPower-Batteriespeicher machen Ihren Betrieb unabhängig vom Stromnetz. Eigenverbrauch maximieren, Spitzenlast kappen, überschüssige Energie speichern.',
    bullets: [
      'Kapazitäten 64 bis 208 kWh',
      'Spitzenlastmanagement',
      'Netzeinspeisung & Regelenergie',
      'Fernüberwachung via KAMA-net',
    ],
  },
  {
    icon: '⚡',
    title: 'LEG-Bewirtschaftung',
    subtitle: 'Lokale Elektrizitätsgemeinschaft',
    description:
      'Mit einer lokalen Elektrizitätsgemeinschaft (LEG) teilen Gebäude und Unternehmen ihren Solarstrom. Wir übernehmen die gesamte Bewirtschaftung und Abrechnung.',
    bullets: [
      'Eigenverbrauchsoptimierung',
      'Automatische Verbrauchssteuerung',
      'Transparente Abrechnung',
      'Rechtskonforme LEG-Verwaltung (CH)',
    ],
  },
]

export default function Services() {
  return (
    <section id="leistungen" className="bg-background-alt py-24">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="text-accent font-semibold text-sm uppercase tracking-widest">
            Unsere Leistungen
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl font-bold text-primary">
            Alles aus einer Hand
          </h2>
          <p className="mt-4 text-text-main/70 max-w-2xl mx-auto">
            Von der Planung bis zum laufenden Betrieb begleiten wir Sie in allen
            Schritten Ihrer Energiewende.
          </p>
        </div>

        {/* Cards */}
        <div className="grid md:grid-cols-3 gap-8">
          {services.map((service) => (
            <div
              key={service.title}
              className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 hover:shadow-md hover:-translate-y-1 transition-all duration-200"
            >
              <div className="text-4xl mb-4">{service.icon}</div>
              <h3 className="text-xl font-bold text-primary mb-1">
                {service.title}
              </h3>
              <p className="text-accent text-sm font-semibold mb-4">
                {service.subtitle}
              </p>
              <p className="text-text-main/70 text-sm leading-relaxed mb-6">
                {service.description}
              </p>
              <ul className="space-y-2">
                {service.bullets.map((bullet) => (
                  <li
                    key={bullet}
                    className="flex items-start gap-2 text-sm text-text-main/80"
                  >
                    <span className="text-accent font-bold mt-0.5">✓</span>
                    {bullet}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
