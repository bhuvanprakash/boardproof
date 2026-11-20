import Link from "next/link";
import type { Metadata } from "next";
import { MarketingLayout } from "../site-chrome";

export const metadata: Metadata = {
  title: "Product | BoardProof",
  description: "Circuit, PCB, datasheet, and revision checks for hardware teams.",
};

const checks = [
  ["Circuit", "Check exported nets against explicit voltage, connection, and firmware pin rules."],
  ["PCB", "Inspect footprints, copper connectivity, board rules, and generated Gerber files."],
  ["Parts", "Keep datasheet source, file hash, and cited pages beside the rules that use them."],
  ["Revisions", "Compare reports to see new, fixed, and still-open findings."],
];

export default function ProductPage() {
  return (
    <MarketingLayout>
      <main id="main-content" className="marketing-main">
        <section className="marketing-shell page-hero">
          <p className="eyebrow">Product</p>
          <h1>Checks that connect design files to the rules behind them.</h1>
          <p>BoardProof brings circuit checks, board review, and revision evidence into one workspace.</p>
          <Link className="site-button site-button-primary" href="/login">Open the workspace</Link>
        </section>
        <section className="marketing-section">
          <div className="marketing-shell">
            <div className="product-check-grid">
              {checks.map(([title, body], index) => (
                <article className="feature-card product-check-card" key={title}>
                  <span className="feature-number">0{index + 1}</span>
                  <h2>{title}</h2>
                  <p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="marketing-section workflow-band">
          <div className="marketing-shell product-trust-grid">
            <div>
              <p className="eyebrow">Rule provenance</p>
              <h2>AI can draft a rule. It cannot approve one.</h2>
            </div>
            <p>When configured, Gemini can suggest constraints from a datasheet with page citations. A person reviews those constraints. The deterministic checker decides the result; model output cannot change a pass or fail.</p>
          </div>
        </section>
        <section className="marketing-shell limit-callout">
          <strong>Current scope</strong>
          <p>BoardProof complements KiCad ERC and DRC. It does not replace them. Generated boards without routed copper remain marked for review.</p>
        </section>
      </main>
    </MarketingLayout>
  );
}
