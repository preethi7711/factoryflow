/** @type {import('tailwindcss').Config} */
// Design tokens for direction C "Pouch & Process" (DESIGN.md). Every colour in the app comes from here.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        turmeric: { 50: "#FDF4DC", 100: "#FBE7B3", 300: "#F2C25A", 500: "#E8A317", 700: "#9A6608" },
        chilli: { 50: "#FBEAE6", 100: "#F6D2C9", 500: "#C8361D", 700: "#962613" },
        leaf: { 50: "#E8F1E9", 100: "#CFE3D2", 500: "#2F6B3A", 700: "#22502B" },
        choc: { 100: "#EFE4D6", 300: "#B9A391", 500: "#6B5242", 700: "#4A3427", 900: "#3B2416" },
        cream: "#FFF6E3",
        paper: "#FFFDF8",
        line: "#EADFCB",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"],
        sans: ['"Hind Madurai"', "system-ui", "sans-serif"],
      },
      keyframes: {
        pop: {
          "0%": { transform: "scale(1)" },
          "40%": { transform: "scale(1.18)" },
          "100%": { transform: "scale(1)" },
        },
        flow: { to: { strokeDashoffset: "-24" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
      },
      animation: {
        pop: "pop 220ms ease-out",
        flow: "flow 1.2s linear infinite",
        "fade-in": "fade-in 200ms ease-out",
        "spin-slow": "spin 24s linear infinite",
      },
    },
  },
  plugins: [],
};
