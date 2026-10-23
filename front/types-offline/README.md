Minimal React type declarations used ONLY when the real `@types/react` cannot be installed
(the build workspace had no npm registry access). `npm run typecheck` uses the real types;
`npm run typecheck:offline` uses these. They cover the React APIs this app uses.
