import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  devIndicators: false,
  turbopack: {
    // Pin the workspace root so stray lockfiles in parent folders don't confuse Next.js
    root: __dirname,
  },
};

export default nextConfig;
