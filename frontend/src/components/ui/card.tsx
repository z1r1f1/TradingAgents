import type { PropsWithChildren } from 'react';

export function Card({ children }: PropsWithChildren) {
  return <section className="rounded-xl border border-slate-700 bg-slate-900/80 p-5 shadow-xl shadow-black/20">{children}</section>;
}

export function CardTitle({ children }: PropsWithChildren) {
  return <h2 className="mb-3 text-lg font-semibold text-white">{children}</h2>;
}
