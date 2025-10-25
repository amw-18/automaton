# OpenAPI TypeScript Client Auto-Generation

**Added to**: All Tasks  
**Tool**: `@hey-api/openapi-ts`

---

## Overview

Instead of manually writing API client code, we use **automatic TypeScript client generation** from FastAPI's OpenAPI specification. This ensures:

✅ **Type Safety** - TypeScript types match backend Pydantic models exactly  
✅ **Auto-Sync** - Frontend stays in sync with backend API changes  
✅ **No Manual Code** - API functions generated automatically  
✅ **Autocomplete** - Full IDE support for API calls  
✅ **Error Prevention** - Compile-time errors if API changes break frontend  

---

## How It Works

### 1. FastAPI Generates OpenAPI Schema

FastAPI automatically exposes the OpenAPI 3.1 specification at `/openapi.json`:

```bash
curl http://localhost:8000/openapi.json
```

This schema includes:
- All endpoint paths and methods
- Request/response types from Pydantic models
- Parameter definitions
- Error responses

### 2. hey-api/openapi-ts Generates TypeScript Client

The `@hey-api/openapi-ts` tool reads the OpenAPI schema and generates:

- **`types.gen.ts`** - TypeScript interfaces matching Pydantic models
- **`services.gen.ts`** - Typed functions for each API endpoint
- **`schemas.gen.ts`** - JSON schemas for validation

### 3. Frontend Uses Generated Client

```typescript
import { uploadVideo, getSession } from '@/lib/api-client';

// Fully typed function call
const result = await uploadVideo({
  body: { video: file },
});

// TypeScript knows the exact response type
console.log(result.data.sessionId); // ✓ Autocomplete works!
```

---

## Setup (Task 01)

### Install Dependencies

```bash
npm install --save-dev @hey-api/openapi-ts
npm install @hey-api/client-fetch
```

### Create Config File (`openapi-ts.config.ts`)

```typescript
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  client: '@hey-api/client-fetch',
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: 'lib/api-client',
  },
});
```

### Add Script to `package.json`

```json
{
  "scripts": {
    "generate-client": "openapi-ts"
  }
}
```

### Generate Client

```bash
npm run generate-client
```

---

## Usage Pattern

### After Adding Backend Endpoint

1. **Add FastAPI endpoint** with Pydantic models
2. **Run generation**: `npm run generate-client`
3. **Use in frontend**: Import from `@/lib/api-client`

### Example Backend Endpoint

```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class VideoUploadResponse(BaseModel):
    sessionId: str
    status: str
    message: str

@router.post("/api/videos/upload", response_model=VideoUploadResponse)
async def upload_video(video: UploadFile):
    # ... implementation
    return VideoUploadResponse(
        sessionId="abc-123",
        status="uploaded",
        message="Video uploaded successfully"
    )
```

### Generated TypeScript

```typescript
// types.gen.ts
export interface VideoUploadResponse {
  sessionId: string;
  status: string;
  message: string;
}

// services.gen.ts
export const uploadVideo = (options: {
  body: { video: File };
}) => {
  return client.POST('/api/videos/upload', options);
};
```

### Frontend Usage

```typescript
import { uploadVideo, VideoUploadResponse } from '@/lib/api-client';

const result = await uploadVideo({
  body: { video: file },
});

// result.data is typed as VideoUploadResponse
const sessionId: string = result.data.sessionId; // ✓ Type-safe
```

---

## Benefits

### 1. Type Safety

**Before** (manual API client):
```typescript
// No types, runtime errors possible
const result = await fetch('/api/videos/upload', {
  method: 'POST',
  body: formData,
});
const data = await result.json(); // any type
console.log(data.sesionId); // Typo! Runtime error
```

**After** (generated client):
```typescript
import { uploadVideo } from '@/lib/api-client';

const result = await uploadVideo({ body: { video: file } });
console.log(result.data.sessionId); // ✓ Autocomplete catches typos
```

### 2. Auto-Sync with Backend

When backend changes:
```python
# Backend: Add new field to response
class VideoUploadResponse(BaseModel):
    sessionId: str
    status: str
    videoSize: int  # NEW FIELD
```

Frontend automatically gets updated types:
```typescript
// After npm run generate-client
const result = await uploadVideo(...);
console.log(result.data.videoSize); // ✓ New field available
```

### 3. Compile-Time Error Detection

If backend removes a field:
```python
# Backend: Remove 'message' field
class VideoUploadResponse(BaseModel):
    sessionId: str
    status: str
    # message: str  ← REMOVED
```

Frontend TypeScript compilation fails:
```typescript
const result = await uploadVideo(...);
console.log(result.data.message); 
// ❌ TypeScript error: Property 'message' does not exist
```

---

## Workflow Integration

### Development Workflow

```bash
# Terminal 1 - Backend
cd backend
python main.py

# Terminal 2 - Frontend
cd frontend
npm run generate-client  # When backend changes
npm run dev
```

### Optional: Auto-Regenerate on Changes

Add a file watcher (optional, not required for MVP):

```bash
npm install --save-dev chokidar-cli
```

Update `package.json`:
```json
{
  "scripts": {
    "dev": "next dev",
    "dev:watch": "npm run dev & npm run watch:api",
    "watch:api": "chokidar 'http://localhost:8000/openapi.json' -c 'npm run generate-client'"
  }
}
```

---

## File Structure

```
frontend/
├── openapi-ts.config.ts          # Configuration
├── lib/
│   └── api-client/                # ← AUTO-GENERATED (gitignored)
│       ├── types.gen.ts           # TypeScript interfaces
│       ├── services.gen.ts        # API functions
│       ├── schemas.gen.ts         # JSON schemas
│       └── index.ts               # Exports
├── app/
│   └── page.tsx                   # Uses generated client
└── components/
    └── VideoUploader.tsx          # Uses generated client
```

---

## What Changed in Tasks

### Task 01 (Setup)
- ✅ Added `@hey-api/openapi-ts` installation
- ✅ Added `openapi-ts.config.ts`
- ✅ Added `generate-client` script
- ❌ Removed manual `lib/api.ts` file

### Task 02 (Video Upload)
- ✅ Use `uploadVideo()` from generated client
- ✅ Use `getSession()` from generated client
- ✅ Run `npm run generate-client` after adding endpoints
- ❌ No manual API client updates needed

### Task 03-06 (Subsequent Tasks)
- ✅ Always regenerate client after backend changes
- ✅ Use generated types in components
- ✅ No manual API code

---

## Troubleshooting

### Client Not Generating

**Problem**: `npm run generate-client` fails

**Solutions**:
1. Ensure backend is running: `http://localhost:8000`
2. Check OpenAPI schema loads: `http://localhost:8000/openapi.json`
3. Verify `openapi-ts.config.ts` has correct URL
4. Check for TypeScript errors in backend models

### Types Not Matching

**Problem**: Generated types don't match expectations

**Solutions**:
1. Check Pydantic models in backend
2. Ensure `response_model` is set on endpoints
3. Regenerate client: `npm run generate-client`
4. Clear Next.js cache: `rm -rf .next`

### Import Errors

**Problem**: Cannot import from `@/lib/api-client`

**Solutions**:
1. Verify client was generated: `ls lib/api-client/`
2. Check `tsconfig.json` has path alias
3. Restart TypeScript server in IDE
4. Ensure `lib/api-client/index.ts` exists

---

## References

- [FastAPI Generate Clients Documentation](https://fastapi.tiangolo.com/advanced/generate-clients/)
- [hey-api/openapi-ts GitHub](https://github.com/hey-api/openapi-ts)
- [hey-api Documentation](https://heyapi.dev/)
- [OpenAPI Specification](https://swagger.io/specification/)

---

## Summary

**Key Points:**

1. **No manual API client code** - Everything auto-generated
2. **Run `npm run generate-client`** after backend changes
3. **Full type safety** from backend to frontend
4. **Automatic IDE autocomplete** for API calls
5. **Catch breaking changes at compile time**

This approach ensures the frontend and backend stay in perfect sync with minimal manual effort! 🚀
