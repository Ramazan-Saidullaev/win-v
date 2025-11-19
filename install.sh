#!/bin/bash
# Скрипт для установки всех зависимостей приложения истории буфера обмена

echo "=== Установка приложения истории буфера обмена ==="
echo ""

# Проверка, что мы в правильной директории
if [ ! -f "clipboard_history.py" ]; then
    echo "Ошибка: файл clipboard_history.py не найден!"
    echo "Запустите скрипт из директории проекта."
    exit 1
fi

# Установка системных зависимостей
echo "1. Установка системных зависимостей (xclip, xsel, python3-tk)..."
sudo apt-get update
sudo apt-get install -y xclip xsel python3-tk

if [ $? -eq 0 ]; then
    echo "✓ Системные зависимости установлены"
else
    echo "✗ Ошибка при установке системных зависимостей"
    exit 1
fi

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo ""
    echo "2. Создание виртуального окружения..."
    python3 -m venv venv
    echo "✓ Виртуальное окружение создано"
else
    echo ""
    echo "2. Виртуальное окружение уже существует"
fi

# Активация виртуального окружения и установка Python зависимостей
echo ""
echo "3. Установка Python зависимостей..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Python зависимости установлены"
else
    echo "✗ Ошибка при установке Python зависимостей"
    exit 1
fi

# Настройка прав доступа
echo ""
echo "4. Настройка прав доступа..."
echo "Добавление пользователя $USER в группу input (для работы горячих клавиш)..."
sudo usermod -a -G input $USER

if [ $? -eq 0 ]; then
    echo "✓ Пользователь добавлен в группу input"
    echo "  ⚠ ВНИМАНИЕ: Нужно перелогиниться в системе, чтобы изменения вступили в силу!"
else
    echo "✗ Ошибка при добавлении в группу input"
fi

# Делаем скрипты исполняемыми
chmod +x clipboard_history.py
chmod +x setup_autostart.sh

echo ""
echo "=== Установка завершена! ==="
echo ""
echo "Следующие шаги:"
echo "1. ПЕРЕЛОГИНИТЕСЬ в системе (чтобы изменения прав вступили в силу)"
echo "2. Запустите приложение:"
echo "   source venv/bin/activate"
echo "   python3 clipboard_history.py"
echo ""
echo "3. Для настройки автозапуска:"
echo "   ./setup_autostart.sh"
echo ""

