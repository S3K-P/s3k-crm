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
        }
      },
    },
  },
  plugins: [],
};
export default config;
