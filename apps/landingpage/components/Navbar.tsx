export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-primary shadow-md">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <a href="#" className="flex items-center gap-2">
          <span className="text-white font-bold text-2xl tracking-widest">
            K<span className="text-accent">▲</span>MA
          </span>
        </a>
        <div className="hidden md:flex items-center gap-8 text-sm text-white/80">
          <a href="#leistungen" className="hover:text-accent transition-colors">Leistungen</a>
          <a href="#referenzen" className="hover:text-accent transition-colors">Referenzen</a>
          <a href="#kontakt" className="hover:text-accent transition-colors">Kontakt</a>
        </div>
        <a
          href="#kontakt"
          className="bg-accent text-white text-sm font-semibold px-4 py-2 rounded-md hover:bg-amber-500 transition-colors"
        >
          Beratung anfragen
        </a>
      </div>
    </nav>
  )
}
