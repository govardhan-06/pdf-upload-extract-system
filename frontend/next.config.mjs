const nextConfig = {
  webpack: (config) => {
    if (!config.resolve) {
      config.resolve = {};
    }

    config.resolve.fallback = {
      ...config.resolve.fallback,
      canvas: false,
      encoding: false,
      fs: false,
      path: false,
    };

    if (!config.module) {
      config.module = { rules: [] };
    }

    config.module.rules.push({
      test: /\.node$/,
      use: 'node-loader'
    });

    return config;
  },
  transpilePackages: [
    '@react-pdf-viewer/core',
    '@react-pdf-viewer/default-layout',
    'pdfjs-dist'
  ]
};

export default nextConfig;