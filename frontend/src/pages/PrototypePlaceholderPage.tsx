type PrototypePlaceholderPageProps = {
  title: string
  description: string
}

function PrototypePlaceholderPage({ title, description }: PrototypePlaceholderPageProps) {
  return (
    <section className="bg-slate-800 border border-slate-700 rounded-xl p-6">
      <h1 className="text-2xl font-bold text-white">{title}</h1>
      <p className="text-slate-400 text-sm mt-2">{description}</p>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
          <p className="text-slate-500 text-xs uppercase">Estado</p>
          <p className="text-emerald-400 text-sm mt-1">Base integrada</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
          <p className="text-slate-500 text-xs uppercase">Siguiente paso</p>
          <p className="text-slate-200 text-sm mt-1">Migrar componentes visuales</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
          <p className="text-slate-500 text-xs uppercase">Datos</p>
          <p className="text-slate-200 text-sm mt-1">Pendiente de mapear API/mocks</p>
        </div>
      </div>
    </section>
  )
}

export default PrototypePlaceholderPage
