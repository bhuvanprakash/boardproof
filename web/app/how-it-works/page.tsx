import Link from "next/link";
import type { Metadata } from "next";
import { MarketingLayout } from "../site-chrome";

export const metadata: Metadata = {
  title: "How it works | BoardProof",
  description: "Import a design, review its rules, and compare hardware revisions.",
};

const steps = [
  { number: "01", title: "Bring in the design", text: "Import a KiCad board, netlist, or firmware source, or select an included demo configuration." },
  { number: "02", title: "Review the rules", text: "Check component limits, firmware mappings, and source citations before using them." },
  { number: "03", title: "Run and compare", text: "Run checks, inspect board views, then compare the report with another revision." },
];

export default function HowItWorksPage() {
  return (
    <MarketingLayout>
      <main id="main-content" className="marketing-main">
        <section className="marketing-shell page-hero">
          <p className="eyebrow">How it works</p>
          <h1>Keep each hardware decision tied to its source.</h1>
          <p>BoardProof turns design inputs and reviewed constraints into checks that can be repeated on the next revision.</p>
        </section>
        <section className="marketing-section">
          <div className="marketing-shell workflow-page-grid">
            {steps.map((step) => (
              <article className="workflow-card" key={step.number}>
                <span className="feature-number">{step.number}</span>
                <h2>{step.title}</h2>
                <p>{step.text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="marketing-shell demo-examples">
          <div>
            <p className="eyebrow">Included examples</p>
            <h2>Start with a board you can inspect.</h2>
          </div>
          <div className="example-list">
            <article><strong>Jeden Uno</strong><p>Arduino Uno-compatible KiCad board with 2D and 3D views.</p></article>
            <article><strong>TMP102</strong><p>Compare Rev B wiring faults with the corrected Rev C configuration.</p></article>
          </div>
          <Link className="site-button site-button-primary" href="/login">Open the workspace</Link>
        </section>
      </main>
    </MarketingLayout>
  );
}
