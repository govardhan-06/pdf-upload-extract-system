# PDF Text Extractor

A Next.js application for extracting and analyzing text from PDF documents. This project allows users to view PDFs, extract text, and visualize the extracted content with bounding box highlighting.

The deployed website can be seen at [https://pdf-upload-extract-system-j4k0htu2n.vercel.app](https://pdf-upload-extract-system-j4k0htu2n.vercel.app).

The backend is deployed using Azure as a Docker container with 2 vCPUs.

## Features

- PDF viewing with zoom and navigation controls
- Text extraction from PDFs
- Text chunk visualization
- Bounding box highlighting for extracted text

## Technologies Used

- **Next.js 15**: A React framework for building server-side rendered applications.
- **TypeScript**: A typed superset of JavaScript that compiles to plain JavaScript.
- **Tailwind CSS**: A utility-first CSS framework for styling.
- **React PDF Viewer**: A library for rendering PDF documents in React applications.
- **pdfjs-dist**: A library for parsing and rendering PDF files.
- **EasyOCR**: An OCR library used in the backend for text extraction from PDFs.
- **PyMuPDF**: A Python library used in the backend for PDF parsing and text processing.
