import type { PropsWithChildren } from 'react';

export function Card({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`rounded-card border border-strong bg-surface p-5 shadow-panel backdrop-blur ${className}`}>{children}</section>;
}

export function CardTitle({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <h2 className={`mb-4 text-lg font-bold text-primary ${className}`}>{children}</h2>;
}
