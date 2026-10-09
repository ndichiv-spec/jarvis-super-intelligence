import Link from 'next/link';
import { ArrowRight, CircleHelp, Settings2 } from 'lucide-react';

interface CapabilityLink {
  label: string;
  href: string;
  description: string;
}

interface FeatureNotConfiguredPageProps {
  title: string;
  summary: string;
  links: CapabilityLink[];
}

export function FeatureNotConfiguredPage({
  title,
  summary,
  links,
}: FeatureNotConfiguredPageProps) {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 text-slate-100 sm:px-8 sm:py-10">
      <div className="mb-8 border-b border-slate-800/80 pb-6">
        <p className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-indigo-200/80">
          <span className="h-px w-6 bg-indigo-300/70" />
          JARVIS / Platform capability
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-[32px]">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">{summary}</p>
      </div>

      <section
        aria-labelledby="capability-status"
        className="relative overflow-hidden border border-slate-800 bg-[#0b1220] p-5 sm:p-7"
      >
        <div aria-hidden="true" className="absolute inset-y-0 left-0 w-[2px] bg-indigo-300/70" />
        <div className="flex items-start gap-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-indigo-300/15 bg-indigo-300/[0.07] text-indigo-200">
            <Settings2 aria-hidden="true" className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="mb-2 inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/70 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-300">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-slate-500" />
              Not configured
            </p>
            <h2 id="capability-status" className="text-lg font-medium text-slate-100">
              No connected service is reporting this capability.
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              This route is retained for navigation compatibility. There is no configured backend contract for its data or actions, so JARVIS is not showing sample metrics or implying that work has run.
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="available-capabilities" className="mt-8">
        <div className="mb-4 flex items-center gap-2">
          <CircleHelp aria-hidden="true" className="h-4 w-4 text-slate-500" />
          <h2 id="available-capabilities" className="text-sm font-semibold text-slate-200">
            Available workspace routes
          </h2>
        </div>
        <div className="divide-y divide-slate-800/80 border-y border-slate-800/80">
          {links.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="group flex items-center justify-between gap-4 py-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-300"
            >
              <span>
                <span className="block text-sm font-medium text-slate-200 transition-colors group-hover:text-indigo-100">{item.label}</span>
                <span className="mt-1 block text-xs leading-5 text-slate-500">{item.description}</span>
              </span>
              <ArrowRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-indigo-200" />
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
