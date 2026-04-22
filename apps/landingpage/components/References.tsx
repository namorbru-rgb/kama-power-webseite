const projects = [
  {
    title: 'Landwirtschaftsbetrieb Müller',
    location: 'Aargau, CH',
    kwp: 120,
    kwh: 128,
    type: 'PV + BESS',
    description:
      'Gesamtsystem aus Dachanlage und Batteriespeicher für maximalen Eigenverbrauch. Integration ins bestehende Stromnetz des Betriebs.',
    color: 'bg-blue-50',
  },
  {
    title: 'Gewerbepark Solaris',
    location: 'Zürich, CH',
    kwp: 280,
    kwh: 208,
    type: 'PV + LEG',
    description:
      'Lokale Elektrizitätsgemeinschaft mit 5 Gewerbemietern. KAMA übernimmt Abrechnung und Eigenverbrauchssteuerung vollautomatisch.',
    color: 'bg-amber-50',
  },
  {
    title: 'Molkerei Alpstein AG',
    location: 'Appenzell, CH',
    kwp: 95,
    kwh: 64,
    type: 'PV + BESS',
    description:
      'Photovoltaik auf der Produktionshalle mit AgroPower-Speicher für Lastspitzenreduktion. Amortisation in unter 8 Jahren.',
    color: 'bg-green-50',
  },
]

export default function References() {
  return (
    <section id="referenzen" className="bg-white py-24">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="text-accent font-semibold text-sm uppercase tracking-widest">
            Referenzprojekte
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl font-bold text-primary">
            Erfolgreich umgesetzte Anlagen
          </h2>
          <p className="mt-4 text-text-main/70 max-w-2xl mx-auto">
            Reale Projekte — nachhaltig, wirtschaftlich, zuverlässig.
          </p>
        </div>

        {/* Cards */}
        <div className="grid md:grid-cols-3 gap-8">
          {projects.map((project) => (
            <div
              key={project.title}
              className="rounded-2xl overflow-hidden border border-gray-100 shadow-sm hover:shadow-md transition-shadow duration-200"
            >
              {/* Placeholder image */}
              <div
                className={`${project.color} h-48 flex items-center justify-center`}
              >
                <div className="text-center">
                  <div className="text-5xl mb-2">🏭</div>
                  <span className="text-xs font-semibold text-primary/50 uppercase tracking-widest">
                    {project.type}
                  </span>
                </div>
              </div>

              {/* Content */}
              <div className="p-6">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-primary text-lg">
                    {project.title}
                  </h3>
                </div>
                <p className="text-xs text-text-main/50 mb-4 flex items-center gap-1">
                  <span>📍</span> {project.location}
                </p>
                <p className="text-sm text-text-main/70 mb-6 leading-relaxed">
                  {project.description}
                </p>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-4 border-t border-gray-100 pt-4">
                  <div>
                    <div className="text-xl font-bold text-primary">
                      {project.kwp} kWp
                    </div>
                    <div className="text-xs text-text-main/50">
                      Anlagengrösse
                    </div>
                  </div>
                  <div>
                    <div className="text-xl font-bold text-accent">
                      {project.kwh} kWh
                    </div>
                    <div className="text-xs text-text-main/50">
                      Batteriekapazität
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
