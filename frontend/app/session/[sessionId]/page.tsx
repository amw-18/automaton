'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getSessionApiSessionsSessionIdGet, processVideoApiSessionsSessionIdProcessPost } from '@/lib/api-client';
import { useWebSocket, WebSocketMessage } from '@/lib/useWebSocket';

interface Session {
  sessionId: string;
  status: string;
  videoPath: string;
  workflowActions: number;
  createdAt: string;
}

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [processing, setProcessing] = useState(false);
  const [showProcessForm, setShowProcessForm] = useState(false);
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
      }
    }
  }, [lastMessage]);

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
          workflow_name: formData.workflowName,
          workflow_description: formData.workflowDescription
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

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-xl">Loading session...</div>
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
    <main className="min-h-screen p-8 md:p-24">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Session</h1>
        <p className="text-sm text-gray-500 mb-8 font-mono">{sessionId}</p>
        
        {/* Connection Status */}
        <div className="mb-6 flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-sm text-gray-600">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        
        {/* Session Details */}
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Session Details</h2>
          <div className="space-y-2 text-sm">
            <div className="flex">
              <span className="font-medium w-32">Status:</span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                session?.status === 'uploaded' ? 'bg-blue-100 text-blue-800' :
                session?.status === 'processing' ? 'bg-yellow-100 text-yellow-800' :
                session?.status === 'processed' ? 'bg-green-100 text-green-800' :
                session?.status === 'error' ? 'bg-red-100 text-red-800' :
                'bg-gray-100 text-gray-800'
              }`}>
                {session?.status}
              </span>
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
                  Workflow Name *
                </label>
                <input
                  type="text"
                  id="workflowName"
                  required
                  value={formData.workflowName}
                  onChange={(e) => setFormData({ ...formData, workflowName: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Login workflow"
                />
                <p className="text-xs text-gray-500 mt-1">A short name for this workflow</p>
              </div>

              <div>
                <label htmlFor="workflowDescription" className="block text-sm font-medium text-gray-700 mb-1">
                  Workflow Description *
                </label>
                <textarea
                  id="workflowDescription"
                  required
                  rows={3}
                  value={formData.workflowDescription}
                  onChange={(e) => setFormData({ ...formData, workflowDescription: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Describe what this workflow does..."
                />
                <p className="text-xs text-gray-500 mt-1">Describe the purpose of this workflow</p>
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
            <p className="text-green-700 text-sm">
              Detected {session?.workflowActions} actions. Ready to generate test script.
            </p>
            <p className="text-xs text-green-600 mt-2">
              (Test script generation will be implemented in the next task)
            </p>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}

        {/* WebSocket Messages Log */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Activity Log</h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {messages.length === 0 ? (
              <p className="text-gray-500 text-sm">No activity yet...</p>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className="text-sm border-l-2 border-blue-500 pl-3 py-1">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium">{msg.type}</span>
                      {msg.status && <span className="text-gray-600"> - {msg.status}</span>}
                      {msg.log?.message && (
                        <div className="text-gray-500 text-xs mt-1">{msg.log.message}</div>
                      )}
                    </div>
                    {msg.timestamp && (
                      <span className="text-xs text-gray-400">
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
