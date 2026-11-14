import React from 'react';

interface FeatureCardProps {
  title: string;
  description: string;
  icon?: React.ReactNode;
  imageUrl?: string;
}

export const FeatureCard: React.FC<FeatureCardProps> = ({ title, description, icon, imageUrl }) => {
  return (
    <div className="flex flex-col p-6 bg-white rounded-xl shadow-md border border-gray-100 hover:shadow-lg transition-shadow">
      {imageUrl && <img src={imageUrl} alt={title} className="w-full h-48 object-cover rounded-t-lg mb-4" />}
      <div className="flex items-center mb-3">
        {icon && <span className="mr-3 text-blue-600">{icon}</span>}
        <h3 className="text-xl font-semibold text-gray-900">{title}</h3>
      </div>
      <p className="text-gray-600 leading-relaxed">{description}</p>
    </div>
  );
};