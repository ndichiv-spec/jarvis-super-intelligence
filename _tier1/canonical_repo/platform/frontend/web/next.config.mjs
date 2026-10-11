/** @type {import('next').NextConfig} */
import path from 'node:path';

const backendOrigin = process.env.JARVIS_API_INTERNAL_URL
  || process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === 'development' ? 'http://127.0.0.1:8000' : '');

const nextConfig = {
  reactStrictMode: false,
  output: 'standalone',
  turbopack: {
    root: path.resolve(process.cwd()),
  },
  async rewrites() {
    if (!backendOrigin) return [];
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendOrigin}/api/v1/:path*`,
      },
      {
        source: '/api/chat/:path*',
        destination: `${backendOrigin}/api/chat/:path*`,
      },
      {
        source: '/api/health',
        destination: `${backendOrigin}/health`,
      },
      {
        source: '/health',
        destination: `${backendOrigin}/health`,
      },
      {
        source: '/api/ping',
        destination: `${backendOrigin}/api/ping`,
      },
      {
        source: '/api/version',
        destination: `${backendOrigin}/api/version`,
      },
    ];
  },
};

export default nextConfig;
