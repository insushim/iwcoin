"use client";

import { useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import { useDashboardStore } from "@/lib/store";

export default function ClientShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const initialize = useDashboardStore((s) => s.initialize);

  useEffect(() => {
    initialize();
  }, [initialize]);

  return (
    <>
      <Sidebar />
      <main className="min-h-screen lg:ml-60">
        <div className="mx-auto max-w-7xl px-4 py-6 pt-16 lg:pt-6">
          {children}
        </div>
      </main>
    </>
  );
}
