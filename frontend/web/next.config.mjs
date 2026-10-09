/** @type {import('next').NextConfig} */
const backendOrigin = process.env.JARVIS_API_INTERNAL_URL
  || process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === 'development' ? 'http://127.0.0.1:8000' : '');
const configuredBasePath = process.env.NEXT_PUBLIC_BASE_PATH?.trim() || '/';
const basePath = configuredBasePath === '/' ? '' : `/${configuredBasePath.split('/').filter(Boolean).join('/')}`;

const nextConfig = {
  reactStrictMode: false,
  output: 'standalone',
  ...(basePath ? { basePath } : {}),
  // Type errors now fail the build.
  //
  // This was `ignoreBuildErrors: true`, which let seven real type errors ship
  // unnoticed -- including a dead `STREAM_INTERRUPTED` branch in the chat store
  // that could never execute because `'status'` was missing from the stream
  // frame union. The `typescript` block is removed entirely rather than set to
  // `false`, so the compiler's default (enforce) applies.
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
        source: '/api/chat',
        destination: `${backendOrigin}/api/chat`,
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
  async headers() {
    return [{
      source: '/:path*',
      headers: [{
        key: 'Permissions-Policy',
        value: 'camera=(), microphone=(), geolocation=(self)',
      }],
    }];
  },
};

export default nextConfig;
