import { StrictMode, Component } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Application crashed:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--paper, #f5f0e8)',
            backgroundImage:
              'radial-gradient(circle at 20% 80%, rgba(184, 134, 11, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(194, 58, 43, 0.03) 0%, transparent 50%)',
            padding: '24px',
            fontFamily: "'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          }}
        >
          <div
            style={{
              maxWidth: '520px',
              width: '100%',
              padding: '32px',
              borderRadius: '16px',
              background: '#fff',
              border: '1px solid var(--gold-light, #d4a843)',
              boxShadow: '0 20px 50px rgba(0, 0, 0, 0.15)',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                width: '56px',
                height: '56px',
                margin: '0 auto 16px',
                borderRadius: '50%',
                background: 'var(--vermilion-bg, #fdf2f0)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '28px',
                fontWeight: 700,
                color: 'var(--vermilion, #c23a2b)',
                border: '1px solid var(--vermilion-light, #d94f3f)',
              }}
            >
              !
            </div>
            <h1
              style={{
                margin: '0 0 8px',
                fontSize: '20px',
                fontWeight: 700,
                color: 'var(--ink, #2c1810)',
                fontFamily: "'Noto Serif SC', 'SimSun', serif",
              }}
            >
              应用遇到了问题
            </h1>
            <p
              style={{
                margin: '0 0 20px',
                fontSize: '14px',
                color: 'var(--ink-light, #4a3728)',
                lineHeight: 1.6,
              }}
            >
              页面在渲染时发生了异常，您可以尝试重新加载。如果问题持续出现，请检查控制台获取详细错误信息。
            </p>
            {this.state.error && (
              <pre
                style={{
                  margin: '0 0 20px',
                  padding: '12px',
                  background: 'var(--paper-dark, #ebe4d8)',
                  border: '1px solid var(--border, #d4c8b8)',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontFamily: "'Fira Code', monospace",
                  color: 'var(--vermilion, #c23a2b)',
                  textAlign: 'left',
                  maxHeight: '160px',
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {this.state.error.toString()}
                {this.state.errorInfo && this.state.errorInfo.componentStack
                  ? `\n\n${this.state.errorInfo.componentStack}`
                  : ''}
              </pre>
            )}
            <button
              onClick={this.handleReload}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '10px 24px',
                borderRadius: '8px',
                border: 'none',
                background: 'linear-gradient(135deg, #3d2b1f 0%, #5c3d2e 50%, #3d2b1f 100%)',
                color: '#fff',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                boxShadow: '0 4px 14px rgba(194, 58, 43, 0.2)',
              }}
            >
              重新加载
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
