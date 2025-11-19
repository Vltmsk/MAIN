#!/usr/bin/env node
/**
 * Скрипт запуска Next.js сервера в production режиме
 * Явно задает порт через переменную окружения PORT
 */

// Устанавливаем порт по умолчанию, если не задан
process.env.PORT = process.env.PORT || '3000';
process.env.HOSTNAME = process.env.HOSTNAME || '0.0.0.0';

console.log(`Запуск Next.js сервера на порту ${process.env.PORT}...`);

// Запускаем standalone сервер
require('./.next/standalone/server.js');

