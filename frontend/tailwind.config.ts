import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./features/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
      },
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        navy: {
          900: "#090B2D",
          800: "#11133F",
        },
        brand: {
          violet: "#5B4FF7",
          purple: "#7C3AED",
          magenta: "#C03BE8",
          lavender: "#F4F2FF",
        },
        // Theme tokens from app/globals.css, exposed as Tailwind utilities
        // (bg-accent, from-accent, border-accent, ...) so components use the
        // live brand colour instead of hard-coded palette classes.
        accent: {
          DEFAULT: "var(--accent)",
          2: "var(--accent-2)",
          soft: "var(--accent-soft)",
        },
      },
    },
  },
  plugins: [],
};
export default config;
