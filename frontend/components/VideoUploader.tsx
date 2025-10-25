'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { uploadVideoApiVideosUploadPost } from '@/lib/api-client';

export default function VideoUploader() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = async (file: File) => {
    if (!file.type.startsWith('video/')) {
      setError('Please upload a video file');
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError('File size must be less than 100MB');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      // Use generated API client
      const { data, error: apiError } = await uploadVideoApiVideosUploadPost({
        body: {
          video: file
        }
      });
      
      if (apiError) {
        throw new Error('Upload failed');
      }
      
      // Redirect to session page
      if (data && 'sessionId' in data) {
        router.push(`/session/${data.sessionId}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    
    const file = e.dataTransfer.files[0];
    if (file) {
      handleFile(file);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file);
    }
  };

  return (
    <div className="w-full max-w-md">
      <div
        className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
        } ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept="video/*"
          onChange={handleChange}
          className="hidden"
          id="video-upload"
          disabled={uploading}
        />
        
        <label htmlFor="video-upload" className="cursor-pointer">
          <div className="text-6xl mb-4">📹</div>
          <p className="text-lg font-medium mb-2">
            {uploading ? 'Uploading...' : 'Upload Workflow Video'}
          </p>
          <p className="text-sm text-gray-500">
            Drag & drop or click to select
          </p>
          <p className="text-xs text-gray-400 mt-2">
            Max 100MB • MP4, MOV, WebM
          </p>
        </label>
      </div>

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
