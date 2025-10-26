'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import StatusBadge from './StatusBadge';

interface SessionItem {
  id: string;
  status: string;
  workflowActions: number;
  createdAt: string;
}

export default function SessionsSidebar() {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const params = useParams();
  const router = useRouter();
  const currentSessionId = params.sessionId as string;

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/api/sessions`);
        const data = await response.json();
        setSessions(data.sessions || []);
      } catch (error) {
        console.error('Error fetching sessions:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchSessions();
    
    // Refresh every 10 seconds
    const interval = setInterval(fetchSessions, 10000);
    return () => clearInterval(interval);
  }, []);

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    return date.toLocaleDateString();
  };

  return (
    <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col h-screen">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <h2 className="font-bold text-lg">Sessions</h2>
        <button
          onClick={() => router.push('/')}
          className="mt-2 w-full bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded text-sm font-medium transition-colors"
        >
          + New Session
        </button>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            Loading...
          </div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            No sessions yet
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => router.push(`/session/${session.id}`)}
                className={`w-full text-left p-3 hover:bg-gray-100 transition-colors ${
                  currentSessionId === session.id ? 'bg-blue-50 border-l-4 border-blue-600' : ''
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <StatusBadge status={session.status} />
                  <span className="text-xs text-gray-500">
                    {formatDate(session.createdAt)}
                  </span>
                </div>
                <div className="text-xs text-gray-600">
                  {session.workflowActions > 0 
                    ? `${session.workflowActions} actions` 
                    : 'No workflow'}
                </div>
                <div className="text-xs text-gray-400 font-mono mt-1 truncate">
                  {session.id.slice(0, 8)}...
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
