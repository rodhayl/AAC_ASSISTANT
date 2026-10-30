import React from 'react'
import { useNavigate } from 'react-router-dom'
import { withTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'

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
        <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50 dark:bg-gray-900">
          <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 text-center">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">{this.props.t('title')}</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{this.props.t('subtitle')}</p>
            <div className="flex justify-center gap-3">
              <button onClick={() => this.setState({ hasError: false })} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">{this.props.t('retry')}</button>
              <button onClick={() => this.props.navigate('/')} className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">{this.props.t('dashboard')}</button>
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
