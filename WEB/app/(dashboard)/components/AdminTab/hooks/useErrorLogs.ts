"use client";

import { useState, useCallback } from "react";
import { ErrorLog } from "../types";

export function useErrorLogs(userLogin: string, isAdmin: boolean) {
  const [errorLogs, setErrorLogs] = useState<ErrorLog[]>([]);
  const [errorLogsLoading, setErrorLogsLoading] = useState(false);
  const [errorLogsFilter, setErrorLogsFilter] = useState<{
    exchange?: string;
    error_type?: string;
    limit: number;
  }>({ limit: 100 });

  // Загрузка логов ошибок
  const fetchErrorLogs = useCallback(async () => {
    setErrorLogsLoading(true);
    try {
      const params = new URLSearchParams();
      if (errorLogsFilter.exchange) {
        params.append("exchange", errorLogsFilter.exchange);
      }
      if (errorLogsFilter.error_type) {
        params.append("error_type", errorLogsFilter.error_type);
      }
      params.append("limit", errorLogsFilter.limit.toString());

      const res = await fetch(`/api/errors?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setErrorLogs(data.errors || []);
      } else {
        throw new Error("Ошибка загрузки логов");
      }
    } catch (err) {
      console.error("Ошибка загрузки логов:", err);
      setErrorLogs([]);
    } finally {
      setErrorLogsLoading(false);
    }
  }, [errorLogsFilter]);

  // Удаление одного лога ошибки
  const deleteError = useCallback(async (errorId: number, onSuccess?: () => void) => {
    if (!isAdmin) {
      alert("Удаление логов ошибок доступно только для пользователя 'Влад'");
      return;
    }

    if (!confirm("Вы уверены, что хотите удалить этот лог ошибки?")) {
      return;
    }

    try {
      const params = new URLSearchParams();
      params.append("error_id", errorId.toString());
      params.append("user", userLogin);

      const res = await fetch(`/api/errors?${params.toString()}`, {
        method: "DELETE",
      });

      if (res.ok) {
        if (onSuccess) {
          onSuccess();
        } else {
          fetchErrorLogs();
        }
      } else {
        const data = await res.json();
        alert(data.error || "Ошибка при удалении лога");
      }
    } catch (err) {
      console.error("Ошибка удаления лога:", err);
      alert("Ошибка при удалении лога");
    }
  }, [userLogin, isAdmin, fetchErrorLogs]);

  // Удаление всех логов ошибок
  const deleteAllErrors = useCallback(async (onSuccess?: () => void) => {
    if (!isAdmin) {
      alert("Удаление всех логов ошибок доступно только для пользователя 'Влад'");
      return;
    }

    if (!confirm("Вы уверены, что хотите удалить ВСЕ логи ошибок? Это действие нельзя отменить.")) {
      return;
    }

    try {
      const params = new URLSearchParams();
      params.append("user", userLogin);

      const res = await fetch(`/api/errors?${params.toString()}`, {
        method: "DELETE",
      });

      if (res.ok) {
        const data = await res.json();
        alert(`Успешно удалено ${data.deleted_count || 0} логов ошибок`);
        if (onSuccess) {
          onSuccess();
        } else {
          fetchErrorLogs();
        }
      } else {
        const data = await res.json();
        alert(data.error || "Ошибка при удалении логов");
      }
    } catch (err) {
      console.error("Ошибка удаления всех логов:", err);
      alert("Ошибка при удалении логов");
    }
  }, [userLogin, isAdmin, fetchErrorLogs]);

  return {
    errorLogs,
    errorLogsLoading,
    errorLogsFilter,
    setErrorLogsFilter,
    fetchErrorLogs,
    deleteError,
    deleteAllErrors,
  };
}

