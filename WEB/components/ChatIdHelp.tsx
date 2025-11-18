"use client";

import { useState } from "react";

interface ChatIdHelpProps {
  variant?: "default" | "compact";
  showBotTokenWarning?: boolean;
  forBotToken?: boolean; // Новый проп для отображения инструкции для bot token
}

export default function ChatIdHelp({ variant = "default", showBotTokenWarning = false, forBotToken = false }: ChatIdHelpProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (variant === "compact") {
    if (forBotToken) {
      return null; // Для bot token не показываем compact версию
    }
    return (
      <div className="mt-1">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs text-emerald-400 hover:text-emerald-300 underline transition-colors"
        >
          {isExpanded ? "Скрыть инструкцию" : "Как получить Chat ID?"}
        </button>
        {isExpanded && (
          <div className="mt-2 p-3 bg-zinc-800/50 border border-zinc-700 rounded-lg text-xs text-zinc-300">
            <div className="space-y-2">
              <p className="font-medium text-white mb-2">📋 Быстрая инструкция:</p>
              <ol className="list-decimal list-inside space-y-1 ml-2">
                <li>Добавьте бота <a href="tg://resolve?domain=getmyid_bot" className="text-emerald-400 hover:text-emerald-300 underline">@getmyid_bot</a> в группу/канал</li>
                <li>Для каналов: дайте боту права администратора</li>
                <li>Скопируйте <strong>"Current chat ID"</strong> из сообщения бота</li>
                <li>Вставьте в поле выше</li>
              </ol>
              <p className="text-zinc-400 mt-2 text-xs">
                💡 Для групп используйте "Current chat ID" (отрицательное число), для личных чатов — "Your ID" (положительное)
              </p>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-sm text-emerald-400 hover:text-emerald-300 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {isExpanded ? "Скрыть инструкцию" : (forBotToken ? "Как получить bot token?" : "Как получить Chat ID?")}
        <svg 
          className={`w-4 h-4 transition-transform ${isExpanded ? "rotate-180" : ""}`} 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isExpanded && !forBotToken && (
        <div className="mt-3 p-4 bg-zinc-800/50 border border-zinc-700 rounded-lg space-y-4">
          {/* Основной способ для групп и каналов */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <span>📋</span> Пошаговая инструкция (для групп и каналов):
            </h4>
            <ol className="space-y-3 text-sm text-zinc-300">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">1</span>
                <div>
                  <p className="font-medium text-white mb-1">Добавьте бота в группу/канал</p>
                  <p className="text-zinc-400">
                    Откройте Telegram и найдите бота{" "}
                    <a 
                      href="tg://resolve?domain=getmyid_bot" 
                      className="text-emerald-400 hover:text-emerald-300 underline font-medium"
                    >
                      @getmyid_bot
                    </a>
                    . Добавьте бота в группу или канал, куда вы хотите получать уведомления о детектах.
                  </p>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">2</span>
                <div>
                  <p className="font-medium text-white mb-1">Настройте права бота (для каналов)</p>
                  <div className="text-zinc-400 space-y-1">
                    <p className="flex items-start gap-2">
                      <span className="text-yellow-400">⚠️</span>
                      <span><strong className="text-yellow-400">Важно для каналов:</strong> Если вы добавляете бота в канал, ему нужны права администратора для отправки сообщений</span>
                    </p>
                    <p>Перейдите в настройки канала → "Администраторы" → найдите бота @getmyid_bot</p>
                    <p>Дайте боту права администратора (или хотя бы право на отправку сообщений)</p>
                    <p className="text-zinc-500">Без этих прав бот не сможет отправить сообщение с Chat ID</p>
                  </div>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">3</span>
                <div>
                  <p className="font-medium text-white mb-1">Получите Chat ID автоматически</p>
                  <p className="text-zinc-400 mb-2">
                    Бот автоматически отправит сообщение сразу после добавления (если у него есть права).
                    Если сообщение не пришло — проверьте права бота в настройках канала.
                  </p>
                  <div className="bg-zinc-900 border border-zinc-700 rounded p-3 font-mono text-xs text-zinc-300">
                    <div>Your ID: 2065581586</div>
                    <div className="text-emerald-400 font-semibold">Current chat ID: -1003763476778</div>
                  </div>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">4</span>
                <div>
                  <p className="font-medium text-white mb-1">Скопируйте Chat ID</p>
                  <p className="text-zinc-400">
                    Найдите строку <strong className="text-emerald-400">"Current chat ID"</strong> в сообщении бота.
                    Скопируйте число (например: <code className="bg-zinc-900 px-1 rounded">-1003763476778</code>).
                    Это и есть ваш Chat ID для группы/канала.
                  </p>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">5</span>
                <div>
                  <p className="font-medium text-white mb-1">Вставьте в поле</p>
                  <p className="text-zinc-400">
                    Вставьте скопированное число в поле "Chat ID" выше и сохраните настройки.
                  </p>
                </div>
              </li>
            </ol>
          </div>

          {/* Альтернативный способ для личного чата */}
          <div className="pt-3 border-t border-zinc-700">
            <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <span>💬</span> Альтернативный способ (для личного чата):
            </h4>
            <ol className="space-y-2 text-sm text-zinc-300">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-xs">1</span>
                <div>
                  <p className="font-medium text-white mb-1">Напишите боту в личку</p>
                  <p className="text-zinc-400">
                    Откройте Telegram и найдите бота{" "}
                    <a 
                      href="tg://resolve?domain=getmyid_bot" 
                      className="text-emerald-400 hover:text-emerald-300 underline font-medium"
                    >
                      @getmyid_bot
                    </a>
                    . Напишите боту любое сообщение или отправьте <code className="bg-zinc-900 px-1 rounded">/start</code>.
                  </p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-xs">2</span>
                <div>
                  <p className="font-medium text-white mb-1">Получите ваш ID</p>
                  <p className="text-zinc-400">
                    Бот автоматически отправит вам сообщение с вашим ID.
                    Используйте значение из строки <strong className="text-emerald-400">"Your ID"</strong> (положительное число).
                  </p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-xs">3</span>
                <div>
                  <p className="font-medium text-white mb-1">Вставьте в поле</p>
                  <p className="text-zinc-400">
                    Скопируйте число и вставьте в поле "Chat ID" выше.
                  </p>
                </div>
              </li>
            </ol>
          </div>

          {/* Важные примечания */}
          <div className="pt-3 border-t border-zinc-700">
            <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
              <span>💡</span> Важные примечания:
            </h4>
            <ul className="space-y-2 text-sm text-zinc-300">
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">✓</span>
                <span><strong className="text-white">Chat ID для групп/каналов</strong> — отрицательное число (например: <code className="bg-zinc-900 px-1 rounded">-1003763476778</code>)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">✓</span>
                <span><strong className="text-white">Chat ID для личных чатов</strong> — положительное число (например: <code className="bg-zinc-900 px-1 rounded">2065581586</code>)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">✓</span>
                <span>Формат: от 8 до 20 цифр</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-yellow-400 mt-0.5">⚠️</span>
                <span>Не путайте "Your ID" и "Current chat ID" — для групп используйте "Current chat ID"</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-yellow-400 mt-0.5">⚠️</span>
                <span>Не путайте Chat ID с Username (username начинается с @)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-yellow-400 mt-0.5">⚠️</span>
                <span><strong>Проблема с каналами:</strong> Если бот не отправил сообщение после добавления в канал, проверьте его права:
                  <ul className="list-disc list-inside ml-4 mt-1 space-y-1 text-zinc-400">
                    <li>Перейдите в настройки канала → "Администраторы"</li>
                    <li>Найдите бота @getmyid_bot и дайте ему права администратора</li>
                    <li>Или хотя бы включите право "Отправлять сообщения"</li>
                    <li>После этого бот сможет отправить Chat ID</li>
                  </ul>
                </span>
              </li>
            </ul>
          </div>

          {/* Кнопка быстрого доступа */}
          <div className="pt-3 border-t border-zinc-700">
            <a
              href="tg://resolve?domain=getmyid_bot"
              className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg transition-colors"
            >
              <span className="text-lg">📱</span>
              Открыть @getmyid_bot в Telegram
            </a>
          </div>
        </div>
      )}

      {isExpanded && forBotToken && (
        <div className="mt-3 p-4 bg-zinc-800/50 border border-zinc-700 rounded-lg space-y-4">
          {/* Инструкция для получения bot token */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <span>🤖</span> Как получить Bot Token:
            </h4>
            <ol className="space-y-3 text-sm text-zinc-300">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">1</span>
                <div>
                  <p className="font-medium text-white mb-1">Откройте @BotFather в Telegram</p>
                  <p className="text-zinc-400">
                    Найдите бота{" "}
                    <a 
                      href="tg://resolve?domain=BotFather" 
                      className="text-emerald-400 hover:text-emerald-300 underline font-medium"
                    >
                      @BotFather
                    </a>
                    {" "}в Telegram и начните с ним диалог.
                  </p>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">2</span>
                <div>
                  <p className="font-medium text-white mb-1">Создайте нового бота</p>
                  <p className="text-zinc-400">
                    Отправьте команду <code className="bg-zinc-900 px-1 rounded">/newbot</code> и следуйте инструкциям бота.
                    Придумайте имя и username для вашего бота.
                  </p>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">3</span>
                <div>
                  <p className="font-medium text-white mb-1">Получите Bot Token</p>
                  <p className="text-zinc-400 mb-2">
                    После создания бота @BotFather отправит вам сообщение с Bot Token.
                    Это строка вида: <code className="bg-zinc-900 px-1 rounded">1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz</code>
                  </p>
                  <div className="bg-zinc-900 border border-zinc-700 rounded p-3 font-mono text-xs text-zinc-300">
                    <div className="text-emerald-400 font-semibold">Use this token to access the HTTP API:</div>
                    <div className="mt-1">1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz</div>
                  </div>
                </div>
              </li>
              
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-emerald-600 rounded-full flex items-center justify-center text-white font-bold text-xs">4</span>
                <div>
                  <p className="font-medium text-white mb-1">Скопируйте и вставьте Token</p>
                  <p className="text-zinc-400">
                    Скопируйте весь Bot Token (включая число и двоеточие) и вставьте в поле "Bot Token" выше.
                  </p>
                </div>
              </li>
            </ol>
          </div>

          {/* Важные примечания для bot token */}
          <div className="pt-3 border-t border-zinc-700">
            <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
              <span>💡</span> Важные примечания:
            </h4>
            <ul className="space-y-2 text-sm text-zinc-300">
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">✓</span>
                <span>Формат Bot Token: <code className="bg-zinc-900 px-1 rounded">число:буквы</code> (например: <code className="bg-zinc-900 px-1 rounded">1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz</code>)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-yellow-400 mt-0.5">⚠️</span>
                <span><strong>Безопасность:</strong> Не делитесь Bot Token с другими людьми. Тот, кто имеет доступ к токену, может управлять вашим ботом.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-yellow-400 mt-0.5">⚠️</span>
                <span><strong>Рекомендация:</strong> Создайте отдельного бота специально для этого сервиса. Не используйте бота, который уже используется для других целей.</span>
              </li>
            </ul>
          </div>

          {/* Кнопка быстрого доступа */}
          <div className="pt-3 border-t border-zinc-700">
            <a
              href="tg://resolve?domain=BotFather"
              className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg transition-colors"
            >
              <span className="text-lg">🤖</span>
              Открыть @BotFather в Telegram
            </a>
          </div>
        </div>
      )}

      {showBotTokenWarning && (
        <div className="mt-3 p-3 bg-yellow-900/20 border border-yellow-700/50 rounded-lg">
          <div className="flex items-start gap-2">
            <span className="text-yellow-400 text-lg">⚠️</span>
            <div className="flex-1 text-sm">
              <p className="font-semibold text-yellow-400 mb-1">Важно:</p>
              <p className="text-zinc-300">
                Создайте отдельного бота через{" "}
                <a 
                  href="tg://resolve?domain=BotFather" 
                  className="text-emerald-400 hover:text-emerald-300 underline font-medium"
                >
                  @BotFather
                </a>
                {" "}и используйте его <strong>только для получения сигналов с этого сайта</strong>. 
                Не используйте этого бота для других целей.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

