/** Charte Lagom Natura : Rubik, ardoise #44405A, vert #80C595, jaune #FBCF38 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Rubik', 'Arial', 'Helvetica', 'sans-serif'] },
      colors: {
        slate: { DEFAULT: '#44405a', light: '#7a7790' },
        green: { DEFAULT: '#80c595', dark: '#5aa876', soft: '#eaf5ee' },
        yellow: { DEFAULT: '#fbcf38' },
        line: '#e6e8e6',
        page: '#f7f8f7',
      },
      borderRadius: { DEFAULT: '6px', sm: '2px' },
    },
  },
  plugins: [],
}
