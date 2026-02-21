/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  typescript: {
    ignoreBuildErrors: false,
  },
  // Do NOT set NEXT_PUBLIC_API_URL or add rewrites() here.
  // All /api/* requests use relative URLs and are routed through
  // Caddy reverse proxy to jsr-backend:8000.
}

module.exports = nextConfig
