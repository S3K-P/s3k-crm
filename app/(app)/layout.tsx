import Footer from "@/components/Footer";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    // Top-tab shell: each page renders <Header /> as its own sticky top bar.
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg)" }}>
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
      <Footer />
    </div>
  );
}
