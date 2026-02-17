/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          dark: '#0a1628',
          panel: '#111827',
          accent: {
            green: '#00d97e',
            red: '#e63757',
          },
        },
      },
      backgroundColor: {
        'base': '#0a1628',
        'panel': '#111827',
      },
      borderColor: {
        'panel': '#1f2937',
      },
    },
  },
  plugins: [],
}
