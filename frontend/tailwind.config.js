/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        base: '#080F1C',
        surface: '#101B2D',
        card: '#142238',
        edge: '#24344F',
        accent: '#22C55E',
        teal: '#14B8A6',
        warn: '#F59E0B',
        danger: '#EF4444',
        ink: '#F8FAFC',
        muted: '#94A3B8',
      },
      fontFamily: {
        sans: [
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(34,197,94,0.18), 0 18px 40px -28px rgba(34,197,94,0.65)',
        panel: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 24px 60px -40px rgba(0,0,0,0.9)',
      },
      animation: {
        'fade-in': 'fadeIn 180ms ease-out',
        'pulse-soft': 'pulseSoft 2.4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
      },
    },
  },
  plugins: [],
}
