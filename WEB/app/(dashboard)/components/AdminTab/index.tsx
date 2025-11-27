"use client";

import { useEffect } from "react";
import MetricsAdminTab from "../MetricsAdminTab";
import { useAdminUsers } from "./hooks/useAdminUsers";
import { useErrorLogs } from "./hooks/useErrorLogs";
import UserManagement from "./UserManagement";
import UserSettingsEditor from "./UserSettingsEditor";
import ErrorLogsPanel from "./ErrorLogsPanel";
import { AdminTabProps } from "./types";

export default function AdminTab({ userLogin, isAdmin, activeTab }: AdminTabProps) {
  const adminUsersHook = useAdminUsers();
  const errorLogsHook = useErrorLogs(userLogin, isAdmin);

  // Загрузка пользователей админ панели при переключении на вкладку
  useEffect(() => {
    if (activeTab === "admin" && isAdmin) {
      adminUsersHook.fetchAdminUsers();
      errorLogsHook.fetchErrorLogs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, isAdmin]);

  // Обновление логов при изменении фильтров
  useEffect(() => {
    if (activeTab === "admin" && isAdmin) {
      const timer = setTimeout(() => {
        errorLogsHook.fetchErrorLogs();
      }, 300); // Небольшая задержка для дебаунса
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errorLogsHook.errorLogsFilter.exchange, errorLogsHook.errorLogsFilter.error_type, errorLogsHook.errorLogsFilter.limit, activeTab, isAdmin]);

  return (
    <div className="mb-6 md:mb-8">
      {/* Заголовок и кнопка удаления статистики */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Админ панель</h1>
          <p className="text-zinc-400">Управление пользователями системы</p>
        </div>
        {/* Кнопка удаления рыночной статистики */}
        <button
          onClick={adminUsersHook.deleteGlobalStats}
          disabled={adminUsersHook.deletingGlobalStats}
          className={`px-6 py-3 rounded-lg text-sm font-medium transition-colors ${
            adminUsersHook.deletingGlobalStats
              ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
              : "bg-red-600 hover:bg-red-700 text-white"
          }`}
          title="Удалить всю рыночную статистику стрел (пользователь 'Stats')"
        >
          {adminUsersHook.deletingGlobalStats ? (
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin"></span>
              Удаление...
            </span>
          ) : (
            "🗑️ Удалить рыночную статистику"
          )}
        </button>
      </div>

      {/* Управление пользователями */}
      <UserManagement
        users={adminUsersHook.adminUsers}
        onUserSelect={adminUsersHook.loadUserSettings}
        onUserCreate={adminUsersHook.createAdminUser}
        onUserDelete={adminUsersHook.deleteAdminUser}
        loading={adminUsersHook.adminLoading}
        formValue={adminUsersHook.adminForm}
        onFormChange={adminUsersHook.setAdminForm}
        message={adminUsersHook.adminMsg}
      />

      {/* Панель настроек выбранного пользователя */}
      {adminUsersHook.selectedUserSettings && (
        <UserSettingsEditor
          userSettings={adminUsersHook.selectedUserSettings}
          onSave={adminUsersHook.saveAdminUserSettings}
          onClose={() => adminUsersHook.setSelectedUserSettings(null)}
          loading={adminUsersHook.adminLoading}
          exchangeFilters={adminUsersHook.adminExchangeFilters}
          pairSettings={adminUsersHook.adminPairSettings}
          onExchangeFiltersChange={adminUsersHook.setAdminExchangeFilters}
          onPairSettingsChange={adminUsersHook.setAdminPairSettings}
          expandedExchanges={adminUsersHook.adminExpandedExchanges}
          onExpandedExchangesChange={adminUsersHook.setAdminExpandedExchanges}
          onUserSettingsChange={adminUsersHook.setSelectedUserSettings}
        />
      )}

      {/* Управление метриками производительности */}
      <MetricsAdminTab isAdmin={isAdmin} />

      {/* Блок Логов */}
      <ErrorLogsPanel
        errorLogs={errorLogsHook.errorLogs}
        loading={errorLogsHook.errorLogsLoading}
        filter={errorLogsHook.errorLogsFilter}
        onFilterChange={errorLogsHook.setErrorLogsFilter}
        onRefresh={errorLogsHook.fetchErrorLogs}
        onDelete={(errorId) => errorLogsHook.deleteError(errorId, errorLogsHook.fetchErrorLogs)}
        onDeleteAll={() => errorLogsHook.deleteAllErrors(errorLogsHook.fetchErrorLogs)}
        isAdmin={isAdmin}
      />
    </div>
  );
}

