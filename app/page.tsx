import { DocumentAnalyzer } from "@/components/document-analyzer"

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-white relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-72 bg-[radial-gradient(circle_at_top,rgba(16,185,129,0.22),transparent_55%)] opacity-70 blur-3xl pointer-events-none" />
      <div className="absolute inset-x-0 bottom-0 h-96 bg-[radial-gradient(circle_at_bottom,rgba(245,158,11,0.16),transparent_50%)] opacity-80 blur-3xl pointer-events-none" />
      <DocumentAnalyzer />
    </main>
  )
}
