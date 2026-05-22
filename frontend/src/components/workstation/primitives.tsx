import type { ReactNode } from 'react';

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <div className="block space-y-1.5 text-sm"><span className="font-medium text-slate-800">{label}</span>{children}{hint && <span className="block text-xs text-slate-400">{hint}</span>}</div>;
}

export function MiniStat({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-2xl border border-slate-200 bg-white/80 p-4 backdrop-blur"><p className="text-xs text-slate-400">{label}</p><p className="mt-1 font-bold text-slate-950">{value}</p></div>;
}

export function MetricCard({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-xl shadow-slate-200/70 backdrop-blur"><p className="text-sm text-slate-400">{label}</p><p className="mt-2 text-3xl font-black text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-400">{detail}</p></div>;
}

export function Notice({ tone, children }: { tone: 'amber' | 'red'; children: ReactNode }) {
  const classes = tone === 'amber' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-red-200 bg-red-50 text-red-700';
  return <div className={`rounded-2xl border p-4 text-sm ${classes}`}>{children}</div>;
}

export function StatusBadge({ status, formatStatusLabel = defaultFormatStatusLabel }: { status: string | undefined | null; formatStatusLabel?: (status: string | undefined | null) => string }) {
  const normalized = status ?? 'unknown';
  const positive = ['ok', 'active', 'completed', 'open', 'running'].includes(normalized);
  const paused = ['paused', 'pending', 'queued'].includes(normalized);
  const color = positive ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : paused ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-red-200 bg-red-50 text-red-700';
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${color}`}>{formatStatusLabel(normalized)}</span>;
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center"><p className="font-semibold text-slate-800">{title}</p><p className="mt-2 text-sm text-slate-400">{description}</p></div>;
}

export function InfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50/90 p-4"><h4 className="mb-3 font-semibold text-slate-950">{title}</h4>{children}</div>;
}

function defaultFormatStatusLabel(status: string | undefined | null): string {
  if (!status) return '未知';
  return status;
}
