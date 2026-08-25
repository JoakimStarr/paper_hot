'use client';

import React from 'react';
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';

export interface SubfieldRadarProps {
  data: { subfield: string; count: number }[];
}

export default function SubfieldRadar({ data }: SubfieldRadarProps) {
  const { t } = useLanguage();
  const { isDark } = useTheme();

  return (
    <div className="mt-6 sm:mt-8 bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-lg sm:text-xl">🎯</span>
        <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">{t('tr.radarTitle')}</h2>
        <span className="text-xs text-gray-400 hidden sm:inline">{t('tr.radarSub')}</span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke={isDark ? '#4b5563' : '#e5e7eb'} />
          <PolarAngleAxis
            dataKey="subfield"
            tick={{ fontSize: 10, fill: isDark ? '#d1d5db' : '#4b5563' }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 'auto']}
            tick={{ fontSize: 9, fill: '#9ca3af' }}
          />
          <Tooltip
            formatter={(value: number) => [`${value}`, t('tr.radarUnit')]}
            labelFormatter={(label: string) => `${t('tr.subfieldLabel')}: ${label}`}
            contentStyle={isDark ? { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' } : undefined}
          />
          <Radar
            name={t('tr.radarUnit')}
            dataKey="count"
            stroke="#7c3aed"
            fill="#7c3aed"
            fillOpacity={0.25}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}