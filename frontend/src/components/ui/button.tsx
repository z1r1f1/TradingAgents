import type { ButtonHTMLAttributes, PropsWithChildren } from 'react';

export function Button({ className = '', children, ...props }: PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>>) {
  return <button className={`rounded-xl bg-cyan-600 px-4 py-2 text-sm font-bold text-white shadow-sm shadow-cyan-100 transition hover:-translate-y-0.5 hover:bg-cyan-500 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 ${className}`} {...props}>{children}</button>;
}
