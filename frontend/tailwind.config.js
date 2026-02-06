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
  			primary: {
  				DEFAULT: '#CD1C33',
  				light: '#E63946',
  				dark: '#9B1422',
  				foreground: '#FFFFFF'
  			},
  			secondary: {
  				DEFAULT: '#D4AF37',
  				light: '#F3E5AB',
  				dark: '#8F7524',
  				foreground: '#000000'
  			},
  			background: {
  				DEFAULT: '#0B1120',
  				paper: '#151E32',
  				subtle: '#1E293B'
  			}
  		},
  		fontFamily: {
  			heading: ['Syne', 'sans-serif'],
  			body: ['Manrope', 'sans-serif'],
  			accent: ['Playfair Display', 'serif']
  		},
  		backgroundImage: {
  			'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
  			'gradient-hero': 'linear-gradient(135deg, #0B1120 0%, #151E32 100%)',
  			'gradient-gold': 'linear-gradient(45deg, #D4AF37 0%, #F3E5AB 50%, #8F7524 100%)'
  		},
  		boxShadow: {
  			'glow': '0 0 20px rgba(212, 175, 55, 0.15)',
  			'glow-strong': '0 0 30px rgba(212, 175, 55, 0.3)'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
}