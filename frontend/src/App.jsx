import React from 'react'
import TranslationApp from './TranslationApp.jsx'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          background: '#080c14',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'monospace',
          padding: '2rem',
          gap: '1rem'
        }}>
          <div style={{ fontSize: '3rem' }}>❌</div>
          <h2 style={{ color: '#f87171' }}>App crashed — see error below</h2>
          <pre style={{
            background: '#0d1220',
            border: '1px solid #f87171',
            borderRadius: '8px',
            padding: '1.5rem',
            maxWidth: '800px',
            width: '100%',
            overflowX: 'auto',
            color: '#fca5a5',
            fontSize: '0.85rem',
            lineHeight: '1.6'
          }}>
            {this.state.error?.toString()}
            {'\n\n'}
            {this.state.error?.stack}
          </pre>
          <p style={{ color: '#94a3b8', fontSize: '0.9rem' }}>
            Copy this error and share it to get help fixing it.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '0.6rem 1.5rem',
              background: 'rgba(79,158,255,0.15)',
              border: '1px solid #4f9eff',
              borderRadius: '8px',
              color: '#4f9eff',
              cursor: 'pointer',
              fontFamily: 'monospace'
            }}
          >
            🔄 Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <TranslationApp />
    </ErrorBoundary>
  )
}