/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async redirects() {
    return [
      {
        source: "/dashboard/monitor",
        destination: "/dashboard#live",
        permanent: true,
      },
      {
        source: "/dashboard/analytics",
        destination: "/dashboard#usage",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
