export default function SitesPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center max-w-sm mx-auto px-4">
        <div className="w-16 h-16 mx-auto mb-4 rounded-2xl flex items-center justify-center"
             style={{ backgroundColor: '#1a2d5a' }}>
          <span className="text-2xl">⚡</span>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">KAMA Energie</h1>
        <p className="mt-2 text-gray-500 text-sm">
          Bitte Standort-ID in der URL angeben:
        </p>
        <p className="mt-1 text-gray-400 text-xs font-mono">
          /sites/&lt;site-id&gt;
        </p>
        <p className="mt-4 text-xs text-gray-400">
          Oder{' '}
          <span className="font-mono text-gray-500">DEFAULT_SITE_ID</span>{' '}
          in der Umgebungsvariable setzen.
        </p>
      </div>
    </main>
  );
}
