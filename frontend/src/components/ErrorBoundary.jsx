import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * Route-level error boundary: a rendering bug on one page shows a recoverable
 * message instead of blanking the whole application. Keyed on the route path
 * by the caller so navigating away resets it.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface in the console for developers; never send record content anywhere.
    console.error('Page render failed', error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty-state" role="alert" style={{ minHeight: '50vh' }}>
        <AlertTriangle size={32} aria-hidden="true" style={{ color: 'var(--status-amber)' }} />
        <div className="empty-state-title">This page failed to display</div>
        <p style={{ fontSize: '0.82rem', marginTop: 6, maxWidth: 420, marginInline: 'auto' }}>
          The problem has been contained to this page. You can retry, or go back to the dashboard.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 14 }}>
          <button type="button" className="btn btn-secondary" onClick={() => this.setState({ error: null })}>Retry</button>
          <a className="btn btn-primary" href="/dashboard">Go to dashboard</a>
        </div>
      </div>
    );
  }
}
