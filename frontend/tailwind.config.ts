import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(214 32% 91%)',
        background: 'hsl(222 47% 11%)',
        card: 'hsl(222 47% 14%)',
        primary: 'hsl(142 71% 45%)'
      }
    }
  },
  plugins: []
} satisfies Config;
