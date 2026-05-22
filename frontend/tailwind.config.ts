import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border) / <alpha-value>)',
        background: 'hsl(var(--background) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        canvas: 'hsl(var(--canvas) / <alpha-value>)',
        surface: {
          DEFAULT: 'hsl(var(--surface) / <alpha-value>)',
          strong: 'hsl(var(--surface-strong) / <alpha-value>)',
          elevated: 'hsl(var(--surface-elevated) / <alpha-value>)'
        },
        panel: {
          DEFAULT: 'hsl(var(--panel) / <alpha-value>)',
          muted: 'hsl(var(--panel-muted) / <alpha-value>)'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
          soft: 'hsl(var(--accent-soft) / <alpha-value>)',
          strong: 'hsl(var(--accent-strong) / <alpha-value>)',
          foreground: 'hsl(var(--accent-foreground) / <alpha-value>)'
        },
        positive: {
          DEFAULT: 'hsl(var(--positive) / <alpha-value>)',
          soft: 'hsl(var(--positive-soft) / <alpha-value>)',
          foreground: 'hsl(var(--positive-foreground) / <alpha-value>)'
        },
        caution: {
          DEFAULT: 'hsl(var(--caution) / <alpha-value>)',
          soft: 'hsl(var(--caution-soft) / <alpha-value>)',
          foreground: 'hsl(var(--caution-foreground) / <alpha-value>)'
        },
        negative: {
          DEFAULT: 'hsl(var(--negative) / <alpha-value>)',
          soft: 'hsl(var(--negative-soft) / <alpha-value>)',
          foreground: 'hsl(var(--negative-foreground) / <alpha-value>)'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
          foreground: 'hsl(var(--muted-foreground) / <alpha-value>)'
        },
        primary: {
          DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
          foreground: 'hsl(var(--accent-foreground) / <alpha-value>)'
        }
      },
      borderColor: {
        subtle: 'hsl(var(--border) / 0.9)',
        strong: 'hsl(var(--border-strong) / 0.95)',
        accent: 'hsl(var(--accent) / 0.4)'
      },
      textColor: {
        primary: 'hsl(var(--foreground) / 1)',
        muted: 'hsl(var(--muted-foreground) / 1)',
        subtle: 'hsl(var(--subtle-foreground) / 1)',
        accent: 'hsl(var(--accent) / 1)',
        positive: 'hsl(var(--positive-foreground) / 1)',
        caution: 'hsl(var(--caution-foreground) / 1)',
        negative: 'hsl(var(--negative-foreground) / 1)'
      },
      backgroundImage: {
        'grid-shell': 'linear-gradient(hsl(var(--grid-line) / 0.12) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--grid-line) / 0.12) 1px, transparent 1px)',
        'radial-focus': 'radial-gradient(circle at top, hsl(var(--accent) / 0.2), transparent 55%)',
        'panel-sheen': 'linear-gradient(135deg, hsl(var(--surface-elevated) / 0.96), hsl(var(--surface) / 0.88))'
      },
      boxShadow: {
        panel: '10px 10px 0 hsl(var(--canvas) / 0.92)',
        float: '14px 14px 0 hsl(var(--canvas) / 0.9)',
        glow: '0 0 0 1px hsl(var(--accent) / 0.16), 10px 10px 0 hsl(var(--canvas) / 0.9)'
      },
      borderRadius: {
        panel: '0.5rem',
        card: '0.5rem',
        pill: '999px'
      },
      fontFamily: {
        sans: [
          '"Avenir Next"',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          '"Microsoft YaHei"',
          '"PingFang SC"',
          'sans-serif'
        ]
      },
      letterSpacing: {
        panel: '0.14em',
        data: '0'
      }
    }
  },
  plugins: []
} satisfies Config;
