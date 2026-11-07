/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  corePlugins: { preflight: false },   // design/sonariq.css owns base styles
  theme: { extend: {} },
  plugins: [],
};
