import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "material-symbols/outlined.css";
import "./globals.css";

// next/font downloads Inter at build time and serves it from this app, so
// workstations never request fonts from Google.
const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter-next" });

export const metadata: Metadata = {
  title: "ERAS Clinical Remote Monitoring | Risk Queue",
  description: "Post-Operative Remote Monitoring Clinical Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-surface-bright font-body-md text-on-surface antialiased">
        {children}
      </body>
    </html>
  );
}
