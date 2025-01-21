'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTheme } from './ThemeProvider';

export default function Home() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      router.push(`/viewer?url=${encodeURIComponent(url)}`);
    } catch (error) {
      console.error('Error processing URL:', error);
      setError(error instanceof Error ? error.message : 'Failed to process URL');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className={`min-h-screen p-8 ${theme === 'dark' ? 'dark' : ''}`}>
      <div className="max-w-3xl mx-auto">
        {/* Header with Theme Toggle */}
        <div className="flex justify-between items-center mb-12">
          <h1 className="text-3xl font-semibold text-gray-900 dark:text-white">PDF Text Extractor</h1>
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>

        {/* URL Input Form */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label 
                htmlFor="pdfUrl" 
                className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2"
              >
                Enter PDF URL
              </label>
              <input
                id="pdfUrl"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/document.pdf"
                className="w-full p-3 border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                required
              />
            </div>
            {error && (
              <div className="text-red-500 text-sm">{error}</div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-500 hover:bg-blue-600 text-white font-medium py-3 px-4 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Processing...' : 'Extract Text'}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}