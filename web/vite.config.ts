import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 画面は Python のローカルプログラム（app/）が配信する。ビルド先はその static/。
// 開発時は  lipvoice run --dev  を起動しておき、npm run dev の画面から /api をそこへ中継する。
//   トークンは LIPVOICE_TOKEN=dev で起動し、VITE_LIPVOICE_TOKEN=dev で画面側に渡す。
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../app/lipvoice/static", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: true } },
  },
});
