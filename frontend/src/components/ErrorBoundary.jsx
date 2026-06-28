/**
 * ErrorBoundary — Production-grade React class component error boundary.
 *
 * Catches uncaught render/lifecycle errors in any child component tree.
 * Fires-and-forgets a structured error report to the backend logging endpoint.
 * Renders a friendly fallback instead of a blank white screen.
 *
 * Usage: wrap independent UI regions with separate boundaries so that one
 * crashed region never takes down the rest of the app.
 */
import { Component } from 'react';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo);

    // Fire-and-forget: send structured report to the backend logging endpoint.
    // Never let the logging call itself throw (catch swallows all errors).
    fetch('/api/log-client-error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => {});
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      // Allow the parent to supply a fully custom fallback UI.
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          reset: this.handleReset,
        });
      }

      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            minHeight: '120px',
            padding: '2rem',
            textAlign: 'center',
            gap: '8px',
          }}
        >
          <p
            style={{
              fontSize: '14px',
              fontWeight: '500',
              color: '#18181B',
              margin: 0,
            }}
          >
            Something went wrong on this screen.
          </p>
          <p
            style={{
              fontSize: '13px',
              color: '#71717A',
              margin: 0,
              lineHeight: '1.5',
            }}
          >
            Your conversation history is safe. Try refreshing this section.
          </p>
          <button
            onClick={this.handleReset}
            style={{
              marginTop: '8px',
              padding: '6px 16px',
              fontSize: '13px',
              fontWeight: '500',
              color: '#4F46E5',
              background: '#EEF2FF',
              border: '1px solid #C7D2FE',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
