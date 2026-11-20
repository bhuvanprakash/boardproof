"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Workbench from "../workbench";

export default function DashboardPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setEmail(sessionStorage.getItem("boardproof.demo-email") ?? "");
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready && !email) router.replace("/login");
  }, [email, ready, router]);

  function signOut() {
    sessionStorage.removeItem("boardproof.demo-email");
    router.replace("/");
  }

  if (!ready || !email) {
    return <main className="dashboard-loading" aria-live="polite">Opening workspace…</main>;
  }

  return (
    <>
      <Workbench email={email} onSignOut={signOut} />
    </>
  );
}
