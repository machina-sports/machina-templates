# Machina Frontend Coding Standards

To maintain consistency and code quality across all Machina Sports projects, developers must adhere to the following standards.

## 1. Type Safety
- **Strict TypeScript**: `noImplicitAny` is enabled. Use interfaces or types for all objects.
- **No `any`**: The use of `any` is strictly prohibited. If a type is unknown, use `unknown` and perform type narrowing.
- **API Responses**: Always define interfaces for API responses in the corresponding `service.ts` or a shared `types.ts` file.
- **Component Props**: Define props using interfaces for every component.

## 2. Component Development
- **Presentational Focus**: Keep components focused on UI. Move logic to Redux actions or custom hooks within Providers.
- **"use client" Directive**: Use only when necessary for interactivity (hooks, event listeners). Prefer Server Components for static content, although the boilerplate is optimized for Client-side state management via Redux.
- **Tailwind CSS**: Use utility classes for styling. Avoid inline styles or CSS-in-JS unless absolutely necessary for dynamic values that cannot be handled by Tailwind.
- **Styling Overrides**: Use the `className` prop to allow components to be styled from the outside.

## 3. Naming Conventions
- **Folders**: Kebab-case (e.g., `user-profile`).
- **Components**: PascalCase (e.g., `UserProfile.tsx`).
- **Files (non-component)**: camelCase or kebab-case (e.g., `actions.ts`, `base-controller.ts`).
- **Interfaces/Types**: PascalCase (e.g., `UserResponse`).

## 4. State Management Patterns
- **Selectors**: Use memoized selectors where possible to prevent unnecessary re-renders.
- **Thunks**: All asynchronous logic (API calls) must be handled via Redux Thunks in `actions.ts`.
- **Hooks**: Use `useAppSelector` and `useAppDispatch` instead of standard `useSelector` and `useDispatch` to maintain type safety.

## 5. Localization & Assets
- **Language**: All code comments, variable names, and user-facing text must be in **English**.
- **Images/Icons**: Place global assets in `public/assets/`. Brand-specific assets should be managed via the `config/brands/` configuration.

## 6. Code Validation Checklist for AI Assistant
When validating user code, ensure:
1. [ ] No `any` types are used.
2. [ ] Components don't call `fetch` or `axios` directly (must use Services).
3. [ ] `useAppSelector` and `useAppDispatch` are used for Redux.
4. [ ] Proper folder structure is followed (actions, reducer, service, provider).
5. [ ] Brand-specific logic uses the `useBrand()` hook instead of hardcoding values.
6. [ ] "use client" is present if the component uses hooks.

