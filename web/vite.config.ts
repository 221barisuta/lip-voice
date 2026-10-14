import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// .env.dev / .env.prod はリポジトリ直下に置く。VITE_ 接頭辞の値だけがブラウザに渡る。
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: { port: 5173 },
});
