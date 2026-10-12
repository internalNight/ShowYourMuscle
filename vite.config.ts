import { defineConfig } from 'vite';

export default defineConfig({
  // Research files from previous mixed-model prototypes remain in public/ for
  // audit, but the app packages only the explicit unified-model allowlist.
  publicDir: false,
});
