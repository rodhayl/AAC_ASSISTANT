import React from 'react'
import { useNavigate } from 'react-router'
import { withTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { Button } from './ui/button'

interface InnerBoundaryProps {
  navigate: (to: string) => void;
  children: React.ReactNode;
  t: TFunction;
}

class InnerBoundary extends React.Component<InnerBoundaryProps, { hasError: boolean }> {
  constructor(props: InnerBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error.message, error.stack, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-6 bg-background">
          <div className="max-w-md w-full bg-surface rounded-xl shadow-lg p-6 text-center border border-border">
            <h2 className="text-xl font-semibold text-foreground mb-2">{this.props.t('title')}</h2>
            <p className="text-sm text-muted-foreground mb-4">{this.props.t('subtitle')}</p>
            <div className="flex justify-center gap-3">
              <Button onClick={() => this.setState({ hasError: false })}>{this.props.t('retry')}</Button>
              <Button variant="ghost" onClick={() => this.props.navigate('/')}>{this.props.t('dashboard')}</Button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function ErrorBoundaryBase({ children, t }: { children: React.ReactNode; t: TFunction }) {
  const navigate = useNavigate()
  return <InnerBoundary navigate={navigate} t={t}>{children}</InnerBoundary>
}

export const ErrorBoundary = withTranslation('error')(ErrorBoundaryBase)
