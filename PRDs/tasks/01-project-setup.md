# Task 01: Project Setup & Basic Infrastructure

**Goal**: Set up FastAPI backend and Next.js frontend with basic "Hello World" communication

**Status**: Not Started  
**Estimated Time**: 2-3 hours

---

## Backend Setup

### 1. Create Backend Directory Structure
```bash
backend/
├── main.py
├── requirements.txt
└── .env
```

### 2. Install Dependencies (`requirements.txt`)
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
python-dotenv==1.0.0
```

### 3. Basic FastAPI App (`backend/main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Automaton API", version="1.0.0")

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Automaton API", "status": "running"}

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 4. Environment File (`.env`)
```bash
GOOGLE_APPLICATION_CREDENTIALS=../vertex-ai-credentials.json
GCP_PROJECT_ID=deft-axon-474218-j8
GCP_LOCATION=us-central1
```

---

## Frontend Setup

### 1. Create Next.js App
```bash
cd frontend
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir
```

Options:
- ✅ TypeScript
- ✅ ESLint
- ✅ Tailwind CSS
- ✅ App Router
- ❌ src/ directory (use app/ directly)
- ❌ import alias

### 2. Install OpenAPI TypeScript Generator
```bash
npm install --save-dev @hey-api/openapi-ts
npm install @hey-api/client-fetch
```

### 3. Create OpenAPI Config (`openapi-ts.config.ts`)
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

### 4. Add Generation Script to `package.json`
```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "generate-client": "openapi-ts"
  }
}
```

### 5. Generate Initial Client
```bash
# Make sure backend is running on localhost:8000
npm run generate-client
```

This creates `lib/api-client/` with:
- `types.gen.ts` - TypeScript types from Pydantic models
- `services.gen.ts` - Typed API functions
- `schemas.gen.ts` - JSON schemas

### 6. Update Landing Page (`app/page.tsx`)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { client } from '@/lib/api-client';

export default function Home() {
  const [apiStatus, setApiStatus] = useState<string>('checking...');

  useEffect(() => {
    // Configure the client base URL
    client.setConfig({
      baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    });

    // Test the connection
    fetch(`${client.getConfig().baseUrl}/api/health`)
      .then(res => res.json())
      .then(() => setApiStatus('connected ✅'))
      .catch(() => setApiStatus('disconnected ❌'));
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">Automaton</h1>
        <p className="text-xl text-gray-600 mb-8">
          AI-Powered Test Automation
        </p>
        <div className="text-sm text-gray-500">
          API Status: {apiStatus}
        </div>
      </div>
    </main>
  );
}
```

### 7. Environment File (`frontend/.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 8. Add Generated Files to `.gitignore`
```
# API Client (auto-generated)
lib/api-client/
```

---

## Testing

### Start Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Backend should be running at: http://localhost:8000

### Start Frontend
```bash
cd frontend
npm install
npm run generate-client  # Generate TypeScript client from OpenAPI
npm run dev
```

Frontend should be running at: http://localhost:3000

### Verification
1. Backend running: http://localhost:8000
2. Visit http://localhost:8000/docs - FastAPI Swagger docs should load
3. Visit http://localhost:8000/openapi.json - OpenAPI schema should display
4. Check `frontend/lib/api-client/` - generated files should exist
5. Visit http://localhost:3000 - You should see "API Status: connected ✅"

---

## Success Criteria

- ✅ Backend runs on port 8000
- ✅ OpenAPI schema accessible at /openapi.json
- ✅ TypeScript client auto-generated in `lib/api-client/`
- ✅ Generated types match backend Pydantic models
- ✅ Frontend runs on port 3000
- ✅ CORS is configured correctly
- ✅ "connected ✅" appears on homepage

---

## Files Created
- `backend/main.py`
- `backend/requirements.txt`
- `backend/.env`
- `frontend/openapi-ts.config.ts` ← NEW
- `frontend/lib/api-client/` ← AUTO-GENERATED
- `frontend/app/page.tsx`
- `frontend/.env.local`
- `frontend/.gitignore` (updated)

---

## Next Task
**Task 02**: Video Upload Flow (backend endpoint + frontend UI)
