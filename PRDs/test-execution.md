# Test Execution Feature

## Overview

The test execution feature allows users to run and verify generated Playwright test scripts in a sandboxed Docker environment. The execution is recorded as a video, providing visual feedback on test behavior.

## Architecture

```
┌──────────────┐
│   Frontend   │
│  (Test Button)│
└──────┬───────┘
       │ POST /api/sessions/{id}/test
       ▼
┌──────────────────────┐
│  Backend API         │
│  - sessions.py       │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Test Execution Service       │
│ - Prepare Docker environment │
│ - Modify script for recording│
│ - Run in container           │
│ - Extract video              │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Docker Container    │
│  - Playwright installed│
│  - Chromium browser  │
│  - Video recording   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Test Execution Video│
│  (WebM format)       │
└──────────────────────┘
```

## Components

### 1. Docker Image

**File**: `backend/docker/Dockerfile.playwright-runner`

- Based on official Playwright Python image
- Pre-installed with Chromium and dependencies
- Minimal footprint for fast execution
- Supports video recording out of the box

**Build Command**:
```bash
cd backend/docker
./build-image.sh
```

### 2. Test Execution Service

**File**: `backend/services/test_execution_service.py`

**Responsibilities**:
- Ensure Docker image is built and ready
- Modify generated test scripts to enable video recording
- Execute tests in isolated Docker containers
- Extract and save video recordings
- Update session status via WebSocket

**Key Methods**:
- `ensure_docker_image()` - Build Docker image if not present
- `run_test(session_id)` - Main entry point for test execution
- `_prepare_test_script_with_video()` - Inject video recording config
- `_run_in_docker()` - Execute script in Docker container

### 3. API Endpoints

#### POST /api/sessions/{session_id}/test

**Purpose**: Trigger test execution for a generated script

**Requirements**:
- Session must exist
- Status must be `complete` (script generated)
- Docker must be available on the system

**Response**:
```json
{
  "sessionId": "uuid",
  "status": "testing",
  "message": "Test execution started"
}
```

#### GET /api/test-videos/{session_id}/execution.webm

**Purpose**: Serve the test execution video

**Response**: WebM video file

### 4. Session Model Updates

**New Fields**:
- `test_video_path` - Path to test execution video

**New Statuses**:
- `testing` - Test execution in progress
- `test_complete` - Test completed successfully
- `test_failed` - Test execution failed

### 5. Frontend UI

**Location**: `frontend/app/session/[sessionId]/page.tsx`

**Features**:
- "Test Script" button (shown after script generation)
- Real-time status updates via WebSocket
- Video player for test execution recording
- Error handling and user feedback

## Workflow

### User Flow

1. **Upload Video** → Process → Generate Script (existing flow)
2. **Click "Test Script" button** (new)
3. System prepares Docker environment
4. Script is modified to enable video recording
5. Docker container runs the test
6. Video recording is extracted and saved
7. User sees video playback in UI

### Technical Flow

```
1. User clicks "Test Script" button
   ↓
2. POST /api/sessions/{id}/test
   ↓
3. Background task: test_execution_service.run_test()
   ↓
4. Check/build Docker image
   ↓
5. Modify script to add video recording
   ↓
6. Run: docker run -v [script]:/test/test_script.py playwright-runner
   ↓
7. Playwright records video during execution
   ↓
8. Extract video from container to uploads/{id}/test_output/
   ↓
9. Update session status to test_complete
   ↓
10. Frontend displays video player
```

## Configuration

### Video Recording Settings

Located in `test_execution_service.py`:

```python
record_video_dir="/test/videos"
record_video_size={"width": 1280, "height": 720}
```

### Docker Settings

- **Network**: `--network host` (allows test to access web)
- **Volume Mounts**: 
  - Script (read-only): `-v {script}:/test/test_script.py:ro`
  - Output (read-write): `-v {output_dir}:/test/videos:rw`

## Prerequisites

### System Requirements

1. **Docker Engine** must be installed and running
2. **Docker permissions** - Backend must have access to Docker socket
3. **Disk space** - ~500MB for Docker image, ~10-50MB per test video

### Backend Setup

```bash
# 1. Build Docker image
cd backend/docker
./build-image.sh

# 2. Verify image exists
docker images | grep playwright-runner

# 3. Test image (optional)
docker run --rm playwright-runner python --version
```

## Troubleshooting

### Docker Image Not Building

**Problem**: Build fails with permission errors

**Solution**:
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER
newgrp docker

# Or run backend with sufficient permissions
```

### No Video Recorded

**Problem**: Test completes but no video file

**Possible Causes**:
1. Script didn't call `browser.new_context()` - video recording requires context
2. Volume mount failed - check Docker permissions
3. Script crashed before video was saved

**Debug**:
```bash
# Check Docker logs
docker ps -a | grep playwright-runner

# Check session events
GET /api/sessions/{id}/events
```

### Test Execution Timeout

**Problem**: Docker container runs indefinitely

**Solution**: Add timeout to Docker run command (future enhancement)

## Security Considerations

1. **Container Isolation**: Each test runs in isolated container
2. **Network Access**: Container has `--network host` for web access
3. **Resource Limits**: No current limits (add `--memory`, `--cpus` for production)
4. **Script Validation**: Scripts are user-generated - run in sandboxed environment

## Future Enhancements

### Planned Features

- [ ] **Configurable Timeouts**: Set max test execution time
- [ ] **Resource Limits**: CPU/memory constraints for Docker
- [ ] **Multiple Browser Support**: Firefox, Safari (WebKit)
- [ ] **Screenshot Comparison**: Compare test vs original workflow
- [ ] **Test Artifacts**: Save console logs, network traces
- [ ] **Parallel Execution**: Run multiple tests simultaneously
- [ ] **Custom Docker Images**: User-provided base images
- [ ] **Test Scheduling**: Scheduled/recurring test runs

### Performance Optimizations

- [ ] Keep Docker container warm (reduce cold start time)
- [ ] Pre-pull base image on backend startup
- [ ] Compress videos for faster delivery
- [ ] Stream video during execution (not just after)

## API Reference

### WebSocket Messages

#### Testing Status
```json
{
  "type": "status",
  "sessionId": "uuid",
  "status": "testing",
  "timestamp": "2025-10-26T10:00:00Z",
  "log": {
    "message": "Running test in Docker container..."
  }
}
```

#### Test Complete
```json
{
  "type": "status",
  "sessionId": "uuid",
  "status": "test_complete",
  "timestamp": "2025-10-26T10:02:00Z",
  "log": {
    "message": "Test execution completed successfully",
    "video_path": "test_output/test_execution.webm"
  }
}
```

#### Test Failed
```json
{
  "type": "status",
  "sessionId": "uuid",
  "status": "test_failed",
  "timestamp": "2025-10-26T10:01:00Z",
  "log": {
    "error": "Test execution failed with exit code 1"
  }
}
```

## Development

### Running Tests Manually

```bash
# 1. Generate a test script first (via UI or API)

# 2. Run test execution
curl -X POST http://localhost:8000/api/sessions/{session_id}/test

# 3. Watch WebSocket for status updates
# (Connect to ws://localhost:8000/ws/{session_id})

# 4. View video when complete
open http://localhost:8000/api/test-videos/{session_id}/execution.webm
```

### Debugging

Enable debug logging in `test_execution_service.py`:

```python
# Check Docker output
print(f"📄 Docker stdout:\n{stdout.decode()}")
print(f"📄 Docker stderr:\n{stderr.decode()}")
```

## Dependencies

### Backend

- **Docker SDK** (optional, using subprocess instead)
- Existing FastAPI dependencies

### Docker Image

- `mcr.microsoft.com/playwright/python:v1.48.0-jammy`
- `playwright-python-async`
- Chromium browser (pre-installed)

## Limitations

1. **Docker Required**: Cannot run without Docker engine
2. **Single Browser**: Currently supports Chromium only
3. **No Streaming**: Video only available after test completes
4. **Fixed Resolution**: 1280x720 (configurable in code)
5. **Network Access**: Tests can access internet (security consideration)

## Related Documentation

- [PRD: Web Interface Streaming](./web-interface-streaming.md)
- [Backend README](../backend/README.md)
- [Playwright Video Recording Docs](https://playwright.dev/python/docs/videos)
