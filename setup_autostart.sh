#!/bin/bash
# Скрипт для настройки автозапуска приложения истории буфера обмена

# Получаем абсолютный путь к директории скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/clipboard_history.py"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

# Создаем desktop файл для автозапуска
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

DESKTOP_FILE="$AUTOSTART_DIR/clipboard-history.desktop"

# Создаем desktop файл
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Clipboard History
Comment=История буфера обмена (Win+V)
Exec=$VENV_PYTHON $APP_PATH
Icon=edit-paste
Terminal=false
Categories=Utility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

echo "Desktop файл создан: $DESKTOP_FILE"
echo "Приложение будет запускаться автоматически при входе в систему."
echo ""
echo "Для отключения автозапуска удалите файл:"
echo "  rm $DESKTOP_FILE"

