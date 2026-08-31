import type { Metadata } from "next";
import { Inter, Sora } from "next/font/google";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import { ConfirmProvider } from "@/components/crm/dialogs/ConfirmDialog";
import { ThemeProvider, themeInitScript } from "@/context/ThemeContext";
import { PLATFORM_BRAND } from "@/config/site";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
const sora = Sora({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-sora",
  display: "swap",
});

/**
 * The platform's title, not the CRM's.
 *
 * This is the fallback for every route that does not set its own, which
 * now includes the workspace, the app catalogue and the signup wizard —
 * pages where the visitor has not chosen an app yet. The `(crm)` layout
 * and the marketing pages override it with their own.
 */
export const metadata: Metadata = {
  title: `${PLATFORM_BRAND.name} — ${PLATFORM_BRAND.tagline}`,
  description:
    "One S3K account across every S3K application, with shared users, roles and data boundaries.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${sora.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="antialiased">
        <ThemeProvider>
          <AuthProvider>
            {/* One dialog host and one toast host for the whole app: every
                confirmation and every success/error notice in the CRM is
                raised through these two, so they cannot drift per screen. */}
            <ConfirmProvider>{children}</ConfirmProvider>
            <Toaster position="bottom-right" richColors closeButton />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
