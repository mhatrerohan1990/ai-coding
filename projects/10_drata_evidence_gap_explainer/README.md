# fastify-ts-app

TypeScript project with Fastify and the `src/gap` evidence-gap modules.

## Requirements

- Node.js 22+
- npm

## Setup

```sh
npm install
```

## Run

Dev server (watch mode, port 3000):

```sh
npm run dev
```

Check it:

```sh
curl http://localhost:3000/health
```

Build and run the compiled output:

```sh
npm run build
npm start
```

## Test

```sh
npx vitest run
```

## Typecheck

```sh
npx tsc --noEmit
```
