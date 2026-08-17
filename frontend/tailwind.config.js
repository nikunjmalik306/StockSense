/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          900: '#1e3a8a',
        },
        risk: {
          low: '#22c55e',
          medium: '#f59e0b',
          high: '#f97316',
          critical: '#ef4444',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f8fafc',
          subtle: '#f1f5f9',
        },
        sidebar: {
          DEFAULT: '#0f172a',
          deep: '#0c1222',
          hover: '#1e293b',
          active: '#1a2332',
          border: 'rgba(255, 255, 255, 0.08)',
          muted: '#94a3b8',
          faint: '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(15, 23, 42, 0.04)',
        elevated: '0 4px 12px rgba(15, 23, 42, 0.06)',
        glow: '0 0 0 1px rgba(37, 99, 235, 0.15), 0 8px 24px rgba(15, 23, 42, 0.25)',
      },
      backgroundImage: {
        'sidebar-gradient': 'linear-gradient(180deg, #0f172a 0%, #0c1222 100%)',
        'brand-gradient': 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
      },
    },
  },
  plugins: [],
}
