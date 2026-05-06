'use client';

import React, { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import PaperCard from '@/components/PaperCard';
import Filters from '@/components/Filters';
import Pagination from '@/components/Pagination';
import { papersApi } from '@/lib/api';
import { Paper } from '@/types/paper';
import { Loader2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

export default function HomePage() {
  const { t } = useLanguage();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize] = useState(12); // 每页显示12篇论文
  const [totalPages, setTotalPages] = useState(1);
  
  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedDiscipline, setSelectedDiscipline] = useState<string | null>(null);
  const [selectedJournal, setSelectedJournal] = useState<string | null>(null);

  useEffect(() => {
    fetchPapers();
  }, [page, minScore, selectedDiscipline, selectedJournal]);

  const fetchPapers = async () => {
    setLoading(true);
    try {
      const response = await papersApi.getPapers({
        page,
        page_size: pageSize,
        min_score: minScore || undefined,
        discipline: selectedDiscipline || undefined,
        journal_name: selectedJournal || undefined,
      });
      setPapers(response.papers);
      setTotal(response.total);
      setTotalPages(Math.ceil(response.total / pageSize));
    } catch (error) {
      console.error('Error fetching papers:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    // 滚动到页面顶部
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleMinScoreChange = (score: number | null) => {
    setMinScore(score);
    setPage(1);
  };

  const handleDisciplineChange = (discipline: string | null) => {
    setSelectedDiscipline(discipline);
    setPage(1);
  };

  const handleJournalChange = (journal: string | null) => {
    setSelectedJournal(journal);
    setPage(1);
  };

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {t('home.title')}
        </h1>
        <p className="text-gray-600">
          {t('home.subtitle')}
        </p>
      </div>

      <Filters
        minScore={minScore}
        selectedDiscipline={selectedDiscipline}
        selectedJournal={selectedJournal}
        onMinScoreChange={handleMinScoreChange}
        onDisciplineChange={handleDisciplineChange}
        onJournalChange={handleJournalChange}
      />

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6">
            {papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {papers.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-600">{t('home.noPapers')}</p>
            </div>
          )}

          {papers.length > 0 && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              totalItems={total}
              pageSize={pageSize}
              onPageChange={handlePageChange}
            />
          )}
        </>
      )}
    </Layout>
  );
}
