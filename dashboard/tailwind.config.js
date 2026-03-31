/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        dark: { 50: '#1a1a2e', 100: '#16162a', 200: '#0f0f1a', 300: '#0a0a0f' },
        neon: { cyan: '#00d4ff', blue: '#0066ff', purple: '#8b5cf6' },
        gold: { light: '#ffd700', DEFAULT: '#ff9f1c', dark: '#ff6b35' },
        profit: '#00e676',
        loss: '#ff3366',
      },
      boxShadow: {
        glow: '0 0 20px rgba(0, 212, 255, 0.3)',
        'glow-lg': '0 0 40px rgba(0, 212, 255, 0.4)',
        'glow-gold': '0 0 20px rgba(255, 159, 28, 0.3)',
        'glow-profit': '0 0 15px rgba(0, 230, 118, 0.3)',
        'glow-loss': '0 0 15px rgba(255, 51, 102, 0.3)',
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'float': 'float 3s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'count-up': 'count-up 1s ease-out',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(0, 212, 255, 0.2)' },
          '50%': { boxShadow: '0 0 40px rgba(0, 212, 255, 0.5)' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
};
