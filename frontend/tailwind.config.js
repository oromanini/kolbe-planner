/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
  	extend: {
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			navy: '#0F1B2D',
  			'imperial-red': '#C0392B',
  			'victory-gold': '#F2E6C9',
  			paper: '#FAF9F7'
  		},
  		fontFamily: {
  			heading: ['Playfair Display', 'serif'],
  			body: ['Manrope', 'sans-serif']
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
}