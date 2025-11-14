"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [allowedUsers, setAllowedUsers] = useState<string[]>([]);
  const [whitelistLoaded, setWhitelistLoaded] = useState(false);
  const [whitelistLoadError, setWhitelistLoadError] = useState("");

  useEffect(() => {
    // Проверка авторизации - если пользователь авторизован, редиректим на dashboard
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("auth_token");
      if (token) {
        router.push("/dashboard");
        return;
      }
    }

    const loadWhitelist = async () => {
      try {
        const res = await fetch("/api/auth/whitelist");
        if (!res.ok) {
          const fallback = await res.text().catch(() => "");
          throw new Error(fallback || "Не удалось получить белый список");
        }
        const data = await res.json();
        const list = Array.isArray(data.whitelist)
          ? data.whitelist
              .map((entry: { username?: string }) => entry?.username)
              .filter((username: string | undefined): username is string => Boolean(username))
          : [];
        setAllowedUsers(list);
        setWhitelistLoadError("");
      } catch (err) {
        console.error("Ошибка загрузки белого списка:", err);
        setAllowedUsers([]);
        setWhitelistLoadError("Не удалось загрузить список разрешённых логинов. Попробуйте обновить страницу или обратитесь к администратору.");
      } finally {
        setWhitelistLoaded(true);
      }
    };

    loadWhitelist();
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (!login || !password) {
        setError("Заполните все поля");
        return;
      }

      if (!whitelistLoaded) {
        setError("Список разрешённых логинов ещё загружается. Попробуйте позже.");
        return;
      }

      if (allowedUsers.length === 0) {
        setError("Вход временно недоступен. Обратитесь к администратору.");
        return;
      }

      // Проверка, что пользователь в списке разрешённых (без учёта регистра)
      const matchedUser = allowedUsers.find(
        (user) => user.toLowerCase() === login.toLowerCase()
      );

      if (!matchedUser) {
        setError("Неверный логин или пароль");
        return;
      }

      // Проверка пароля
      if (!password || password.trim().length === 0) {
        setError("Введите пароль");
        return;
      }
      
      if (password.length < 4) {
        setError("Пароль должен быть не менее 4 символов");
        return;
      }

      // Нормализуем имя пользователя - используем правильную версию из белого списка
      const normalizedLogin = matchedUser;

      const detectTimezone = () => {
        try {
          const resolved = Intl.DateTimeFormat().resolvedOptions();
          const timezone = resolved.timeZone || "UTC";
          const offsetMinutes = -new Date().getTimezoneOffset(); // Приводим к привычному знаку: положительное значение = впереди UTC
          const absoluteMinutes = Math.abs(offsetMinutes);
          const hours = Math.floor(absoluteMinutes / 60);
          const minutes = absoluteMinutes % 60;
          const sign = offsetMinutes >= 0 ? "+" : "-";
          const formattedOffset = `${sign}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
          const locale = typeof navigator !== "undefined" ? navigator.language : undefined;

          return {
            timezone,
            timezone_offset_minutes: offsetMinutes,
            timezone_offset_formatted: `UTC${formattedOffset}`,
            timezone_client_locale: locale,
          };
        } catch (tzError) {
          console.warn("Не удалось автоматически определить временную зону, используем UTC по умолчанию:", tzError);
          return {
            timezone: "UTC",
            timezone_offset_minutes: 0,
            timezone_offset_formatted: "UTC+00:00",
            timezone_client_locale: typeof navigator !== "undefined" ? navigator.language : undefined,
          };
        }
      };

      const timezonePayload = detectTimezone();

      // Пытаемся войти (проверяем пароль)
      const loginResponse = await fetch(`/api/auth/login/${encodeURIComponent(normalizedLogin)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password,
          ...timezonePayload,
        }),
      });

      const responseText = await loginResponse.text().catch(() => "");
      let responseData: any = {};
      if (responseText) {
        try {
          responseData = JSON.parse(responseText);
        } catch {
          responseData = {};
        }
      }

      if (!loginResponse.ok) {
        const errorMessage = responseData.detail || responseData.error || responseText || "Ошибка входа";
        if (loginResponse.status === 401 || loginResponse.status === 400) {
          setError(errorMessage || "Неверный логин или пароль");
        } else {
          setError(errorMessage);
        }
        return;
      }

      const storedLogin = responseData.user || normalizedLogin;

      // Успешный вход - сохраняем токен и логин
      if (typeof window !== "undefined") {
        localStorage.setItem("auth_token", "demo_token");
        localStorage.setItem("user_login", storedLogin);
      }

      // Перенаправление на dashboard
      router.push("/dashboard");
    } catch (err) {
      console.error("Ошибка при входе:", err);
      setError("Ошибка входа. Попробуйте ещё раз.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md animate-scale-in">
        {/* Карточка с формой */}
        <div className="glass-strong rounded-2xl p-4 md:p-8 shadow-2xl card-hover gradient-border relative">
          {/* Логотип */}
          <div className="flex justify-center mb-6 animate-float">
            <div className="w-16 h-16 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl flex items-center justify-center shadow-emerald hover-glow">
              <svg
                className="w-8 h-8 text-white"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
          </div>

          {/* Заголовок */}
          <h1 className="text-2xl md:text-3xl font-bold gradient-text text-center mb-2">
            Exchange Monitor
          </h1>
          <p className="text-zinc-400 text-center text-sm mb-8">
            Мониторинг криптовалютных бирж в реальном времени
          </p>

          {/* Форма */}
          <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
            {whitelistLoadError && (
              <div className="bg-amber-500/20 border border-amber-500/50 text-amber-300 px-4 py-3 rounded-lg text-sm animate-fade-in relative z-10">
                {whitelistLoadError}
              </div>
            )}
            {error && (
              <div className="bg-red-500/20 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg text-sm animate-fade-in relative z-10">
                {error}
              </div>
            )}

            <div className="animate-slide-in relative z-10">
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Логин
              </label>
              <input
                type="text"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                placeholder="Введите ваш логин"
                className="w-full px-4 py-3 glass border border-zinc-600/50 rounded-lg text-white placeholder-zinc-500 input-focus smooth-transition relative z-10"
                required
                autoFocus
              />
            </div>

            <div className="animate-slide-in relative z-10" style={{ animationDelay: '0.1s' }}>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Пароль
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-4 py-3 glass border border-zinc-600/50 rounded-lg text-white placeholder-zinc-500 input-focus smooth-transition relative z-10"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-semibold py-3 px-4 rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:transform-none"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Загрузка...
                </span>
              ) : "Войти"}
            </button>
          </form>
        </div>

        {/* Ссылка на регистрацию */}
        <div className="mt-6 text-center animate-fade-in">
          <p className="text-sm text-zinc-500">
            Нет аккаунта?{" "}
            <a
              href="/register"
              className="text-emerald-500 hover:text-emerald-400 underline smooth-transition hover-glow"
            >
              Зарегистрироваться
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
