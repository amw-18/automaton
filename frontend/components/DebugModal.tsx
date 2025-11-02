'use client';

import { WebSocketMessage } from '@/lib/useWebSocket';

interface DebugModalProps {
  isOpen: boolean;
  onClose: () => void;
  messages: WebSocketMessage[];
}

export default function DebugModal({ isOpen, onClose, messages }: DebugModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-xl font-semibold">Debug Activity Log</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-2">
            {messages.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-8">
                No activity yet...
              </p>
            ) : (
              messages.map((msg, idx) => (
                <div
                  key={idx}
                  className="text-sm border-l-2 border-blue-500 pl-3 py-2 bg-gray-50 rounded"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <span className="font-medium text-blue-700">{msg.type}</span>
                      {msg.status && (
                        <span className="text-gray-600 ml-2">- {msg.status}</span>
                      )}
                      {msg.log?.message && (
                        <div className="text-gray-500 text-xs mt-1 font-mono">
                          {msg.log.message}
                        </div>
                      )}
                      {msg.imageUrl && (
                        <div className="text-gray-500 text-xs mt-1">
                          📸 Screenshot: {msg.imageUrl}
                        </div>
                      )}
                      {msg.error && (
                        <div className="text-red-600 text-xs mt-1">
                          ❌ {msg.error}
                        </div>
                      )}
                      {msg.success !== undefined && (
                        <div className={`text-xs mt-1 ${msg.success ? 'text-green-600' : 'text-red-600'}`}>
                          {msg.success ? '✅ Success' : '❌ Failed'}
                          {msg.scriptPath && ` - ${msg.scriptPath}`}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t bg-gray-50">
          <div className="text-sm text-gray-600">
            {messages.length} messages
          </div>
          <button
            onClick={onClose}
            className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
