"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { MarketingLayout } from "../site-chrome";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");

  function continueToWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = email.trim().toLowerCase();
    if (!value) return;
    sessionStorage.setItem("boardproof.demo-email", value);
    router.push("/dashboard");
  }

  return (
    <MarketingLayout>
      <main id="main-content" className="login-main">
        <section className="login-card">
          <p className="eyebrow">BoardProof workspace</p>
          <h1>Continue to your workspace</h1>
          <p className="login-summary">Use the local demo workspace to inspect the Arduino and TMP102 examples.</p>
          <form className="login-form" onSubmit={continueToWorkspace}>
            <label htmlFor="demo-email">Email address</label>
            <input
              autoComplete="email"
              id="demo-email"
              name="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            />
            <button className="site-button site-button-primary" type="submit">Continue to workspace</button>
          </form>
          <p className="demo-auth-note">Demo access only. This saves your email in this browser tab; password-based accounts are not enabled.</p>
          <Link className="text-link" href="/">Back to BoardProof</Link>
        </section>
      </main>
    </MarketingLayout>
  );
}
