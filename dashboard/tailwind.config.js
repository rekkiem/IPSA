/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg:       '#0a0e1a',
        surface:  '#111827',
        surface2: '#1a2235',
        border:   '#1e3a5f',
        cyan:     '#00d4ff',
        green:    '#00ff88',
        purple:   '#a855f7',
        red:      '#ff4d6d',
        yellow:   '#ffd166',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
        mono: ['JetBrains Mono', 'ui-monospace'],
      },
    },
  },
  plugins: [],
};
