import { defineConfig } from "vite";

// The FastAPI app serves web/dist in the container; `npm run dev` is for local UI work only.
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
