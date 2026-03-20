import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#e4f600",
          50: "#fdfff0",
          100: "#f9ffe0",
          200: "#f0ffa3",
          300: "#e4f600",
          400: "#d4e600",
          500: "#b8c800",
          600: "#96a300",
          700: "#707a00",
          800: "#4b5200",
          900: "#262900",
        },
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "glow": "glow 2s ease-in-out infinite alternate",
        "slide-up": "slide-up 0.5s ease-out both",
        "fade-in": "fade-in 0.4s ease-out both",
      },
      keyframes: {
        glow: {
          "0%": { opacity: "0.4" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
