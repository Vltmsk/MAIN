"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessMessage("");
    setLoading(true);

    try {
      if (!login || !password || !confirmPassword) {
        setError("Заполните все поля");
        return;
      }

      // Проверка пароля
      if (password.length < 4) {
        setError("Пароль должен быть не менее 4 символов");
        return;
      }

      if (password !== confirmPassword) {
        setError("Пароли не совпадают");
        return;
      }

      // Используем введённый логин (сервер сам проверит существование пользователя в БД)
      const normalizedLogin = login.trim();

      // Регистрация пользователя
      const response = await fetch(`/api/auth/register/${encodeURIComponent(normalizedLogin)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password,
          tg_token: "",
          chat_id: "",
          options_json: JSON.stringify({
            exchanges: { gate: false, binance: false, bitget: false, bybit: false, hyperliquid: false },
            pairSettings: {},
          }),
        }),
      });

      const responseText = await response.text().catch(() => "");
      let responseData: any = {};
      if (responseText) {
        try {
          responseData = JSON.parse(responseText);
        } catch {
          responseData = {};
        }
      }

      if (!response.ok) {
        const errorMessage =
          responseData.detail || responseData.error || responseText || "Ошибка регистрации";
        setError(errorMessage);
        return;
      }

      const storedLogin = (responseData.user || normalizedLogin) as string;
      
      // Сохраняем токен и логин в localStorage
      if (typeof window !== "undefined") {
        localStorage.setItem("auth_token", "demo_token");
        localStorage.setItem("user_login", storedLogin);
      }

      // Специальное поздравительное сообщение для пользователя Valera
      if (storedLogin.trim().toLowerCase() === "valera") {
        const message =
          "Молодец чемпион! Ты смог войти на сайт, это маленькая, но победа! Если ты смог зайти на сайт, ты сможешь всё в этой жизни!";
        setSuccessMessage(message);

        // Показываем сообщение 10 секунд, затем перенаправляем на dashboard
        setTimeout(() => {
          router.push("/dashboard");
        }, 10000);
        return;
      }

      // Для всех остальных пользователей сразу переходим на dashboard
      router.push("/dashboard");
    } catch (err) {
      setError("Ошибка регистрации. Попробуйте ещё раз.");
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
                <path d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            </div>
          </div>

          {/* Заголовок */}
          <h1 className="text-2xl md:text-3xl font-bold gradient-text text-center mb-2">
            Регистрация
          </h1>
          <p className="text-zinc-400 text-center text-sm mb-8">
            Создайте новый аккаунт для мониторинга бирж
          </p>

          {/* Форма */}
          <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
            {error && (
              <div className="bg-red-500/20 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg text-sm animate-fade-in relative z-10">
                {error}
              </div>
            )}

            {successMessage && (
              <div className="bg-emerald-500/15 border border-emerald-500/60 text-emerald-300 px-4 py-3 rounded-lg text-sm animate-fade-in relative z-10">
                {successMessage}
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

            <div className="animate-slide-in relative z-10" style={{ animationDelay: '0.2s' }}>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Подтвердите пароль
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
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
                  Регистрация...
                </span>
              ) : "Зарегистрироваться"}
            </button>
          </form>

          {/* Ссылка на вход */}
          <div className="mt-6 text-center animate-fade-in">
            <p className="text-sm text-zinc-500">
              Уже есть аккаунт?{" "}
              <a
                href="/login"
                className="text-emerald-500 hover:text-emerald-400 underline smooth-transition hover-glow"
              >
                Войти
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

