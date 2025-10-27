'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getSessionApiSessionsSessionIdGet, processVideoApiSessionsSessionIdProcessPost, getWorkflowApiSessionsSessionIdWorkflowGet } from '@/lib/api-client';
import { useWebSocket, WebSocketMessage } from '@/lib/useWebSocket';
import ScreenshotStream from '@/components/ScreenshotStream';
import LoadingSpinner from '@/components/LoadingSpinner';
import StatusBadge from '@/components/StatusBadge';
import DebugModal from '@/components/DebugModal';
import SessionsSidebar from '@/components/SessionsSidebar';

interface Session {
  sessionId: string;
  status: string;
  videoPath: string;
  workflowActions: number;
  workflow?: any;  // Workflow object (present after processing)
  scriptPath?: string;
  testVideoPath?: string;
  createdAt: string;
}

interface Screenshot {
  url: string;
  timestamp: string;
}

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [processing, setProcessing] = useState(false);
  const [running, setRunning] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showProcessForm, setShowProcessForm] = useState(false);
  const [showArtifact, setShowArtifact] = useState(false);
  const [showDebugModal, setShowDebugModal] = useState(false);
  const [workflowJson, setWorkflowJson] = useState<any>(null);
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [formData, setFormData] = useState({
    startingUrl: 'https://example.com',
    workflowName: '',
    workflowDescription: ''
  });

  // WebSocket connection
  const { isConnected, lastMessage } = useWebSocket(sessionId);

  // Load initial session data
  const loadSession = useCallback(async () => {
    try {
      const { data, error: apiError } = await getSessionApiSessionsSessionIdGet({
        path: {
          session_id: sessionId
        }
      });
      
      if (apiError) throw new Error('Session not found');
      if (data) setSession(data as Session);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  // Handle WebSocket messages
  useEffect(() => {
    if (lastMessage) {
      setMessages(prev => [...prev, lastMessage]);
      
      // Update session status
      if (lastMessage.type === 'status' && lastMessage.status) {
        const newStatus = lastMessage.status;
        setSession(prev => prev ? { ...prev, status: newStatus } : null);
        
        // Stop processing indicator when done
        if (newStatus === 'processed' || newStatus === 'error') {
          setProcessing(false);
          // Refetch session to get updated workflow action count
          loadSession();
        }
        
        if (newStatus === 'complete' || newStatus === 'error') {
          setRunning(false);
        }
        
        // Handle test execution status
        if (newStatus === 'testing') {
          setTesting(true);
        }
        
        if (newStatus === 'test_complete' || newStatus === 'test_failed') {
          setTesting(false);
          // Refetch session to get test video path
          loadSession();
        }
      }
      
      // Handle screenshot messages
      if (lastMessage.type === 'screenshot' && lastMessage.imageUrl) {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        setScreenshots(prev => [
          ...prev,
          {
            url: `${apiUrl}${lastMessage.imageUrl}`,
            timestamp: lastMessage.timestamp || new Date().toISOString()
          }
        ]);
      }
      
      // Handle completion
      if (lastMessage.type === 'complete') {
        if (lastMessage.success && lastMessage.scriptPath) {
          setSession(prev => prev ? { ...prev, scriptPath: lastMessage.scriptPath, status: 'complete' } : null);
        }
        setRunning(false);
      }
    }
  }, [lastMessage, loadSession]);

  const handleProcessVideo = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      setProcessing(true);
      setError(null);
      setShowProcessForm(false);
      
      // Use generated API client instead of fetch
      const { data, error: apiError } = await processVideoApiSessionsSessionIdProcessPost({
        path: {
          session_id: sessionId
        },
        body: {
          starting_url: formData.startingUrl,
          workflow_name: formData.workflowName || undefined,
          workflow_description: formData.workflowDescription || undefined
        }
      });
      
      if (apiError) {
        throw new Error('Processing failed');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Processing failed');
      setProcessing(false);
    }
  };

  const handleViewArtifact = async () => {
    try {
      // Use generated API client
      const { data, error: apiError } = await getWorkflowApiSessionsSessionIdWorkflowGet({
        path: {
          session_id: sessionId
        }
      });
      
      if (apiError) {
        throw new Error('Failed to fetch workflow');
      }
      
      setWorkflowJson(data);
      setShowArtifact(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflow');
    }
  };

  const handleStartAgent = async () => {
    try {
      setRunning(true);
      setError(null);
      
      // TODO: Replace with generated API client after regeneration
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/api/sessions/${sessionId}/start`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start agent');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start agent');
      setRunning(false);
    }
  };

  const handleTestScript = async () => {
    try {
      setTesting(true);
      setError(null);
      
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/api/sessions/${sessionId}/test`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start test execution');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start test execution');
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-gray-600">Loading session...</p>
        </div>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-red-500">Error: {error}</div>
      </div>
    );
  }

  const canProcess = session?.status === 'uploaded';
  const isProcessed = session?.status === 'processed';

  return (
    <div className="flex h-screen">
      {/* Sessions Sidebar */}
      <SessionsSidebar />
      
      {/* Main Content */}
      <main className={showArtifact ? "flex-1 flex overflow-hidden" : "flex-1 overflow-y-auto"}>
        <div className={showArtifact ? "w-1/2 overflow-y-auto p-8 md:p-24" : "max-w-4xl mx-auto p-8 md:p-24"}>
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Session</h1>
            <p className="text-sm text-gray-500 font-mono">{sessionId}</p>
          </div>
        
        {/* Connection Status & Debug Button */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-sm text-gray-600">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <button
            onClick={() => setShowDebugModal(true)}
            className="text-sm text-gray-600 hover:text-gray-800 px-3 py-1 rounded border border-gray-300 hover:border-gray-400 transition-colors"
          >
            🐛 Debug Log ({messages.length})
          </button>
        </div>
        
        {/* Session Details */}
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Session Details</h2>
          <div className="space-y-3">
            <div>
              <div className="text-sm text-gray-500 mb-1">Status</div>
              <StatusBadge status={session?.status || 'created'} />
            </div>
            <div className="flex">
              <span className="font-medium w-32">Created:</span>
              <span className="text-gray-600">
                {session?.createdAt ? new Date(session.createdAt).toLocaleString() : 'N/A'}
              </span>
            </div>
            <div className="flex">
              <span className="font-medium w-32">Video:</span>
              <span className="text-gray-600">{session?.videoPath ? '✅ Uploaded' : '❌ Missing'}</span>
            </div>
            {isProcessed && (
              <div className="flex">
                <span className="font-medium w-32">Actions:</span>
                <span className="text-gray-600">{session?.workflowActions} detected</span>
              </div>
            )}
          </div>
          
          {/* Workflow Artifact Button - Always visible if workflow exists */}
          {session?.workflowActions && session.workflowActions > 0 && (
            <div className="mt-4 pt-4 border-t">
              <button
                onClick={handleViewArtifact}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors w-full"
              >
                📄 View Workflow Artifact
              </button>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        {canProcess && !showProcessForm && (
          <div className="mb-6">
            <button
              onClick={() => setShowProcessForm(true)}
              disabled={processing}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              Process Video
            </button>
            <p className="text-sm text-gray-500 mt-2">
              Click to analyze the video and extract workflow actions
            </p>
          </div>
        )}

        {/* Process Video Form */}
        {showProcessForm && (
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Configure Workflow Processing</h2>
            <form onSubmit={handleProcessVideo} className="space-y-4">
              <div>
                <label htmlFor="startingUrl" className="block text-sm font-medium text-gray-700 mb-1">
                  Starting URL *
                </label>
                <input
                  type="url"
                  id="startingUrl"
                  required
                  value={formData.startingUrl}
                  onChange={(e) => setFormData({ ...formData, startingUrl: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="https://example.com"
                />
                <p className="text-xs text-gray-500 mt-1">The initial URL shown in your video</p>
              </div>

              <div>
                <label htmlFor="workflowName" className="block text-sm font-medium text-gray-700 mb-1">
                  Workflow Name <span className="text-gray-400 text-xs">(optional)</span>
                </label>
                <input
                  type="text"
                  id="workflowName"
                  value={formData.workflowName}
                  onChange={(e) => setFormData({ ...formData, workflowName: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Leave empty to auto-extract from video"
                />
                <p className="text-xs text-gray-500 mt-1">AI will extract from video if not provided</p>
              </div>

              <div>
                <label htmlFor="workflowDescription" className="block text-sm font-medium text-gray-700 mb-1">
                  Workflow Description <span className="text-gray-400 text-xs">(optional)</span>
                </label>
                <textarea
                  id="workflowDescription"
                  rows={3}
                  value={formData.workflowDescription}
                  onChange={(e) => setFormData({ ...formData, workflowDescription: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Leave empty to auto-extract from video"
                />
                <p className="text-xs text-gray-500 mt-1">AI will extract from video if not provided</p>
              </div>

              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={processing}
                  className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  {processing ? 'Processing...' : 'Start Processing'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowProcessForm(false)}
                  disabled={processing}
                  className="bg-gray-200 hover:bg-gray-300 disabled:bg-gray-100 text-gray-700 px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {isProcessed && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-6 mb-6">
            <h3 className="font-semibold text-green-800 mb-2">✅ Video Processed</h3>
            <p className="text-green-700 text-sm mb-3">
              Detected {session?.workflowActions} actions. Ready to generate test script.
            </p>
            <button
              onClick={handleStartAgent}
              disabled={running}
              className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
            >
              {running ? '🤖 Agent Running...' : '🚀 Start Agent'}
            </button>
          </div>
        )}
        
        {/* Agent Complete */}
        {session?.status === 'complete' && session.scriptPath && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
            <h3 className="font-semibold text-blue-800 mb-2">🎉 Test Script Generated!</h3>
            <p className="text-blue-700 text-sm mb-3">
              Agent completed successfully. Your Playwright test script is ready.
            </p>
            <div className="flex gap-3">
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/scripts/${sessionId}/test.py`}
                download
                className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                📥 Download Test Script
              </a>
              <button
                onClick={handleTestScript}
                disabled={testing}
                className="bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                {testing ? '🧪 Testing...' : '🧪 Test Script'}
              </button>
            </div>
          </div>
        )}
        
        {/* Test Execution Running */}
        {testing && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-3">
              <LoadingSpinner size="sm" />
              <div>
                <div className="font-medium text-green-800">Test Execution Running</div>
                <div className="text-sm text-green-600">
                  Running your test script in Docker container...
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Test Complete */}
        {(session?.status === 'test_complete' || session?.status === 'test_failed') && (
          <div className={`border rounded-lg p-6 mb-6 ${
            session.status === 'test_complete' 
              ? 'bg-green-50 border-green-200' 
              : 'bg-red-50 border-red-200'
          }`}>
            <h3 className={`font-semibold mb-2 ${
              session.status === 'test_complete' ? 'text-green-800' : 'text-red-800'
            }`}>
              {session.status === 'test_complete' ? '✅ Test Execution Complete!' : '❌ Test Execution Failed'}
            </h3>
            <p className={`text-sm mb-3 ${
              session.status === 'test_complete' ? 'text-green-700' : 'text-red-700'
            }`}>
              {session.status === 'test_complete' 
                ? 'Your test script has been executed successfully. Watch the video recording below.'
                : 'The test execution encountered an error. Watch the video below to see what happened.'
              }
            </p>
            
            {session.status === 'test_failed' && (
              <button
                onClick={handleTestScript}
                disabled={testing}
                className="bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors mb-4"
              >
                🔄 Retry Test Execution
              </button>
            )}
            
            {/* Show video for both success and failure */}
            {session.testVideoPath && (
              <div className="mt-4">
                <h4 className={`font-medium mb-2 ${
                  session.status === 'test_complete' ? 'text-green-800' : 'text-red-800'
                }`}>
                  Test Execution Video:
                </h4>
                <video
                  controls
                  className={`w-full max-w-2xl rounded-lg border ${
                    session.status === 'test_complete' ? 'border-green-300' : 'border-red-300'
                  }`}
                  src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/test-videos/${sessionId}/execution.webm`}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
            )}
          </div>
        )}

        {/* Agent Running Progress */}
        {running && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-3">
              <LoadingSpinner size="sm" />
              <div>
                <div className="font-medium text-blue-800">Agent Running</div>
                <div className="text-sm text-blue-600">
                  Generating test script... {screenshots.length} screenshots captured
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error Display with Retry Options */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800 text-sm font-medium mb-2">Error: {error}</p>
          </div>
        )}
        
        {/* Error State - Show Retry Options */}
        {session?.status === 'error' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
            <h3 className="font-semibold text-red-800 mb-2">❌ Operation Failed</h3>
            <p className="text-red-700 text-sm mb-4">
              The last operation encountered an error. You can retry from where it failed.
            </p>
            
            {/* Determine which step failed and show appropriate retry */}
            {!session.workflow && (
              <button
                onClick={() => setShowProcessForm(true)}
                className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                🔄 Retry Video Processing
              </button>
            )}
            
            {session.workflow && !session.scriptPath && (
              <button
                onClick={handleStartAgent}
                disabled={running}
                className="bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                🔄 Retry Agent Execution
              </button>
            )}
            
            {session.scriptPath && (
              <button
                onClick={handleTestScript}
                disabled={testing}
                className="bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                🔄 Retry Test Execution
              </button>
            )}
          </div>
        )}

        {/* Screenshot Stream */}
        {screenshots.length > 0 && (
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Agent Progress</h2>
            <ScreenshotStream screenshots={screenshots} />
          </div>
        )}

        </div>

        {/* Full-height Workflow Artifact Viewer */}
        {showArtifact && (
          <div className="w-1/2 h-screen overflow-y-auto bg-gray-900 text-gray-100 p-8">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-semibold">Workflow Artifact</h2>
              <button
                onClick={() => setShowArtifact(false)}
                className="text-gray-400 hover:text-white text-3xl leading-none font-light"
                title="Close artifact view"
              >
                ×
              </button>
            </div>
            <div className="bg-gray-800 rounded-lg p-6 overflow-auto">
              <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap break-words">
                {workflowJson ? JSON.stringify(workflowJson, null, 2) : 'Loading...'}
              </pre>
            </div>
          </div>
        )}
      </main>

      {/* Debug Modal */}
      <DebugModal 
        isOpen={showDebugModal}
        onClose={() => setShowDebugModal(false)}
        messages={messages}
      />
    </div>
  );
}
