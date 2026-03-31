/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // On Vercel, "localhost" is the Vercel runtime, not your PC.
    // Use BACKEND_URL (server-only) to proxy /api and /ws to your backend.
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
    const backendUrlNoTrailingSlash = backendUrl.replace(/\/$/, '');
    return [
      { source: '/api/:path*', destination: `${backendUrlNoTrailingSlash}/api/:path*` },
      { source: '/ws', destination: `${backendUrlNoTrailingSlash}/ws` },
    ];
  },
};

module.exports = nextConfig;
