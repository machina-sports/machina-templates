# Guide: Adding a New Feature

This guide outlines the step-by-step process for implementing a new feature in a Machina Frontend project.

## Step 1: Create the Provider
Create a new directory in `providers/<feature-name>/`.
Every domain folder **MUST** contain:
- `actions.ts`: Define asynchronous Thunks for API calls.
- `reducer.ts`: Define the Redux slice and initial state.
- `service.ts`: Implement the API service by extending `ClientBaseService`.
- `provider.tsx`: Create a React Provider and custom hooks if necessary to expose the domain state.

## Step 2: Define Types
Start by defining the interfaces for your data and API responses.
```typescript
// service.ts or types.ts
export interface FeatureData {
  id: string;
  name: string;
}
```

## Step 3: Implement the Service
Extend `ClientBaseService` to handle HTTP requests.
```typescript
// service.ts
import { ClientBaseService } from '@/libs/client/base.controller';

class FeatureService extends ClientBaseService {
  async getFeatureData(id: string) {
    return this.post<FeatureData>('/api/feature', { id });
  }
}
export const featureService = new FeatureService();
```

## Step 4: Create the Redux Slice
Define your state and reducers.
```typescript
// reducer.ts
import { createSlice } from '@reduxjs/toolkit';

const featureSlice = createSlice({
  name: 'feature',
  initialState: { data: null, loading: false },
  reducers: {
    setData: (state, action) => { state.data = action.payload; }
  }
});
export default featureSlice.reducer;
```

## Step 5: Register the Reducer
Add the new reducer to the root store in `store/index.ts`.
```typescript
// store/index.ts
import featureReducer from '@/providers/feature/reducer';

export const store = configureStore({
  reducer: {
    // ... other reducers
    feature: featureReducer,
  },
});
```

## Step 6: Build the UI Components
Create components in `components/<feature-name>/`.
Use `useAppSelector` to read state and `useAppDispatch` to trigger actions.

```typescript
"use client";
import { useAppSelector, useAppDispatch } from '@/store';
// ...
```

## Step 7: Wrap with Provider (if global)
If the feature needs to be available globally, add its provider to the root `providers/provider.tsx`.

