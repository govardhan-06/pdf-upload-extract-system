'use client';

import { useState, useEffect } from 'react';
import { Worker, Viewer, Position } from '@react-pdf-viewer/core';
import type { SpecialZoomLevel, RenderPageProps } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin } from '@react-pdf-viewer/default-layout';
import { highlightPlugin, Trigger } from '@react-pdf-viewer/highlight';
import { useSearchParams } from 'next/navigation';
import { useTheme } from '../ThemeProvider';
import ReactMarkdown from 'react-markdown';

// Import styles
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import '@react-pdf-viewer/highlight/lib/styles/index.css';

interface TextChunk {
  text: string;
  bbox: number[];
  page: number;
}

interface Highlight {
  pageIndex: number;
  boundingRect: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  };
  text: string;
}

export default function PDFViewer() {
  const [textChunks, setTextChunks] = useState<TextChunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<TextChunk | null>(null);
  const searchParams = useSearchParams();
  const { theme } = useTheme();
  const pdfUrl = searchParams.get('url');

  const defaultLayoutPluginInstance = defaultLayoutPlugin({
    sidebarTabs: (defaultTabs) => [],
  });

  const highlightPluginInstance = highlightPlugin({
    trigger: Trigger.None,
  });

  // Convert TextChunk to Highlight format
  const createHighlight = (chunk: TextChunk): Highlight => {
    const [x1, y1, x2, y2] = chunk.bbox;
    return {
      pageIndex: chunk.page - 1, // Convert 1-based to 0-based page index
      boundingRect: {
        x1,
        y1,
        x2,
        y2,
      },
      text: chunk.text,
    };
  };

  // Custom render for the page that includes highlights with zoom stability
  const renderPage = (props: RenderPageProps) => {
    return (
      <>
        {/* Main content layers */}
        {props.canvasLayer.children}
        {props.textLayer.children}
        {props.annotationLayer.children}

        {/* Highlight overlay */}
        {selectedChunk && selectedChunk.page - 1 === props.pageIndex && (
          <div
            style={{
              position: 'absolute',
              left: `${selectedChunk.bbox[0] * props.scale}px`,
              top: `${selectedChunk.bbox[1] * props.scale}px`,
              width: `${(selectedChunk.bbox[2] - selectedChunk.bbox[0]) * props.scale}px`,
              height: `${(selectedChunk.bbox[3] - selectedChunk.bbox[1]) * props.scale}px`,
              backgroundColor: 'rgba(59, 130, 246, 0.3)',
              mixBlendMode: 'multiply',
              border: '2px solid rgba(59, 130, 246, 0.7)',
              borderRadius: '2px',
              pointerEvents: 'none',
              transition: 'all 0.1s ease',
            }}
          />
        )}
      </>
    );
  };

  useEffect(() => {
    const fetchTextChunks = async () => {
      if (!pdfUrl) {
        setError('No PDF URL provided');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`http://localhost:8000/extract?pdf_url=${encodeURIComponent(pdfUrl)}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          }
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        if (data.text_chunks && Array.isArray(data.text_chunks)) {
          setTextChunks(data.text_chunks);
        } else {
          throw new Error('Invalid response format');
        }
      } catch (error) {
        console.error('Error fetching text chunks:', error);
        setError(error instanceof Error ? error.message : 'Failed to fetch text chunks');
      } finally {
        setLoading(false);
      }
    };

    fetchTextChunks();
  }, [pdfUrl]);

  // Format text chunks into markdown content
  const formatTextContent = (chunks: TextChunk[]) => {
    const groupedByPage = chunks
      .sort((a, b) => {
        if (a.page !== b.page) return a.page - b.page;
        return a.bbox[1] - b.bbox[1];
      })
      .reduce((acc, chunk) => {
        if (!acc[chunk.page]) {
          acc[chunk.page] = [];
        }
        acc[chunk.page].push(chunk);
        return acc;
      }, {} as Record<number, TextChunk[]>);

    return Object.entries(groupedByPage)
      .sort(([pageA], [pageB]) => Number(pageA) - Number(pageB))
      .map(([page, chunks]) => {
        const pageContent = chunks.map((chunk, index) => ({
          ...chunk,
          isSelected: chunk === selectedChunk
        }));

        return (
          <div key={page} className="mb-4">
            <div className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Page {page}
            </div>
            <div className="text-content">
              {pageContent.map((chunk, index) => (
                <span
                  key={`${page}-${index}`}
                  className={`inline cursor-pointer ${
                    chunk.isSelected
                      ? 'bg-blue-100 dark:bg-blue-900/50'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-800/50'
                  } rounded px-1 py-0.5 transition-colors`}
                  onClick={() => setSelectedChunk(chunk)}
                >
                  <ReactMarkdown
                    components={{
                      p: ({ children }) => (
                        <span className={`inline ${
                          chunk.isSelected
                            ? 'text-blue-900 dark:text-blue-100'
                            : 'text-gray-800 dark:text-gray-200'
                        }`}>
                          {children}
                        </span>
                      ),
                      strong: ({ children }) => (
                        <strong className="font-semibold text-gray-900 dark:text-white">
                          {children}
                        </strong>
                      ),
                      em: ({ children }) => (
                        <em className="italic text-gray-800 dark:text-gray-200">
                          {children}
                        </em>
                      ),
                    }}
                  >
                    {chunk.text}
                  </ReactMarkdown>
                  {index < pageContent.length - 1 && ' '}
                </span>
              ))}
            </div>
          </div>
        );
      });
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-900">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-300">Loading PDF and extracting text...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-900">
        <div className="text-center p-8 max-w-md bg-white dark:bg-gray-800 rounded-lg shadow-lg">
          <p className="text-red-500 mb-4">Error: {error}</p>
          <a
            href="/"
            className="inline-block px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Go Back Home
          </a>
        </div>
      </div>
    );
  }

  const proxyUrl = pdfUrl ? `http://localhost:8000/pdf/?pdf_url=${encodeURIComponent(pdfUrl)}` : null;

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      <div className="container mx-auto p-4">
        <div className="grid grid-cols-2 gap-6">
          {/* PDF Viewer */}
          <div className="h-[calc(100vh-2rem)] bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden">
            {proxyUrl && (
              <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js">
                <Viewer
                  fileUrl={proxyUrl}
                  plugins={[defaultLayoutPluginInstance, highlightPluginInstance]}
                  theme={theme === 'dark' ? 'dark' : 'light'}
                  defaultScale={1}
                  renderPage={renderPage}
                  onPageChange={() => setSelectedChunk(null)}
                  onZoom={({ scale }) => {
                    // Force re-render when zoom changes
                    if (selectedChunk) {
                      const updatedChunk = { ...selectedChunk };
                      setSelectedChunk(null);
                      setTimeout(() => setSelectedChunk(updatedChunk), 0);
                    }
                  }}
                  renderError={(error) => (
                    <div className="flex items-center justify-center h-full">
                      <div className="text-center p-4">
                        <p className="text-red-500 mb-4">Failed to load PDF</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          There was an error loading the PDF. Please try again.
                        </p>
                        <a
                          href={pdfUrl || '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-block mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
                        >
                          Open PDF in New Tab
                        </a>
                      </div>
                    </div>
                  )}
                  renderLoader={(percentages: number) => (
                    <div className="flex items-center justify-center h-full">
                      <div className="text-center">
                        <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                        <p>Loading PDF... {Math.round(percentages)}%</p>
                      </div>
                    </div>
                  )}
                />
              </Worker>
            )}
          </div>

          {/* Text Content Panel */}
          <div className="h-[calc(100vh-2rem)] bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 overflow-y-auto">
            <div className="space-y-4 text-base leading-relaxed">
              {formatTextContent(textChunks)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 