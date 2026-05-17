import { resolve } from 'path'

export default {
  build: {
    rollupOptions: {
      input: resolve(__dirname, 'static/js/3dviewpage.js'),
      output: {
        entryFileNames: '3dviewpage.js', // no hash
      },
    },
    outDir: resolve(__dirname, 'static/dist'),
    emptyOutDir: true,
  },
}