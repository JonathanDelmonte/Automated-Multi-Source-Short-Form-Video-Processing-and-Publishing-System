/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Virtu Clips: preto e branco, como a logo. Os valores repetem o
        // tokens.css (literais para que bg-brass/10 compile); `brass` e o
        // acento, que agora e o branco -- o nome ficou, o valor mudou.
        paper: "oklch(13% 0 0 / <alpha-value>)",
        paper2: "oklch(16.5% 0 0 / <alpha-value>)",
        paper3: "oklch(20% 0 0 / <alpha-value>)",
        ink: "oklch(97% 0 0 / <alpha-value>)",
        ink2: "oklch(86% 0 0 / <alpha-value>)",
        muted: "oklch(64% 0 0 / <alpha-value>)",
        brass: "oklch(97% 0 0 / <alpha-value>)",
        brassink: "oklch(13% 0 0 / <alpha-value>)",
        coral: "oklch(68% 0.16 18 / <alpha-value>)",
        ok: "oklch(75% 0.11 150 / <alpha-value>)",
        warn: "oklch(78% 0.14 75 / <alpha-value>)",
        danger: "oklch(66% 0.18 25 / <alpha-value>)",
        // legacy aliases so untouched files degrade gracefully
        background: "oklch(13% 0 0 / <alpha-value>)",
        surface: "oklch(16.5% 0 0 / <alpha-value>)",
        primary: "oklch(97% 0 0 / <alpha-value>)",
        accent: "oklch(68% 0.16 18 / <alpha-value>)",
      },
      fontFamily: {
        display: "var(--font-display)",
        body: "var(--font-body)",
        sans: "var(--font-body)",
        serif: "var(--font-display)",
        mono: "var(--font-mono)",
      },
      borderColor: {
        rule: "var(--color-rule)",
        rule2: "var(--color-rule-2)",
      },
      borderRadius: {
        card: "var(--radius-card)",
        input: "var(--radius-input)",
      },
      fontSize: {
        micro: ["10.5px", { letterSpacing: "0.10em" }],
      },
      transitionTimingFunction: {
        out: "var(--ease-out)",
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade': 'fadeIn 0.4s var(--ease-out)',
        // mobile shell: the nav drawer flies in from the edge, sheets rise
        'slide-in-left': 'slideInLeft 0.24s var(--ease-out)',
        'sheet-up': 'sheetUp 0.26s var(--ease-out)',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideInLeft: {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(0)' },
        },
        sheetUp: {
          from: { transform: 'translateY(12px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
