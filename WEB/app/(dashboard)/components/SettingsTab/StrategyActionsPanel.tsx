"use client";

interface StrategyActionsPanelProps {
  conditionalTemplates: any[];
  selectedStrategies: Set<number>;
  selectedStrategyIndex: number | null;
  hasUnsavedChanges: boolean;
  saving: boolean;
  onTemplatesChange: (templates: any[]) => void;
  onSave: () => Promise<void>;
  onAddStrategy: () => void;
  onDeleteStrategy: (index: number) => void;
  onClose: () => void;
  setHasUnsavedChanges: (value: boolean) => void;
  setSaveMessage: (message: { type: "success" | "error"; text: string } | null) => void;
}

export default function StrategyActionsPanel({
  conditionalTemplates,
  selectedStrategies,
  selectedStrategyIndex,
  hasUnsavedChanges,
  saving,
  onTemplatesChange,
  onSave,
  onAddStrategy,
  onDeleteStrategy,
  onClose,
  setHasUnsavedChanges,
  setSaveMessage,
}: StrategyActionsPanelProps) {
  return (
    <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl p-4 overflow-y-auto">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-1 gap-3">
        <button
          onClick={async () => {
            if (confirm("Остановить все активные стратегии?")) {
              const newTemplates = conditionalTemplates.map((s) => ({
                ...s,
                enabled: false,
              }));
              onTemplatesChange(newTemplates);
              try {
                await onSave();
                setHasUnsavedChanges(false);
                setSaveMessage({
                  type: "success",
                  text: "Все стратегии остановлены и сохранены в БД"
                });
              } catch (error) {
                setHasUnsavedChanges(true);
                setSaveMessage({
                  type: "error",
                  text: error instanceof Error ? error.message : "Ошибка при сохранении изменений"
                });
              }
            }
          }}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-white font-medium transition-colors col-span-2 md:col-span-1 lg:col-span-1"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
          </svg>
          Стоп все
        </button>

        <button
          onClick={async () => {
            if (selectedStrategies.size === 0) {
              alert("Выберите стратегии для запуска");
              return;
            }
            const newTemplates = [...conditionalTemplates];
            selectedStrategies.forEach((index) => {
              if (newTemplates[index]) {
                newTemplates[index].enabled = true;
              }
            });
            onTemplatesChange(newTemplates);
            try {
              await onSave();
              setHasUnsavedChanges(false);
              setSaveMessage({
                type: "success",
                text: `${selectedStrategies.size} стратегий запущено и сохранено в БД`
              });
            } catch (error) {
              setHasUnsavedChanges(true);
              setSaveMessage({
                type: "error",
                text: error instanceof Error ? error.message : "Ошибка при сохранении изменений"
              });
            }
          }}
          disabled={selectedStrategies.size === 0}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors col-span-2 md:col-span-1 lg:col-span-1"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Старт отмеченные {selectedStrategies.size > 0 && `(${selectedStrategies.size})`}
        </button>

        <button
          onClick={async () => {
            if (selectedStrategies.size === 0) {
              alert("Выберите стратегии для остановки");
              return;
            }
            if (confirm(`Остановить ${selectedStrategies.size} выбранную(ых) стратегию(и)?`)) {
              const newTemplates = [...conditionalTemplates];
              selectedStrategies.forEach((index) => {
                if (newTemplates[index]) {
                  newTemplates[index].enabled = false;
                }
              });
              onTemplatesChange(newTemplates);
              try {
                await onSave();
                setHasUnsavedChanges(false);
                setSaveMessage({
                  type: "success",
                  text: `${selectedStrategies.size} стратегий остановлено и сохранено в БД`
                });
              } catch (error) {
                setHasUnsavedChanges(true);
                setSaveMessage({
                  type: "error",
                  text: error instanceof Error ? error.message : "Ошибка при сохранении изменений"
                });
              }
            }
          }}
          disabled={selectedStrategies.size === 0}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors col-span-2 md:col-span-1 lg:col-span-1"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
          </svg>
          Стоп отмеченные {selectedStrategies.size > 0 && `(${selectedStrategies.size})`}
        </button>

        <button
          onClick={onAddStrategy}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-white font-medium transition-colors col-span-2 md:col-span-1 lg:col-span-1"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Добавить новую
        </button>

        <button
          onClick={async () => {
            // Валидация: проверяем, что выбрана стратегия и у неё есть название
            if (selectedStrategyIndex === null) {
              setSaveMessage({
                type: "error",
                text: "Выберите стратегию для сохранения"
              });
              return;
            }
            
            const selectedStrategy = conditionalTemplates[selectedStrategyIndex];
            if (!selectedStrategy || !selectedStrategy.name || selectedStrategy.name.trim() === "") {
              setSaveMessage({
                type: "error",
                text: "Необходимо указать название стратегии перед сохранением"
              });
              return;
            }
            
            try {
              await onSave();
              setHasUnsavedChanges(false);
              // Уведомление об успешном сохранении будет показано из родительского компонента
              // через систему уведомлений useSettings
            } catch (error) {
              // Ошибка будет обработана в onSave, но на всякий случай показываем уведомление
              setSaveMessage({
                type: "error",
                text: error instanceof Error ? error.message : "Ошибка при сохранении стратегии"
              });
            }
          }}
          disabled={saving || selectedStrategyIndex === null}
          className={`w-full flex items-center justify-center gap-2 px-4 py-3 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-all col-span-2 md:col-span-1 lg:col-span-1 ${
            hasUnsavedChanges
              ? "bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 shadow-lg shadow-emerald-500/50 animate-pulse"
              : "bg-zinc-700 hover:bg-zinc-600"
          }`}
          title={selectedStrategyIndex === null ? "Выберите стратегию для сохранения" : hasUnsavedChanges ? "⚠️ Есть несохраненные изменения!" : "Сохранить изменения в выбранной стратегии"}
        >
          {saving ? (
            <>
              <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Сохранение...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
              </svg>
              Сохранить
            </>
          )}
        </button>

        <button
          onClick={() => {
            if (selectedStrategyIndex === null) {
              alert("Выберите стратегию для удаления");
              return;
            }
            onDeleteStrategy(selectedStrategyIndex);
          }}
          disabled={selectedStrategyIndex === null}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors col-span-2 md:col-span-1 lg:col-span-1"
          title={selectedStrategyIndex === null ? "Выберите стратегию для удаления" : "Удалить выбранную стратегию"}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          Удалить стратегию
        </button>

        <button
          onClick={() => {
            if (hasUnsavedChanges) {
              const confirmed = confirm("Есть несохраненные изменения. Закрыть без сохранения?");
              if (!confirmed) {
                return;
              }
            }
            onClose();
          }}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-white font-medium transition-colors col-span-2 md:col-span-1 lg:col-span-1"
          title={hasUnsavedChanges ? "Есть несохраненные изменения" : "Закрыть выбранную стратегию"}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
          Закрыть
        </button>
      </div>
    </div>
  );
}

