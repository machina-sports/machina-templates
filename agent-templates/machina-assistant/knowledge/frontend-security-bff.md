# Frontend Security & BFF Pattern

Security is a primary concern in Machina Sports projects. We use specific patterns to ensure sensitive data and API keys are protected.

## 1. BFF Pattern (Backend for Frontend)
All external API calls **MUST** go through Next.js Route Handlers (`app/api/*`).
- **Purpose**: The API route acts as a proxy, allowing us to keep sensitive API keys on the server and handle authentication securely before forwarding requests to the actual backend.
- **Rule**: Never call external APIs (like Google Gemini, Machina API) directly from the client-side code.

### Example API Route (`app/api/feature/route.ts`)
```typescript
import { NextResponse, NextRequest } from 'next/server';

export async function POST(req: NextRequest) {
  const body = await req.json();
  const apiKey = process.env.MACHINA_API_KEY; // Server-side only
  
  const response = await fetch(`${process.env.API_URL}/data`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  
  const data = await response.json();
  return NextResponse.json(data);
}
```

## 2. Environment Variables
- **Public Variables**: Prefix with `NEXT_PUBLIC_` only if they need to be accessible in the browser (e.g., `NEXT_PUBLIC_BRAND`).
- **Sensitive Variables**: Never prefix sensitive keys (e.g., `MACHINA_API_KEY`, `GEMINI_API_KEY`) with `NEXT_PUBLIC_`. These should only be used in API routes or Server Components.
- **Environment Files**: `.env`, `.env.local`, etc., are ignored by git to prevent accidental exposure of secrets.

## 3. Security Checklist
When developing or reviewing code, ensure the following:
- [ ] No sensitive API keys are prefixed with `NEXT_PUBLIC_`.
- [ ] No direct calls to external domains from components (all must go via `/api/*`).
- [ ] Authentication headers are handled server-side within the API routes.
- [ ] Input validation is performed both in the client (for UX) and in the API route (for security).

## 4. White Labeling Security
Brand-specific tokens and configurations are loaded via the `NEXT_PUBLIC_BRAND` variable. Ensure that brand-specific assets or configurations do not inadvertently expose internal data or cross-brand information.

