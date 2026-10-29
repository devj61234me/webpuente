/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#effaf8", 100: "#d3f2ec", 200: "#a9e4da", 300: "#74cfc2", 400: "#45b5a8", 500: "#2a998d", 600: "#1f7b73", 700: "#1d625d", 800: "#1c4f4c", 900: "#1b4240" },
        ink: { 900: "#14202b", 700: "#33424f", 500: "#5b6b79", 400: "#8795a1", 300: "#b7c1c9", 200: "#dbe1e6", 100: "#edf0f3", 50: "#f6f8f9" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
};
