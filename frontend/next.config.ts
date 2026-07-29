import path from 'path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  devIndicators: false,
  outputFileTracingRoot: path.join(__dirname, '..'),
  turbopack: {
    // Monorepo: dependencies are hoisted to the repo root
    root: path.join(__dirname, '..'),
  },
};

export default nextConfig;
