import React from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '../components/SEO';

export const NotFound: React.FC = () => {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen px-4 bg-gray-50">
      <SEO 
        title="Page Not Found" 
        description="The page you are looking for does not exist or has been moved." 
      />
      <div className="text-center max-w-md w-full pt-12 pb-24">
        <h1 className="text-6xl font-extrabold text-blue-600 mb-4">404</h1>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Page Not Found</h2>
        <p className="text-gray-600 mb-8">
          We couldn't find the page you're looking for. It might have been moved or deleted.
        </p>
        <Link 
          to="/" 
          className="inline-flex items-center justify-center w-full sm:w-auto px-8 py-3 text-base font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 md:text-lg"
        >
          Return to Dashboard
        </Link>
      </div>
    </main>
  );
};