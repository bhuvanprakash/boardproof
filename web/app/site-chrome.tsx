import Link from "next/link";

export function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="marketing-site">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="marketing-header">
        <div className="marketing-shell marketing-nav">
          <Link className="brand" href="/" aria-label="BoardProof home">
            <span className="brand-mark" aria-hidden="true"><span /></span>
            <span>BoardProof</span>
          </Link>
          <nav className="marketing-links" aria-label="Main navigation">
            <Link href="/product">Product</Link>
            <Link href="/how-it-works">How it works</Link>
          </nav>
          <div className="marketing-actions">
            <Link className="sign-in-link" href="/login">Sign in</Link>
            <Link className="site-button site-button-small" href="/login">Open workspace</Link>
          </div>
        </div>
      </header>
      {children}
      <footer className="marketing-footer">
        <div className="marketing-shell footer-layout">
          <div className="footer-brand-block">
            <Link className="brand" href="/">
              <span className="brand-mark" aria-hidden="true"><span /></span>
              <span>BoardProof</span>
            </Link>
            <p>Review hardware changes with traceable evidence.</p>
          </div>
          <nav className="footer-links" aria-label="Footer navigation">
            <Link href="/product">Product</Link>
            <Link href="/how-it-works">How it works</Link>
            <Link href="/login">Sign in</Link>
            <Link href="/dashboard">Dashboard</Link>
          </nav>
          <p className="footer-meta">MVP · Local demo workspace</p>
        </div>
      </footer>
    </div>
  );
}
