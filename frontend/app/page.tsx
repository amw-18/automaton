'use client';

import { useEffect, useState } from 'react';
import VideoUploader from '@/components/VideoUploader';
import { healthApiHealthGet } from '@/lib/api-client';

export default function Home() {
  const [apiStatus, setApiStatus] = useState<string>('checking...');

  useEffect(() => {
    // Test the API connection using generated client
    healthApiHealthGet()
      .then(({ data, error }) => {
        if (error || !data) {
          setApiStatus('disconnected ❌');
        } else {
          setApiStatus('connected ✅');
        }
      })
      .catch(() => setApiStatus('disconnected ❌'));
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4">Automaton</h1>
        <p className="text-xl text-gray-600 mb-2">
          AI-Powered Test Automation
        </p>
        <div className="text-xs text-gray-400">
          API Status: {apiStatus}
        </div>
      </div>

      <VideoUploader />

      <div className="mt-12 text-center text-sm text-gray-500">
        <p>Upload a video of your workflow</p>
        <p>We'll generate a Playwright test script for you</p>
      </div>
    </main>
  );
}
