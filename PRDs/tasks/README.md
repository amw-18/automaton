# Automaton Web Interface - Task Breakdown

This directory contains incremental tasks for building the web interface with real-time agent streaming.

---

## 🔥 Key Feature: Auto-Generated TypeScript Client

**All tasks now use `@hey-api/openapi-ts` for automatic client generation!**

Instead of manually writing API client code, the TypeScript client is **automatically generated** from FastAPI's OpenAPI specification. This ensures:
- ✅ Perfect type safety (frontend types match backend Pydantic models)
- ✅ No manual API client updates needed
- ✅ Compile-time error detection when API changes
- ✅ Full IDE autocomplete support

See [`00-openapi-client-generation.md`](./00-openapi-client-generation.md) for details.

---

## Task Overview

### ✅ Task 01: Project Setup & Basic Infrastructure
**Time**: 2-3 hours  
**Goal**: Set up FastAPI backend and Next.js frontend with **auto-generated TypeScript client**

**Deliverables:**
- FastAPI app with health endpoint  
- OpenAPI schema at `/openapi.json`
- `@hey-api/openapi-ts` configured
- Auto-generated TypeScript client
- Next.js app using generated client
- CORS configuration
- Basic landing page with API status check

**Test**: Run `npm run generate-client` → client generated → Frontend shows "API Status: connected ✅"

---

### ✅ Task 02: Video Upload Flow
**Time**: 3-4 hours  
**Dependencies**: Task 01  
**Goal**: Implement video upload with file storage and session creation

**Deliverables:**
- Video upload endpoint (POST /api/videos/upload)
- Session management (in-memory with UUID)
- **Regenerate client** with `uploadVideo()` and `getSession()` functions
- File validation (type & size)
- Drag & drop upload UI using generated client
- Session page display with typed responses

**Test**: `npm run generate-client` → Upload video → Redirect to `/session/{uuid}` → Session details displayed

---

### ✅ Task 03: WebSocket Infrastructure
**Time**: 2-3 hours  
**Dependencies**: Task 02  
**Goal**: Set up WebSocket connections for real-time communication

**Deliverables:**
- WebSocket endpoint (WS /ws/{sessionId})
- StreamManager for connection management
- Frontend WebSocket hook
- Connection status indicator
- Message logging on frontend

**Test**: WebSocket connects → Green indicator → Ping/pong works

---

### ✅ Task 04: Video Processing Integration
**Time**: 2-3 hours  
**Dependencies**: Task 03  
**Goal**: Integrate existing VideoProcessor to convert videos to WorkflowInput

**Deliverables:**
- VideoService wrapper
- Process endpoint (POST /api/sessions/{id}/process)
- Background task execution
- Status updates via WebSocket
- Workflow JSON generation

**Test**: Click "Process Video" → Status updates stream → workflow.json created

---

### ✅ Task 05: Agent Execution with Screenshot Streaming
**Time**: 4-5 hours  
**Dependencies**: Task 04  
**Goal**: Execute agent pipeline with real-time screenshot streaming

**Deliverables:**
- Modified PlaywrightToolkit (custom screenshot dir + callback)
- AgentExecutionService
- Start agent endpoint (POST /api/sessions/{id}/start)
- Screenshot serving endpoint (GET /api/screenshots/{id}/{filename})
- ScreenshotStream component
- Live screenshot display with timeline

**Test**: Click "Start Agent" → Screenshots stream in real-time → Script generated

---

### ✅ Task 06: Session Cleanup & Polish
**Time**: 2-3 hours  
**Dependencies**: Task 05  
**Goal**: Add automated cleanup and polish the UI

**Deliverables:**
- CleanupService (auto-delete old sessions)
- Background cleanup task (every 30 mins)
- Manual cleanup endpoint
- Stats endpoint (session counts, disk usage)
- LoadingSpinner component
- ErrorBoundary component
- StatusBadge component
- Enhanced error handling
- UI polish and navigation

**Test**: Sessions auto-delete after 1 hour → UI is polished → Error handling works

---

## Total Estimated Time: 18-23 hours

## Implementation Order

```
Task 01 (Setup)
  ↓
Task 02 (Upload)
  ↓
Task 03 (WebSocket)
  ↓
Task 04 (Processing)
  ↓
Task 05 (Agent + Streaming) ← Most Complex
  ↓
Task 06 (Cleanup + Polish)
```

---

## Quick Start Guide

### For Each Task:

1. **Read the task file** (`01-project-setup.md`, etc.)
2. **Create backend files** in the order listed
3. **Regenerate TypeScript client**: `npm run generate-client` (after backend changes)
4. **Create frontend files** using the generated client
5. **Test incrementally** - don't move to next task until current works
6. **Verify success criteria** before proceeding

### Testing Each Task:

```bash
# Terminal 1 - Backend
cd backend
source venv/bin/activate
python main.py

# Terminal 2 - Frontend
cd frontend
npm run generate-client  # ← IMPORTANT: Run after backend changes!
npm run dev

# Browser
http://localhost:3000
```

### 🔁 Client Regeneration Workflow

**After adding/modifying ANY backend endpoint:**

```bash
cd frontend
npm run generate-client
```

This updates:
- `lib/api-client/types.gen.ts` - TypeScript types
- `lib/api-client/services.gen.ts` - API functions
- Your IDE autocomplete automatically updates!

---

## File Structure After All Tasks

```
automaton/
├── backend/                    # FastAPI backend
│   ├── main.py
│   ├── requirements.txt
│   ├── .env
│   ├── models/
│   │   └── session.py
│   ├── routers/
│   │   ├── videos.py
│   │   ├── sessions.py
│   │   ├── websocket.py
│   │   └── static.py
│   └── services/
│       ├── video_service.py
│       ├── agent_service.py
│       ├── stream_service.py
│       └── cleanup_service.py
│
├── frontend/                   # Next.js frontend
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── session/
│   │       └── [sessionId]/
│   │           └── page.tsx
│   ├── components/
│   │   ├── VideoUploader.tsx
│   │   ├── ScreenshotStream.tsx
│   │   ├── LoadingSpinner.tsx
│   │   ├── ErrorBoundary.tsx
│   │   └── StatusBadge.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   └── useWebSocket.ts
│   ├── .env.local
│   └── package.json
│
├── src/                        # Existing Python agent (modified)
│   ├── playwright_framework.py # + screenshot dir & callback
│   └── ... (rest unchanged)
│
└── uploads/                    # Session data
    └── {session-id}/
        ├── video.mp4
        ├── workflow.json
        ├── screenshots/
        │   └── labeled_*.png
        └── output/
            └── test_generated.py
```

---

## Key Technologies

**Backend:**
- FastAPI (async Python web framework)
- WebSockets (real-time communication)
- Existing agent code (VideoProcessor, Agent, PlaywrightToolkit)

**Frontend:**
- Next.js 14 (React framework with App Router)
- TypeScript (type safety)
- Tailwind CSS (styling)
- WebSocket API (real-time updates)

---

## Success Criteria (Overall)

When all tasks are complete:

✅ User can upload workflow video  
✅ Video is processed to extract actions  
✅ Agent executes workflow in Playwright  
✅ Screenshots stream to frontend in real-time  
✅ Test script is generated and downloadable  
✅ Sessions auto-cleanup after 1 hour  
✅ Error handling is robust  
✅ UI is polished and professional  

---

## Troubleshooting

### Backend won't start
- Check Python virtual environment is activated
- Verify `vertex-ai-credentials.json` exists
- Check port 8000 is not in use

### Frontend won't start
- Run `npm install` in frontend directory
- Check `.env.local` has correct API URL
- Check port 3000 is not in use

### WebSocket won't connect
- Verify backend is running
- Check CORS settings allow localhost:3000
- Check WebSocket URL in `.env.local`

### Agent execution fails
- Check Google Cloud credentials
- Verify video was processed successfully
- Check agent logs in `logs/` directory

---

## Support

For issues during implementation:
1. Check task file for specific instructions
2. Verify all dependencies are installed
3. Check browser console for frontend errors
4. Check terminal output for backend errors
5. Review success criteria for current task

---

## Next Steps After Completion

**Optional Enhancements (Phase 3):**
- User authentication
- Session persistence (database)
- Session history
- Video editing
- Multi-browser support
- Headless toggle
- Script editing in browser
- Test execution from UI
- Collaboration features
- Analytics dashboard

---

**Total Project Status**: Ready for implementation! 🚀

Start with **Task 01** and work through sequentially.
