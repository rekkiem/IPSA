/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Sirve los JSON del agente desde /reports como archivos estáticos
  // En producción, reemplazar por S3/CDN o API route real
  async rewrites() {
    return [
      {
        source: '/api/reports/:path*',
        destination: '/api/reports/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
