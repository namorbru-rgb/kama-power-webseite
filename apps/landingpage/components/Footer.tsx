export default function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="bg-primary text-white/80">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid sm:grid-cols-3 gap-10 mb-10">
          {/* Brand */}
          <div>
            <div className="text-white font-bold text-2xl tracking-widest mb-3">
              K<span className="text-accent">▲</span>MA
            </div>
            <p className="text-sm leading-relaxed">
              KAMA GmbH<br />
              Energielösungen für Gewerbe und Landwirtschaft in der Schweiz.
            </p>
          </div>

          {/* Contact */}
          <div>
            <h4 className="text-white font-semibold mb-3 text-sm uppercase tracking-widest">
              Kontakt
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a
                  href="mailto:verkauf@kama-power.ch"
                  className="hover:text-accent transition-colors"
                >
                  verkauf@kama-power.ch
                </a>
              </li>
              <li>Schweiz</li>
            </ul>
          </div>

          {/* Links */}
          <div>
            <h4 className="text-white font-semibold mb-3 text-sm uppercase tracking-widest">
              Links
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="/impressum" className="hover:text-accent transition-colors">
                  Impressum
                </a>
              </li>
              <li>
                <a href="/datenschutz" className="hover:text-accent transition-colors">
                  Datenschutz
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="border-t border-white/10 pt-6 text-xs text-center text-white/40">
          © {year} KAMA GmbH — Alle Rechte vorbehalten
        </div>
      </div>
    </footer>
  )
}
