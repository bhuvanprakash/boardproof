import Link from "next/link";
import type { Metadata } from "next";
import { MarketingLayout } from "./site-chrome";

export const metadata: Metadata = {
  title: "BoardProof | Hardware design review",
  description: "Find cross-file hardware issues before a board spin.",
};

const features = [
  {
    number: "01",
    title: "Check the circuit",
    body: "Compare exported netlists with reviewed component limits and firmware pin mappings.",
  },
  {
    number: "02",
    title: "Review the board",
    body: "Inspect placement in 2D and 3D, check copper connectivity, and export manufacturing files.",
  },
  {
    number: "03",
    title: "Keep the evidence",
    body: "Save reports, datasheet citations, source hashes, and revision comparisons with the design.",
  },
];

export default function Home() {
  return (
    <MarketingLayout>
      <main id="main-content" className="marketing-main">
        <section className="marketing-shell marketing-hero">
          <div className="hero-copy">
            <p className="eyebrow">Hardware review for small teams</p>
            <h1>Catch cross-file hardware issues before the next board spin.</h1>
            <p className="hero-summary">
              BoardProof checks the links between your netlist, component rules, firmware, and PCB.
              Review findings and unresolved checks with the revision.
            </p>
            <div className="hero-actions">
              <Link className="site-button site-button-primary" href="/login">Open the workspace</Link>
              <Link className="site-button site-button-secondary" href="/product">See how it works</Link>
            </div>
            <p className="hero-note">Deterministic checks. Rule-level findings. Approval status shown when recorded.</p>
          </div>

          <article className="board-preview-card" aria-label="TMP102 Rev C demo board preview">
            <div className="preview-card-head">
              <div>
                <span className="preview-kicker">Demo board</span>
                <strong>TMP102 · Rev C</strong>
              </div>
              <span className="review-pill">Review</span>
            </div>
            <figure className="hero-board-image">
              {/* eslint-disable-next-line @next/next/no-img-element -- local demo SVG */}
              <img src="/demo/tmp102-rev-c.svg" alt="TMP102 Rev C printed circuit board layout" />
            </figure>
            <div className="preview-card-foot">
              <div><span>Circuit rules</span><strong>7 configured</strong></div>
              <div><span>PCB routing</span><strong>Review required</strong></div>
              <p>A circuit check does not replace PCB and fabrication review.</p>
            </div>
          </article>
        </section>

        <section className="marketing-section" id="product">
          <div className="marketing-shell">
            <div className="section-intro">
              <p className="eyebrow">One review, connected evidence</p>
              <h2>Hardware changes need more than a schematic check.</h2>
              <p>Bring the design files and rules together before you approve a revision.</p>
            </div>
            <div className="feature-grid">
              {features.map((feature) => (
                <article className="feature-card" key={feature.number}>
                  <span className="feature-number">{feature.number}</span>
                  <h3>{feature.title}</h3>
                  <p>{feature.body}</p>
                </article>
              ))}
            </div>
            <Link className="text-link" href="/product">Explore product checks <span aria-hidden="true">↗</span></Link>
          </div>
        </section>

        <section className="marketing-section workflow-band" id="how-it-works">
          <div className="marketing-shell workflow-layout">
            <div className="section-intro">
              <p className="eyebrow">A review you can repeat</p>
              <h2>From design files to a clear revision record.</h2>
            </div>
            <ol className="workflow-steps">
              <li><span>1</span><div><strong>Import</strong><p>Add a KiCad board, netlist, or design configuration.</p></div></li>
              <li><span>2</span><div><strong>Check</strong><p>Run circuit, firmware, footprint, and board checks.</p></div></li>
              <li><span>3</span><div><strong>Compare</strong><p>Review changed findings and keep the report with its sources.</p></div></li>
            </ol>
          </div>
        </section>

        <section className="marketing-shell demo-callout">
          <div>
            <p className="eyebrow">Try the local demo</p>
            <h2>Explore an Arduino board and a TMP102 revision check.</h2>
            <p>Both demos open in the existing workspace. No project files are needed.</p>
          </div>
          <Link className="site-button site-button-primary" href="/login">Go to the workspace</Link>
        </section>
      </main>
    </MarketingLayout>
  );
}
