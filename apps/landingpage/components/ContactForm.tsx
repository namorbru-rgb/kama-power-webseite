'use client'

import { useState } from 'react'

type FormState = 'idle' | 'loading' | 'success' | 'error'

export default function ContactForm() {
  const [state, setState] = useState<FormState>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setState('loading')
    setErrorMsg('')

    const form = e.currentTarget
    const data = {
      name: (form.elements.namedItem('name') as HTMLInputElement).value,
      firma: (form.elements.namedItem('firma') as HTMLInputElement).value,
      email: (form.elements.namedItem('email') as HTMLInputElement).value,
      telefon: (form.elements.namedItem('telefon') as HTMLInputElement).value,
      anliegen: (form.elements.namedItem('anliegen') as HTMLSelectElement).value,
      source: 'kama-power.ch',
    }

    const webhookUrl = process.env.NEXT_PUBLIC_WEBHOOK_URL
    if (!webhookUrl) {
      setState('error')
      setErrorMsg('Webhook-URL nicht konfiguriert. Bitte kontaktieren Sie uns direkt.')
      return
    }

    try {
      const res = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setState('success')
      form.reset()
    } catch (err) {
      setState('error')
      setErrorMsg('Beim Senden ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut oder schreiben Sie uns direkt an verkauf@kama-power.ch.')
    }
  }

  return (
    <section id="kontakt" className="bg-background-alt py-24">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-2 gap-16 items-start">
          {/* Left: copy */}
          <div>
            <span className="text-accent font-semibold text-sm uppercase tracking-widest">
              Kontakt
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-bold text-primary mb-6">
              Kostenlose Beratung anfragen
            </h2>
            <p className="text-text-main/70 leading-relaxed mb-8">
              Schildern Sie uns Ihr Vorhaben — wir melden uns innerhalb von{' '}
              <strong>24 Stunden</strong> mit einer ersten Einschätzung.
            </p>

            <div className="space-y-4">
              {[
                { icon: '📍', text: 'KAMA GmbH, Schweiz' },
                { icon: '✉️', text: 'verkauf@kama-power.ch' },
              ].map((item) => (
                <div key={item.text} className="flex items-center gap-3 text-text-main/70">
                  <span className="text-xl">{item.icon}</span>
                  <span>{item.text}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Right: form */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
            {state === 'success' ? (
              <div className="text-center py-8">
                <div className="text-5xl mb-4">✅</div>
                <h3 className="text-xl font-bold text-primary mb-2">
                  Anfrage gesendet!
                </h3>
                <p className="text-text-main/70">
                  Vielen Dank. Wir melden uns innerhalb von 24 Stunden bei Ihnen.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="grid sm:grid-cols-2 gap-5">
                  <div>
                    <label
                      htmlFor="name"
                      className="block text-sm font-medium text-text-main mb-1.5"
                    >
                      Name <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="name"
                      name="name"
                      type="text"
                      required
                      placeholder="Max Mustermann"
                      className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="firma"
                      className="block text-sm font-medium text-text-main mb-1.5"
                    >
                      Firma
                    </label>
                    <input
                      id="firma"
                      name="firma"
                      type="text"
                      placeholder="Muster AG"
                      className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition"
                    />
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="email"
                    className="block text-sm font-medium text-text-main mb-1.5"
                  >
                    E-Mail <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    required
                    placeholder="max@muster.ch"
                    className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition"
                  />
                </div>

                <div>
                  <label
                    htmlFor="telefon"
                    className="block text-sm font-medium text-text-main mb-1.5"
                  >
                    Telefon
                  </label>
                  <input
                    id="telefon"
                    name="telefon"
                    type="tel"
                    placeholder="+41 79 000 00 00"
                    className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition"
                  />
                </div>

                <div>
                  <label
                    htmlFor="anliegen"
                    className="block text-sm font-medium text-text-main mb-1.5"
                  >
                    Anliegen <span className="text-red-500">*</span>
                  </label>
                  <select
                    id="anliegen"
                    name="anliegen"
                    required
                    defaultValue=""
                    className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition bg-white"
                  >
                    <option value="" disabled>
                      Bitte wählen…
                    </option>
                    <option value="Solar">Solar (Photovoltaik)</option>
                    <option value="BESS">Batteriespeicher (BESS)</option>
                    <option value="LEG">
                      LEG (Lokale Elektrizitätsgemeinschaft)
                    </option>
                    <option value="Allgemein">Allgemeine Anfrage</option>
                  </select>
                </div>

                {state === 'error' && (
                  <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                    {errorMsg}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={state === 'loading'}
                  className="w-full bg-accent text-white font-bold py-3 rounded-lg hover:bg-amber-500 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {state === 'loading' ? 'Wird gesendet…' : 'Beratung anfragen'}
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
