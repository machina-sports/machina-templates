# Machina Frontend Boilerplate Architecture

This document describes the architectural standards and directory structure of the Machina Frontend Boilerplate, which serves as the foundation for all Machina Sports frontends.

## Core Technologies
- **Next.js 16 (App Router)**: Framework for routing and layouts.
- **Redux Toolkit**: Centralized state management.
- **Tailwind CSS 4**: Utility-first styling.
- **Strict TypeScript**: Ensures type safety across the application.
- **White Label Support**: Built-in multi-brand and configurable theming.

## Directory Structure Overview
```text
├── app/                  # Next.js App Router (Routes & Layouts)
│   ├── api/              # Route Handlers (BFF pattern - Backend for Frontend)
│   ├── layout.tsx        # Root layout with Providers
│   └── page.tsx          # Home page (example/development)
├── components/           # React Components
│   ├── ui/               # Reusable UI primitives (Shadcn-like)
│   └── <feature>/        # Feature-specific components
├── config/               # Configuration
│   ├── brands/           # Brand tokens (colors, text, assets)
│   └── runtime.ts        # Runtime environment variables
├── providers/            # Domain Logic (Redux + Context)
│   └── <domain>/         # Domain folder (e.g., auth, data, session)
│       ├── actions.ts    # Redux Thunks
│       ├── reducer.ts    # Redux Slice
│       ├── service.ts    # API Service (HTTP calls)
│       └── provider.tsx  # React Context Provider / Hooks
├── libs/                 # Library Code
│   └── client/           # HTTP Client Base (Axios wrapper)
├── store/                # Redux Store Configuration
└── public/               # Static Assets
```

## Architectural Layers

### 1. HTTP Layer (`libs/client/`)
All external communication must use the `libs/client/base.controller.ts` (Axios wrapper).
- **Rule**: Domain services must extend `ClientBaseService`.
- **Rule**: Never use `fetch` or raw `axios` directly in components.

### 2. Providers Layer (`providers/`)
The "Brain" of the application. Each domain logic bundle resides here.
- **actions.ts**: Contains asynchronous logic (Thunks).
- **reducer.ts**: Defines the state structure and synchronous updates (Slice).
- **service.ts**: Handles API requests by extending `ClientBaseService`.
- **provider.tsx**: Provides the Redux state and actions via React Context or custom hooks to the components.

### 3. State Management (`store/`)
Redux slices from providers must be registered in `store/index.ts`.
- Components consume state via the `useAppSelector` hook.
- Components dispatch actions via the `useAppDispatch` hook.

### 4. Component Layer (`components/`)
Components should be primarily **presentational**.
- UI primitives (buttons, inputs, etc.) go in `components/ui/`.
- Feature-specific UI goes in `components/<feature>/`.
- **Rule**: Business logic should be kept in Providers, while components focus on rendering and user interaction.

### 5. Configuration & Branding (`config/`)
Supports white-labeling by defining brand-specific tokens.
- `config/brands/` defines colors, typography, and assets per brand.
- `NEXT_PUBLIC_BRAND` environment variable determines the active brand at runtime.

