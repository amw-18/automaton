'use client';

import { useState, useEffect } from 'react';

interface Screenshot {
  url: string;
}

interface ScreenshotStreamProps {
  screenshots: Screenshot[];
}

export default function ScreenshotStream({ screenshots }: ScreenshotStreamProps) {
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);

  // Auto-select latest screenshot
  useEffect(() => {
    if (screenshots.length > 0) {
      setSelectedIndex(screenshots.length - 1);
    }
  }, [screenshots.length]);

  if (screenshots.length === 0) {
    return (
      <div className="bg-gray-100 rounded-lg p-12 text-center">
        <div className="text-gray-400 text-lg">
          📸 No screenshots yet
        </div>
        <p className="text-gray-500 text-sm mt-2">
          Screenshots will appear here as the agent executes
        </p>
      </div>
    );
  }

  // Handle case where selectedIndex hasn't been updated yet
  const validIndex = selectedIndex >= 0 ? selectedIndex : screenshots.length - 1;
  const selectedScreenshot = screenshots[validIndex];
  
  // Safety check
  if (!selectedScreenshot) {
    return (
      <div className="bg-gray-100 rounded-lg p-12 text-center">
        <div className="text-gray-400 text-lg">Loading screenshot...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Main Screenshot Display */}
      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="bg-gray-800 text-white px-4 py-2 text-sm flex items-center justify-between">
          <span>Screenshot {validIndex + 1} of {screenshots.length}</span>
        </div>
        <div className="relative w-full" style={{ minHeight: '400px' }}>
          <img
            src={selectedScreenshot.url}
            alt={`Screenshot ${validIndex + 1}`}
            className="w-full h-auto"
          />
        </div>
      </div>

      {/* Thumbnail Timeline */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-sm font-medium mb-3">Timeline</h3>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {screenshots.map((screenshot, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedIndex(idx)}
              className={`flex-shrink-0 w-32 h-20 rounded border-2 overflow-hidden transition-all ${
                idx === validIndex
                  ? 'border-blue-500 ring-2 ring-blue-200'
                  : 'border-gray-200 hover:border-gray-400'
              }`}
            >
              <img
                src={screenshot.url}
                alt={`Thumbnail ${idx + 1}`}
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
