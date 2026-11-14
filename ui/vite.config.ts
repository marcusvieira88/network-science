import path from "node:path";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// The built app may load nothing from another origin. Dev mode needs inline scripts for hot
// reload, so the policy is added to the production build only (checked by check-build.mjs).
export const CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
  "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'";

function contentSecurityPolicy(): Plugin {
  return {
    name: "content-security-policy",
    apply: "build",
    transformIndexHtml: () => [
      { tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: CONTENT_SECURITY_POLICY }, injectTo: "head" },
    ],
  };
}

export default defineConfig({
  // Relative asset paths: the build is a static folder that opens from any location.
  base: "./",
  plugins: [react(), contentSecurityPolicy()],
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve(import.meta.dirname, "src") },
      // Never used: see src/vendor/three-webgpu-stub.ts.
      { find: /^three\/webgpu$/, replacement: path.resolve(import.meta.dirname, "src/vendor/three-webgpu-stub.ts") },
    ],
  },
  // One static bundle served locally, except the 3D network (three.js), loaded only when opened.
  build: { chunkSizeWarningLimit: 1024 },
  server: { host: "127.0.0.1" },
  preview: { host: "127.0.0.1" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
