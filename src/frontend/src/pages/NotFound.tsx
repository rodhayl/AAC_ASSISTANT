import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';

export function NotFound() {
  const { t } = useTranslation('common');

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="text-center space-y-6 max-w-md">
        <div className="flex justify-center">
          <div className="bg-amber-100 dark:bg-amber-900/30 p-4 rounded-full">
            <AlertTriangle className="w-12 h-12 text-amber-600 dark:text-amber-500" />
          </div>
        </div>
        
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
          {t('errors.notFoundTitle', 'Page Not Found')}
        </h1>
        
        <p className="text-gray-500 dark:text-gray-400 text-lg">
          {t('errors.notFoundMessage', "The page you are looking for doesn't exist or has been moved.")}
        </p>

        <Link 
          to="/" 
          className="inline-block px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
        >
          {t('actions.backHome', 'Go Back Home')}
        </Link>
      </div>
    </div>
  );
}
