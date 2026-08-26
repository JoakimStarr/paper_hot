'use client';

import type { Dispatch, SetStateAction } from 'react';
import { SettingsInfo } from '@/types/paper';
import ApiConfigPanel, { NewProviderInput } from './ApiConfigPanel';
import ModelConfigPanel, { TestResult } from './ModelConfigPanel';
import ModelPriorityPanel from './ModelPriorityPanel';

interface ModelConfigTabProps {
  settingsInfo: SettingsInfo | null;
  apiKeys: Record<string, string>;
  apiMessage: Record<string, string>;
  updatingKey: string | null;
  onUpdateApiKey: (provider: string) => void;
  setApiKeys: Dispatch<SetStateAction<Record<string, string>>>;
  newProvider: NewProviderInput;
  setNewProvider: Dispatch<SetStateAction<NewProviderInput>>;
  editingProviderName: string | null;
  savingCustomProvider: boolean;
  customProviderMessage: string;
  onEditCustomProvider: (name: string) => void;
  onCancelEditProvider: () => void;
  onSaveCustomProvider: () => void;
  onDeleteCustomProvider: (name: string) => void;
  ports: { backend: number; frontend: number };
  setPorts: Dispatch<SetStateAction<{ backend: number; frontend: number }>>;
  savingPorts: boolean;
  portMessage: string;
  onUpdatePorts: () => void;
  modelList: SettingsInfo['models'];
  savingModels: boolean;
  modelMessage: string;
  onSaveModelPriority: () => void;
  onMoveModel: (index: number, direction: 'up' | 'down') => void;
  defaultModel: string | null;
  savingDefaultModel: boolean;
  defaultModelMessage: string;
  embeddingModel: string | null;
  embeddingModelDraft: string;
  setEmbeddingModelDraft: Dispatch<SetStateAction<string>>;
  savingEmbeddingModel: boolean;
  embeddingModelMessage: string;
  onSaveEmbeddingModel: () => void;
  onClearDefaultModel: () => void;
  onSetDefaultModel: (model: string) => void;
  testingModel: string;
  testResults: Record<string, TestResult>;
  onTestModelLink: (model: string) => void;
  fetchingModels: boolean;
  onFetchModels: () => void;
}

export default function ModelConfigTab({
  settingsInfo,
  apiKeys,
  apiMessage,
  updatingKey,
  onUpdateApiKey,
  setApiKeys,
  newProvider,
  setNewProvider,
  editingProviderName,
  savingCustomProvider,
  customProviderMessage,
  onEditCustomProvider,
  onCancelEditProvider,
  onSaveCustomProvider,
  onDeleteCustomProvider,
  ports,
  setPorts,
  savingPorts,
  portMessage,
  onUpdatePorts,
  modelList,
  savingModels,
  modelMessage,
  onSaveModelPriority,
  onMoveModel,
  defaultModel,
  savingDefaultModel,
  defaultModelMessage,
  embeddingModel,
  embeddingModelDraft,
  setEmbeddingModelDraft,
  savingEmbeddingModel,
  embeddingModelMessage,
  onSaveEmbeddingModel,
  onClearDefaultModel,
  onSetDefaultModel,
  testingModel,
  testResults,
  onTestModelLink,
  fetchingModels,
  onFetchModels,
}: ModelConfigTabProps) {
  return (
    <>
      <ApiConfigPanel
        settingsInfo={settingsInfo}
        apiKeys={apiKeys}
        apiMessage={apiMessage}
        updatingKey={updatingKey}
        onUpdateApiKey={onUpdateApiKey}
        setApiKeys={setApiKeys}
        newProvider={newProvider}
        setNewProvider={setNewProvider}
        editingProviderName={editingProviderName}
        savingCustomProvider={savingCustomProvider}
        customProviderMessage={customProviderMessage}
        onEditCustomProvider={onEditCustomProvider}
        onCancelEditProvider={onCancelEditProvider}
        onSaveCustomProvider={onSaveCustomProvider}
        onDeleteCustomProvider={onDeleteCustomProvider}
        ports={ports}
        setPorts={setPorts}
        savingPorts={savingPorts}
        portMessage={portMessage}
        onUpdatePorts={onUpdatePorts}
        fetchingModels={fetchingModels}
        onFetchModels={onFetchModels}
      />
      <ModelConfigPanel
        defaultModel={defaultModel}
        savingDefaultModel={savingDefaultModel}
        defaultModelMessage={defaultModelMessage}
        embeddingModel={embeddingModel}
        embeddingModelDraft={embeddingModelDraft}
        setEmbeddingModelDraft={setEmbeddingModelDraft}
        savingEmbeddingModel={savingEmbeddingModel}
        embeddingModelMessage={embeddingModelMessage}
        modelList={modelList}
        testResults={testResults}
        testingModel={testingModel}
        onSaveEmbeddingModel={onSaveEmbeddingModel}
        onClearDefaultModel={onClearDefaultModel}
        onSetDefaultModel={onSetDefaultModel}
        onTestModelLink={onTestModelLink}
      />
      <ModelPriorityPanel
        modelList={modelList}
        savingModels={savingModels}
        modelMessage={modelMessage}
        settingsInfo={settingsInfo}
        onSaveModelPriority={onSaveModelPriority}
        onMoveModel={onMoveModel}
      />
    </>
  );
}