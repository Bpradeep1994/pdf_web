/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  images: {
    domains: ["localhost", "storage.googleapis.com", "avatars.githubusercontent.com", "lh3.googleusercontent.com"],
  },
  webpack: (config) => {
    config.resolve.alias["canvas"] = false;
    return config;
  },
};

export default nextConfig;
