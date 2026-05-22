import type { ButtonHTMLAttributes, PropsWithChildren } from 'react';

export function Button({ className = '', children, ...props }: PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>>) {
  return <button className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-card border border-strong bg-primary px-4 py-2 text-sm font-bold text-primary-foreground transition hover:-translate-y-0.5 hover:bg-accent-strong disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 ${className}`} {...props}>{children}</button>;
}
