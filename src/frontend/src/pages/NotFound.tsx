import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { buttonVariants } from '../components/ui/button';

export function NotFound() {
  const { t } = useTranslation('error');

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center space-y-6 max-w-md">
        <div className="flex justify-center">
          <div className="bg-amber-100 dark:bg-amber-900/30 p-4 rounded-full">
            <AlertTriangle className="w-12 h-12 text-amber-600 dark:text-amber-500" />
          </div>
        </div>
        
        <h1 className="text-3xl font-bold text-foreground">
          {t('notFoundTitle')}
        </h1>
        
        <p className="text-muted-foreground text-lg">
          {t('notFoundMessage')}
        </p>

        <Link
          to="/"
          className={buttonVariants({ variant: 'default', className: 'px-6' })}
        >
          {t('dashboard')}
        </Link>
      </div>
    </div>
  );
}
