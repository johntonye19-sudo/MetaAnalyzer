import { FileSearch, FolderKanban, ShieldCheck } from 'lucide-react'

const features = [
  {
    icon: FolderKanban,
    title: 'Investigation workspace',
    description: 'Organize forensic work into secure, trackable investigations.',
  },
  {
    icon: FileSearch,
    title: 'Evidence analysis',
    description: 'Prepare to inspect evidence and its extracted metadata in one place.',
  },
  {
    icon: ShieldCheck,
    title: 'Evidence integrity',
    description: 'Build workflows around preserved originals and verifiable records.',
  },
]

export default function App() {
  return (
    <main className="min-h-screen px-6 py-12 sm:px-10 lg:px-16">
      <div className="mx-auto max-w-5xl">
        <header className="mb-16 flex items-center gap-3">
          <div className="rounded-xl bg-cyan-400/10 p-2 text-cyan-300">
            <FileSearch aria-hidden="true" size={24} />
          </div>
          <span className="text-lg font-semibold tracking-wide text-white">MetaAnalyzer</span>
          <span className="ml-auto rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">
            Foundation preview
          </span>
        </header>

        <section aria-labelledby="welcome-title" className="mb-12 max-w-3xl">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Digital forensics workspace
          </p>
          <h1 id="welcome-title" className="mb-5 text-4xl font-bold tracking-tight text-white sm:text-6xl">
            Investigate metadata with confidence.
          </h1>
          <p className="max-w-2xl text-lg leading-8 text-slate-300">
            A foundation for managing investigations, analyzing digital evidence, and protecting the integrity of original files.
          </p>
        </section>

        <section aria-label="Platform capabilities" className="grid gap-4 md:grid-cols-3">
          {features.map(({ icon: Icon, title, description }) => (
            <article key={title} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
              <Icon aria-hidden="true" className="mb-5 text-cyan-300" size={24} />
              <h2 className="mb-2 text-base font-semibold text-white">{title}</h2>
              <p className="text-sm leading-6 text-slate-400">{description}</p>
            </article>
          ))}
        </section>

        <footer className="mt-12 border-t border-slate-800 pt-6 text-sm text-slate-500">
          Phase 1 foundation · API status available at <code className="text-cyan-300">/api/health</code>
        </footer>
      </div>
    </main>
  )
}
