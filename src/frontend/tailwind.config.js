/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class',
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            },
            colors: {
                background: 'rgb(var(--bg-background) / <alpha-value>)',
                surface: 'rgb(var(--bg-surface) / <alpha-value>)',
                'surface-hover': 'rgb(var(--bg-surface-hover) / <alpha-value>)',
                border: 'rgb(var(--border-color) / <alpha-value>)',
                primary: 'rgb(var(--text-primary) / <alpha-value>)',
                secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
                muted: 'rgb(var(--text-muted) / <alpha-value>)',
                brand: {
                    DEFAULT: 'rgb(var(--color-brand) / <alpha-value>)',
                    glow: 'rgb(var(--color-brand) / 0.15)',
                }
            },
            boxShadow: {
                'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
                'neon': '0 0 10px rgb(var(--color-brand) / 0.5), 0 0 20px rgb(var(--color-brand) / 0.3)',
            }
        },
    },
    plugins: [],
}
