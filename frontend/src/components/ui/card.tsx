import type { PropsWithChildren } from 'react';

export function Card({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-xl shadow-slate-200/70 backdrop-blur ${className}`}>{children}</section>;
}

export function CardTitle({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <h2 className={`mb-4 text-lg font-bold text-slate-950 ${className}`}>{children}</h2>;
}
