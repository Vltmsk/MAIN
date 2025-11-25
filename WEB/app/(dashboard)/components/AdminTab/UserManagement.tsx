"use client";

import { AdminUser } from "./types";
import { getAdminUserStatus } from "./utils/userStatus";

interface UserManagementProps {
  users: AdminUser[];
  onUserSelect: (userName: string) => void;
  onUserCreate: () => void;
  onUserDelete: (userName: string) => void;
  loading: boolean;
  formValue: string;
  onFormChange: (value: string) => void;
  message?: string;
}

export default function UserManagement({
  users,
  onUserSelect,
  onUserCreate,
  onUserDelete,
  loading,
  formValue,
  onFormChange,
  message,
}: UserManagementProps) {
  return (
    <>
      {/* Форма создания нового пользователя */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Новый пользователь</h2>

        <div className="grid gap-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-2">
              Имя пользователя
            </label>
            <input
              type="text"
              value={formValue}
              onChange={(e) => onFormChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onUserCreate();
                }
              }}
              placeholder="Введите имя пользователя"
              className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="mt-2 text-xs text-zinc-500">
              Введите имя пользователя, чтобы дать разрешение на использование сайта
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={onUserCreate}
              disabled={loading}
              className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Создание..." : "Создать пользователя"}
            </button>
            <button
              onClick={() => onFormChange("")}
              disabled={loading}
              className="px-6 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Очистить
            </button>
          </div>
        </div>
      </div>

      {/* Список пользователей */}
      <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <h2 className="text-xl font-bold text-white mb-4">
          Пользователи ({users.length})
        </h2>
        {users.length === 0 ? (
          <div className="text-zinc-600">Нет пользователей</div>
        ) : (
          <div className="space-y-2">
            {users.map((user) => {
              const statuses = getAdminUserStatus(user);
              const lowerUserName = user.user.trim().toLowerCase();
              const isSystemUser = lowerUserName === "stats" || lowerUserName === "влад";

              return (
                <div
                  key={user.user}
                  className="flex items-center justify-between p-3 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => onUserSelect(user.user)}
                      className="font-medium text-white hover:text-blue-400 transition-colors text-left"
                    >
                      {user.user}
                    </button>
                    {isSystemUser ? (
                      <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 border border-blue-500/40 rounded text-xs">
                        Системный
                      </span>
                    ) : (
                      <>
                        <span
                          className={`px-2 py-0.5 border rounded text-xs ${
                            statuses.telegramActive
                              ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                              : "bg-red-500/20 text-red-300 border-red-500/50"
                          }`}
                        >
                          Telegram: {statuses.telegramActive ? "ON" : "OFF"}
                        </span>
                        <span
                          className={`px-2 py-0.5 border rounded text-xs ${
                            statuses.settingsActive
                              ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                              : "bg-red-500/20 text-red-300 border-red-500/50"
                          }`}
                        >
                          Настройки: {statuses.settingsActive ? "ON" : "OFF"}
                        </span>
                      </>
                    )}
                  </div>
                  <button
                    onClick={() => onUserDelete(user.user)}
                    disabled={isSystemUser}
                    className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Удалить
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Уведомление */}
      {message && (
        <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50">
          <div className="p-6 rounded-xl shadow-2xl max-w-md bg-emerald-500/95 text-white border-2 border-emerald-400">
            <p className="font-semibold text-lg">{message}</p>
          </div>
        </div>
      )}
    </>
  );
}

