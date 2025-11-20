#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clipboard History Manager - Приложение для отслеживания истории буфера обмена
Аналог Windows 11 Win+V для Ubuntu
"""

import pyperclip
import threading
import time
import json
import os
import sys
import subprocess
import hashlib
from datetime import datetime
from collections import deque
from tkinter import Tk, Toplevel, Listbox, Scrollbar, Frame, Button, Label, Entry
from tkinter import ttk
from tkinter import Canvas
import queue

# Пробуем импортировать PIL/Pillow для работы с изображениями
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Предупреждение: библиотека Pillow не установлена. Установите: pip install Pillow")

# Пробуем импортировать keyboard
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    print("Предупреждение: библиотека keyboard не установлена")

# Пробуем импортировать pynput как альтернативу
try:
    from pynput import keyboard as pynput_keyboard
    from pynput.keyboard import Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    KeyboardController = None

class ClipboardHistory:
    def __init__(self, max_history=100, clear_on_startup=False):
        self.max_history = max_history
        self.history = deque(maxlen=max_history)
        self.current_clipboard = ""
        self.monitoring = False
        self.last_check_time = 0
        self.config_file = os.path.expanduser("~/.clipboard_history.json")
        self.images_dir = os.path.expanduser("~/.clipboard_history_images")
        self.history_window = None
        self.root = None
        self.search_queue = queue.Queue()
        self.hotkey_registered = False
        self.hotkey_listener = None
        self.clear_on_startup = clear_on_startup
        self.window_just_opened = False  # Флаг для предотвращения автоматической вставки при открытии
        self.window_open_time = 0  # Время открытия окна
        self.current_clipboard_image_hash = None  # Хеш текущего изображения в буфере
        
        # Создаем директорию для изображений, если её нет
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)
        
        # Инициализируем контроллер клавиатуры для автоматической вставки
        if PYNPUT_AVAILABLE and KeyboardController:
            self.keyboard_controller = KeyboardController()
        else:
            self.keyboard_controller = None
        
        # Загрузка истории из файла
        self.load_history()
        
        # Очистка истории при запуске, если включено
        if self.clear_on_startup:
            self.clear_history()
            print("История буфера обмена очищена при запуске")
        
    def load_history(self):
        """Загрузка истории из файла"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history_list = data.get('history', [])
                    # Обратная совместимость: старые записи без типа считаем текстом
                    for entry in history_list:
                        if 'type' not in entry:
                            entry['type'] = 'text'
                    self.history = deque(history_list, maxlen=self.max_history)
            except Exception as e:
                print(f"Ошибка загрузки истории: {e}")
    
    def save_history(self):
        """Сохранение истории в файл"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'history': list(self.history),
                    'last_update': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")
    
    def check_clipboard_image(self):
        """Проверка наличия изображения в буфере обмена"""
        try:
            # Пробуем получить изображение через xclip
            result = subprocess.run(
                ['xclip', '-selection', 'clipboard', '-t', 'image/png', '-o'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        # Пробуем другие форматы
        for image_type in ['image/jpeg', 'image/jpg', 'image/gif', 'image/bmp']:
            try:
                result = subprocess.run(
                    ['xclip', '-selection', 'clipboard', '-t', image_type, '-o'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=1
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                continue
        
        return None
    
    def save_image_from_clipboard(self, image_data):
        """Сохранение изображения из буфера обмена в файл"""
        if not PIL_AVAILABLE or not image_data:
            return None
        
        try:
            # Вычисляем хеш изображения для проверки дубликатов
            image_hash = hashlib.md5(image_data).hexdigest()
            
            # Проверяем, не дублируется ли последний элемент
            if self.history and len(self.history) > 0:
                last_entry = self.history[-1]
                if last_entry.get('type') == 'image' and last_entry.get('image_hash') == image_hash:
                    return None
            
            # Сохраняем изображение
            image_filename = f"{image_hash}.png"
            image_path = os.path.join(self.images_dir, image_filename)
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            # Создаем превью
            try:
                img = Image.open(image_path)
                # Создаем превью размером 150x150
                img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                preview_filename = f"{image_hash}_preview.png"
                preview_path = os.path.join(self.images_dir, preview_filename)
                img.save(preview_path, 'PNG')
            except Exception as e:
                print(f"Ошибка создания превью: {e}")
                preview_path = image_path
            
            return {
                'image_path': image_path,
                'preview_path': preview_path,
                'image_hash': image_hash
            }
        except Exception as e:
            print(f"Ошибка сохранения изображения: {e}")
            return None
    
    def add_to_history(self, text=None, image_data=None):
        """Добавление текста или изображения в историю"""
        # Обработка изображений
        if image_data:
            image_info = self.save_image_from_clipboard(image_data)
            if image_info:
                entry = {
                    'type': 'image',
                    'image_path': image_info['image_path'],
                    'preview_path': image_info['preview_path'],
                    'image_hash': image_info['image_hash'],
                    'timestamp': datetime.now().isoformat(),
                    'preview': '[Изображение]'
                }
                self.history.append(entry)
                self.save_history()
                print(f"Изображение добавлено в историю: {image_info['image_hash']}")
            return
        
        # Обработка текста
        if not text:
            return
        
        # Убираем пробелы и проверяем, не пустая ли строка
        text_stripped = text.strip()
        if not text_stripped:
            return
        
        # Проверяем, не дублируется ли последний элемент
        if self.history and len(self.history) > 0:
            last_entry = self.history[-1]
            if last_entry.get('type') == 'text' and last_entry.get('text') == text:
                return
        
        entry = {
            'type': 'text',
            'text': text,  # Сохраняем оригинальный текст с пробелами
            'timestamp': datetime.now().isoformat(),
            'preview': text[:100] + ('...' if len(text) > 100 else '')
        }
        
        self.history.append(entry)
        self.save_history()
        print(f"Элемент добавлен в историю. Текст: {text[:30]}...")
    
    def monitor_clipboard(self):
        """Мониторинг буфера обмена в отдельном потоке"""
        self.monitoring = True
        
        # Инициализируем текущее состояние буфера обмена
        try:
            self.current_clipboard = pyperclip.paste()
            # Проверяем изображение
            image_data = self.check_clipboard_image()
            if image_data:
                self.current_clipboard_image_hash = hashlib.md5(image_data).hexdigest()
            print(f"Мониторинг буфера обмена запущен. Текущее содержимое: {self.current_clipboard[:50] if self.current_clipboard else 'пусто'}...")
        except Exception as e:
            print(f"Ошибка инициализации буфера обмена: {e}")
            self.current_clipboard = ""
        
        while self.monitoring:
            try:
                # Сначала проверяем изображение
                image_data = self.check_clipboard_image()
                if image_data:
                    image_hash = hashlib.md5(image_data).hexdigest()
                    if image_hash != self.current_clipboard_image_hash:
                        print("Обнаружено изображение в буфере обмена")
                        self.current_clipboard_image_hash = image_hash
                        self.current_clipboard = ""  # Сбрасываем текст
                        self.add_to_history(image_data=image_data)
                        print(f"Добавлено в историю. Всего элементов: {len(self.history)}")
                        time.sleep(0.3)
                        continue
                
                # Затем проверяем текст
                try:
                    current = pyperclip.paste()
                    if current != self.current_clipboard:
                        # Если это не пустая строка и не изображение
                        if current and current.strip():
                            print(f"Обнаружено изменение буфера обмена: {current[:50]}...")
                            self.current_clipboard = current
                            self.current_clipboard_image_hash = None  # Сбрасываем хеш изображения
                            self.add_to_history(current)
                            print(f"Добавлено в историю. Всего элементов: {len(self.history)}")
                except Exception:
                    # Если не удалось получить текст, это нормально (может быть изображение)
                    pass
                
                time.sleep(0.3)  # Проверка каждые 0.3 секунды для более быстрой реакции
            except Exception as e:
                print(f"Ошибка мониторинга буфера обмена: {e}")
                time.sleep(1)
    
    def show_history_window(self):
        """Показ окна с историей"""
        print(f"Открытие окна истории. Элементов в истории: {len(self.history)}")
        
        if self.history_window and self.history_window.winfo_exists():
            # Если окно уже открыто, обновляем список и поднимаем его наверх
            self.update_history_list(getattr(self, 'current_filter', ''))
            self.history_window.lift()
            self.history_window.focus_force()
            # Сбрасываем флаг, так как окно уже было открыто
            self.window_just_opened = False
            return
        
        # Устанавливаем флаг и время открытия окна для предотвращения автоматической вставки
        self.window_just_opened = True
        self.window_open_time = time.time()
        
        # Создаем новое окно
        self.history_window = Toplevel(self.root)
        self.history_window.title("История буфера обмена")
        self.history_window.geometry("800x600")
        self.history_window.attributes('-topmost', True)
        
        # Центрируем окно
        self.center_window(self.history_window)
        
        # Создаем интерфейс
        self.create_history_ui()
        
        # Обработчик закрытия окна
        self.history_window.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        # Привязываем Escape для закрытия окна (только на уровне окна)
        self.history_window.bind('<Escape>', lambda e: self.history_window.destroy())
        
        # Привязываем клавиши для навигации
        def on_key_up(e):
            self.navigate_list(-1)
            return "break"
        
        def on_key_down(e):
            self.navigate_list(1)
            return "break"
        
        def on_key_return(e):
            self.insert_selected()
            return "break"
        
        self.history_window.bind('<Up>', on_key_up)
        self.history_window.bind('<Down>', on_key_down)
        self.history_window.bind('<Return>', on_key_return)
        self.history_canvas.bind('<Up>', on_key_up)
        self.history_canvas.bind('<Down>', on_key_down)
        self.history_canvas.bind('<Return>', on_key_return)
        self.history_canvas.focus_set()  # Устанавливаем фокус на canvas для получения событий клавиатуры
        
        # Снимаем флаг через небольшую задержку (чтобы предотвратить автоматическую вставку при открытии)
        def clear_window_flag():
            """Снимаем флаг после инициализации окна"""
            time.sleep(0.3)  # Даем окну время на полную инициализацию
            self.window_just_opened = False
        
        threading.Thread(target=clear_window_flag, daemon=True).start()
        
    def center_window(self, window):
        """Центрирование окна на экране"""
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_history_ui(self):
        """Создание интерфейса окна истории"""
        # Сохраняем ссылку на текущий отфильтрованный список
        self.filtered_history = list(self.history)
        self.current_filter = ""  # Сохраняем текущий фильтр
        
        # Фрейм для поиска
        search_frame = Frame(self.history_window)
        search_frame.pack(fill='x', padx=10, pady=10)
        
        Label(search_frame, text="Поиск:").pack(side='left', padx=5)
        search_entry = Entry(search_frame)
        search_entry.pack(side='left', fill='x', expand=True, padx=5)
        # Фокус установим позже с задержкой
        
        # Список истории с поддержкой изображений
        list_frame = Frame(self.history_window)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Создаем Canvas для прокручиваемого списка с изображениями
        canvas = Canvas(list_frame, bg='white', highlightthickness=0)
        scrollbar = Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas, bg='white')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Включаем возможность получения фокуса для canvas
        canvas.configure(takefocus=True)
        
        # Добавляем поддержку прокрутки мышью и тачпадом
        def on_mousewheel(event):
            """Обработчик прокрутки колесиком мыши (Windows/Mac)"""
            # Определяем направление прокрутки
            # event.delta: положительное = прокрутка вверх, отрицательное = вниз
            # Нормализуем delta (обычно 120 единиц = один шаг прокрутки)
            if event.delta:
                delta = -1 * (event.delta / 120)
                # Прокручиваем canvas
                canvas.yview_scroll(int(delta), "units")
            return "break"
        
        def on_mousewheel_linux(event):
            """Обработчик прокрутки для Linux (Button-4 и Button-5)"""
            # Button-4 = прокрутка вверх, Button-5 = прокрутка вниз
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            return "break"
        
        # Привязываем события прокрутки к canvas
        # MouseWheel работает на Windows и Mac
        canvas.bind("<MouseWheel>", on_mousewheel)
        # Button-4 и Button-5 работают на Linux
        canvas.bind("<Button-4>", on_mousewheel_linux)
        canvas.bind("<Button-5>", on_mousewheel_linux)
        
        # Также привязываем к scrollable_frame для прокрутки при наведении на элементы списка
        scrollable_frame.bind("<MouseWheel>", on_mousewheel)
        scrollable_frame.bind("<Button-4>", on_mousewheel_linux)
        scrollable_frame.bind("<Button-5>", on_mousewheel_linux)
        
        # Привязываем к list_frame для прокрутки при наведении на область списка
        list_frame.bind("<MouseWheel>", on_mousewheel)
        list_frame.bind("<Button-4>", on_mousewheel_linux)
        list_frame.bind("<Button-5>", on_mousewheel_linux)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Сохраняем ссылки для использования в других методах
        self.history_canvas = canvas
        self.history_scrollable_frame = scrollable_frame
        self.history_listbox = None  # Для обратной совместимости, но не используется
        
        # Заполняем список
        self.update_history_list()
        
        # Фрейм для кнопок
        button_frame = Frame(self.history_window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        Button(button_frame, text="Вставить", command=self.insert_selected,
               bg='#4CAF50', fg='white', font=('Arial', 10, 'bold'),
               padx=20, pady=5).pack(side='left', padx=5)
        
        Button(button_frame, text="Удалить", command=self.delete_selected,
               bg='#f44336', fg='white', font=('Arial', 10),
               padx=20, pady=5).pack(side='left', padx=5)
        
        Button(button_frame, text="Очистить всю историю", command=self.clear_history,
               bg='#ff9800', fg='white', font=('Arial', 10),
               padx=20, pady=5).pack(side='left', padx=5)
        
        Button(button_frame, text="Перезапустить", command=self.restart_application,
               bg='#2196F3', fg='white', font=('Arial', 10),
               padx=20, pady=5).pack(side='left', padx=5)
        
        Button(button_frame, text="Закрыть", command=self.history_window.destroy,
               font=('Arial', 10), padx=20, pady=5).pack(side='right', padx=5)
        
        # Привязываем поиск
        def on_search_change(e):
            self.filter_history(search_entry.get())
            # Фокус остается на поле поиска, чтобы пользователь мог продолжать вводить
        
        search_entry.bind('<KeyRelease>', on_search_change)
        
        # Привязываем стрелки вверх/вниз в поле поиска - навигируем по списку
        def on_search_arrow_up(e):
            result = self.navigate_list(-1)
            return result if result else "break"
        
        def on_search_arrow_down(e):
            result = self.navigate_list(1)
            return result if result else "break"
        
        search_entry.bind('<Up>', on_search_arrow_up)
        search_entry.bind('<Down>', on_search_arrow_down)
        
        # Привязываем Enter в поле поиска - если есть выбранный элемент, вставляем его
        def on_search_enter(e):
            if hasattr(self, 'history_items') and self.history_items:
                self.insert_selected()
        
        search_entry.bind('<Return>', on_search_enter)
        
        # Привязываем Escape в поле поиска - закрываем окно
        search_entry.bind('<Escape>', lambda e: self.history_window.destroy())
        
        # Выделение первого элемента происходит в update_history_list
        
        # Устанавливаем фокус на canvas для получения событий клавиатуры
        # Фокус на поле поиска можно установить позже, если нужно
        def set_initial_focus():
            """Устанавливаем начальный фокус с задержкой"""
            # Устанавливаем фокус на canvas, чтобы он мог получать события клавиатуры
            self.history_canvas.focus_set()
        
        # Устанавливаем фокус после полной инициализации окна
        self.history_window.after(50, set_initial_focus)
    
    def update_history_list(self, filter_text=""):
        """Обновление списка истории с поддержкой изображений"""
        if not hasattr(self, 'history_scrollable_frame'):
            return
        
        # Очищаем текущий список
        for widget in self.history_scrollable_frame.winfo_children():
            widget.destroy()
        
        # Сохраняем текущий фильтр
        self.current_filter = filter_text
        
        filtered_history = list(self.history)
        if filter_text:
            filter_lower = filter_text.lower()
            filtered_history = [h for h in filtered_history 
                              if filter_lower in h.get('text', '').lower() or 
                              filter_lower in h.get('preview', '').lower() or
                              (h.get('type') == 'image' and 'изображение' in filter_lower)]
        
        # Сохраняем отфильтрованный список для использования в других методах
        self.filtered_history = filtered_history
        
        # Показываем в обратном порядке (новые сверху)
        self.history_items = []  # Список для хранения ссылок на элементы
        
        for idx, entry in enumerate(reversed(filtered_history)):
            try:
                timestamp = datetime.fromisoformat(entry['timestamp'])
                time_str = timestamp.strftime("%d.%m.%Y %H:%M:%S")
            except:
                time_str = entry.get('timestamp', '')
            
            # Создаем фрейм для каждого элемента
            item_frame = Frame(self.history_scrollable_frame, bg='white', relief='solid', bd=1)
            item_frame.pack(fill='x', padx=2, pady=2)
            
            # Сохраняем индекс для обработки кликов
            item_frame.bind('<Button-1>', lambda e, i=idx: self.select_item(i))
            item_frame.bind('<Double-Button-1>', lambda e, i=idx: self.insert_selected_by_index(i))
            
            # Если это изображение
            if entry.get('type') == 'image' and PIL_AVAILABLE:
                preview_path = entry.get('preview_path') or entry.get('image_path')
                if preview_path and os.path.exists(preview_path):
                    try:
                        img = Image.open(preview_path)
                        img.thumbnail((100, 100), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        
                        # Создаем метку с изображением
                        img_label = Label(item_frame, image=photo, bg='white')
                        img_label.image = photo  # Сохраняем ссылку
                        img_label.pack(side='left', padx=5, pady=5)
                    except Exception as e:
                        print(f"Ошибка загрузки превью: {e}")
                
                # Текстовая метка
                text_label = Label(item_frame, 
                                 text=f"[{time_str}] [Изображение]",
                                 font=('Arial', 10),
                                 bg='white',
                                 anchor='w',
                                 justify='left')
                text_label.pack(side='left', fill='x', expand=True, padx=5)
                text_label.bind('<Button-1>', lambda e, i=idx: self.select_item(i))
                text_label.bind('<Double-Button-1>', lambda e, i=idx: self.insert_selected_by_index(i))
            else:
                # Обычный текст
                preview = entry.get('preview', entry.get('text', '')[:100])
                text_label = Label(item_frame,
                                 text=f"[{time_str}] {preview}",
                                 font=('Arial', 11),
                                 bg='white',
                                 anchor='w',
                                 justify='left',
                                 wraplength=600)
                text_label.pack(side='left', fill='x', expand=True, padx=5, pady=5)
                text_label.bind('<Button-1>', lambda e, i=idx: self.select_item(i))
                text_label.bind('<Double-Button-1>', lambda e, i=idx: self.insert_selected_by_index(i))
            
            # Сохраняем ссылку на фрейм
            self.history_items.append({
                'frame': item_frame,
                'entry': entry,
                'index': idx
            })
        
        # Обновляем прокрутку
        self.history_canvas.update_idletasks()
        self.history_canvas.configure(scrollregion=self.history_canvas.bbox("all"))
        
        # Выделяем первый элемент, если есть
        if self.history_items:
            self.selected_index = 0  # Инициализируем selected_index
            self.select_item(0)
        else:
            self.selected_index = None
    
    def select_item(self, index):
        """Выделение элемента по индексу"""
        if not hasattr(self, 'history_items') or not self.history_items:
            return
        
        # Сбрасываем выделение всех элементов
        for item in self.history_items:
            item['frame'].config(bg='white')
            for widget in item['frame'].winfo_children():
                if isinstance(widget, Label):
                    widget.config(bg='white', fg='black')
        
        # Выделяем выбранный элемент
        if 0 <= index < len(self.history_items):
            item = self.history_items[index]
            item['frame'].config(bg='#4CAF50')
            for widget in item['frame'].winfo_children():
                if isinstance(widget, Label):
                    # Для изображений не меняем цвет фона, только рамку
                    if widget.cget('image'):
                        widget.config(bg='#4CAF50')
                    else:
                        widget.config(bg='#4CAF50', fg='white')
            
            # Прокручиваем к выбранному элементу
            self.history_canvas.update_idletasks()
            try:
                frame = item['frame']
                canvas_height = self.history_canvas.winfo_height()
                scrollable_height = self.history_scrollable_frame.winfo_height()
                
                if canvas_height > 0 and scrollable_height > canvas_height:
                    # Получаем позицию элемента относительно scrollable_frame
                    frame_y = frame.winfo_y()
                    frame_height = frame.winfo_height()
                    
                    # Вычисляем текущую видимую область
                    # Получаем текущую позицию прокрутки (0.0 - верх, 1.0 - низ)
                    vbar = self.history_canvas.yview()
                    scroll_top_px = vbar[0] * scrollable_height  # Верх видимой области в пикселях
                    scroll_bottom_px = vbar[1] * scrollable_height  # Низ видимой области в пикселях
                    
                    # Координаты элемента относительно scrollable_frame
                    element_top = frame_y
                    element_bottom = frame_y + frame_height
                    
                    # Отступ для лучшей видимости
                    margin = 5
                    
                    # Вычисляем прокручиваемую область (разница между общей высотой и видимой)
                    scrollable_area = scrollable_height - canvas_height
                    
                    # Проверяем, виден ли элемент полностью
                    needs_scroll = False
                    new_scroll = None
                    
                    # Вычисляем отступ для видимости соседних элементов
                    # Находим высоту предыдущего и следующего элементов для правильного отступа
                    prev_element_height = 0
                    next_element_height = 0
                    
                    # Высота предыдущего элемента (для прокрутки вверх)
                    if index > 0:
                        prev_item = self.history_items[index - 1]
                        prev_element_height = prev_item['frame'].winfo_height()
                    
                    # Высота следующего элемента (для прокрутки вниз)
                    if index < len(self.history_items) - 1:
                        next_item = self.history_items[index + 1]
                        next_element_height = next_item['frame'].winfo_height()
                    
                    # Если не удалось получить высоты соседних элементов, используем высоту текущего элемента
                    if prev_element_height == 0:
                        prev_element_height = frame_height
                    if next_element_height == 0:
                        next_element_height = frame_height
                    
                    if element_top < scroll_top_px + margin:
                        # Элемент выше видимой области - прокручиваем вверх
                        # Прокручиваем так, чтобы элемент был виден, а за ним был виден предыдущий элемент
                        if scrollable_area > 0:
                            # Вычисляем позицию так, чтобы элемент был виден, а сверху был виден предыдущий элемент
                            # Отступ = высота предыдущего элемента + небольшой margin
                            offset = prev_element_height + margin
                            scroll_pixels = max(0, element_top - offset)
                            new_scroll = scroll_pixels / scrollable_area
                            needs_scroll = True
                    elif element_bottom > scroll_bottom_px - margin:
                        # Элемент ниже видимой области - прокручиваем вниз
                        # Прокручиваем так, чтобы элемент был виден, а снизу был виден следующий элемент
                        if scrollable_area > 0:
                            # Вычисляем позицию так, чтобы элемент был виден, а снизу был виден следующий элемент
                            # Отступ = высота следующего элемента + небольшой margin
                            offset = next_element_height + margin
                            scroll_pixels = element_bottom - canvas_height + offset
                            new_scroll = scroll_pixels / scrollable_area
                            needs_scroll = True
                    
                    if needs_scroll and new_scroll is not None:
                        # Ограничиваем значение от 0.0 до 1.0
                        new_scroll = max(0.0, min(1.0, new_scroll))
                        self.history_canvas.yview_moveto(new_scroll)
                        # Обновляем canvas для немедленного отображения изменений
                        self.history_canvas.update_idletasks()
            except Exception as e:
                # Fallback: простая прокрутка по индексу
                try:
                    total_items = len(self.history_items)
                    if total_items > 0:
                        # Вычисляем примерную позицию элемента
                        # Учитываем, что каждый элемент имеет примерно одинаковую высоту
                        item_ratio = index / max(1, total_items - 1)
                        # Применяем небольшую корректировку для центрирования
                        scroll_pos = max(0.0, min(1.0, item_ratio * 0.9))
                        self.history_canvas.yview_moveto(scroll_pos)
                except:
                    pass
        
        self.selected_index = index
    
    def navigate_list(self, direction):
        """Навигация по списку клавишами Вверх/Вниз"""
        if not hasattr(self, 'history_items') or not self.history_items:
            return "break"
        
        # Получаем текущий индекс, если его нет - используем 0
        current_index = getattr(self, 'selected_index', None)
        if current_index is None:
            current_index = 0
        
        new_index = current_index + direction
        
        # Проверяем границы списка
        if new_index < 0:
            new_index = 0
        elif new_index >= len(self.history_items):
            new_index = len(self.history_items) - 1
        
        # Обновляем только если индекс действительно изменился
        if new_index != current_index:
            self.select_item(new_index)
        
        return "break"  # Предотвращаем дальнейшую обработку события
    
    def filter_history(self, filter_text):
        """Фильтрация истории по поисковому запросу"""
        self.update_history_list(filter_text)
        # Выделение первого элемента происходит в update_history_list
    
    def insert_selected_by_index(self, index):
        """Вставка элемента по индексу"""
        # Защита от автоматической вставки при открытии окна
        if self.window_just_opened or (time.time() - self.window_open_time) < 0.5:
            print("Вставка заблокирована: окно только что открылось")
            return
        
        # Используем сохраненный отфильтрованный список
        filtered_history = getattr(self, 'filtered_history', list(self.history))
        
        if 0 <= index < len(filtered_history):
            # Берем в обратном порядке (новые сверху)
            entry = filtered_history[-(index + 1)]
            
            # Обработка изображений
            if entry.get('type') == 'image':
                image_path = entry.get('image_path')
                if image_path and os.path.exists(image_path):
                    # Копируем изображение в буфер обмена через xclip
                    try:
                        with open(image_path, 'rb') as f:
                            image_data = f.read()
                        subprocess.run(
                            ['xclip', '-selection', 'clipboard', '-t', 'image/png'],
                            input=image_data,
                            check=True
                        )
                        print(f"Изображение скопировано в буфер обмена: {image_path}")
                    except Exception as e:
                        print(f"Ошибка копирования изображения: {e}")
                        return
                else:
                    print("Файл изображения не найден")
                    return
            else:
                # Обработка текста
                text_to_insert = entry.get('text', '')
                if not text_to_insert:
                    return
                
                # Копируем текст в буфер обмена
                pyperclip.copy(text_to_insert)
                self.current_clipboard = text_to_insert
            
            # Закрываем окно
            self.history_window.destroy()
            self.history_window = None
            
            # Автоматически вставляем через Ctrl+V после небольшой задержки
            def auto_paste():
                """Автоматическая вставка через Ctrl+V"""
                time.sleep(0.15)
                if self.keyboard_controller:
                    try:
                        with self.keyboard_controller.pressed(pynput_keyboard.Key.ctrl_l):
                            self.keyboard_controller.press('v')
                            self.keyboard_controller.release('v')
                        if entry.get('type') == 'image':
                            print("Изображение автоматически вставлено")
                        else:
                            print(f"Текст автоматически вставлен: {text_to_insert[:50]}...")
                    except Exception as e:
                        try:
                            with self.keyboard_controller.pressed(pynput_keyboard.Key.ctrl):
                                self.keyboard_controller.press('v')
                                self.keyboard_controller.release('v')
                            if entry.get('type') == 'image':
                                print("Изображение автоматически вставлено")
                            else:
                                print(f"Текст автоматически вставлен: {text_to_insert[:50]}...")
                        except Exception as e2:
                            print(f"Ошибка при автоматической вставке: {e2}")
                            if entry.get('type') == 'image':
                                print("Изображение скопировано в буфер обмена, вставьте вручную (Ctrl+V)")
                            else:
                                print("Текст скопирован в буфер обмена, вставьте вручную (Ctrl+V)")
                else:
                    if entry.get('type') == 'image':
                        print("Контроллер клавиатуры недоступен. Изображение скопировано в буфер обмена.")
                    else:
                        print("Контроллер клавиатуры недоступен. Текст скопирован в буфер обмена.")
            
            # Запускаем автоматическую вставку в отдельном потоке
            paste_thread = threading.Thread(target=auto_paste, daemon=True)
            paste_thread.start()
    
    def insert_selected(self):
        """Вставка выбранного элемента в буфер обмена и автоматическая вставка"""
        selected_index = getattr(self, 'selected_index', 0)
        self.insert_selected_by_index(selected_index)
    
    def delete_selected(self):
        """Удаление выбранного элемента из истории"""
        selected_index = getattr(self, 'selected_index', None)
        if selected_index is None:
            return
        
        # Используем сохраненный отфильтрованный список
        filtered_history = getattr(self, 'filtered_history', list(self.history))
        
        if 0 <= selected_index < len(filtered_history):
            entry = filtered_history[-(selected_index + 1)]
            # Удаляем из основного списка истории
            if entry in self.history:
                # Если это изображение, удаляем файлы
                if entry.get('type') == 'image':
                    image_path = entry.get('image_path')
                    preview_path = entry.get('preview_path')
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                        except:
                            pass
                    if preview_path and os.path.exists(preview_path) and preview_path != image_path:
                        try:
                            os.remove(preview_path)
                        except:
                            pass
                
                self.history.remove(entry)
                self.save_history()
                # Обновляем список с учетом текущего фильтра
                current_filter = getattr(self, 'current_filter', '')
                self.update_history_list(current_filter)
    
    def clear_history(self):
        """Очистка всей истории"""
        # Удаляем файлы изображений
        for entry in list(self.history):
            if entry.get('type') == 'image':
                image_path = entry.get('image_path')
                preview_path = entry.get('preview_path')
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except:
                        pass
                if preview_path and os.path.exists(preview_path) and preview_path != image_path:
                    try:
                        os.remove(preview_path)
                    except:
                        pass
        
        self.history.clear()
        self.save_history()
        self.update_history_list()
    
    def on_window_close(self):
        """Обработчик закрытия окна"""
        self.history_window.destroy()
        self.history_window = None
        self.window_just_opened = False  # Сбрасываем флаг при закрытии
    
    def restart_application(self):
        """Перезапуск приложения"""
        try:
            # Сохраняем историю перед перезапуском
            self.save_history()
            
            # Получаем путь к текущему скрипту
            script_path = os.path.abspath(__file__)
            script_dir = os.path.dirname(script_path)
            
            # Проверяем, есть ли виртуальное окружение
            venv_python = os.path.join(script_dir, 'venv', 'bin', 'python3')
            if os.path.exists(venv_python):
                python_executable = venv_python
            else:
                python_executable = sys.executable
            
            # Закрываем окно
            if self.history_window:
                self.history_window.destroy()
                self.history_window = None
            
            # Запускаем новый процесс в фоне
            # Используем start_new_session=True для запуска в новой сессии
            # Перенаправляем вывод в /dev/null для фонового запуска
            with open(os.devnull, 'w') as devnull:
                subprocess.Popen(
                    [python_executable, script_path],
                    cwd=script_dir,
                    stdout=devnull,
                    stderr=devnull,
                    start_new_session=True
                )
            
            print("Приложение перезапускается...")
            
            # Останавливаем текущий процесс через небольшую задержку
            def stop_current():
                time.sleep(0.5)  # Даем время новому процессу запуститься
                self.stop()
            
            threading.Thread(target=stop_current, daemon=True).start()
            
        except Exception as e:
            print(f"Ошибка при перезапуске приложения: {e}")
            import traceback
            traceback.print_exc()
    
    def start(self):
        """Запуск приложения"""
        # Создаем скрытое главное окно
        self.root = Tk()
        self.root.withdraw()  # Скрываем главное окно
        
        # Запускаем мониторинг в отдельном потоке
        monitor_thread = threading.Thread(target=self.monitor_clipboard, daemon=True)
        monitor_thread.start()
        
        # Регистрируем горячую клавишу (Ctrl + Alt + Z)
        self.register_hotkey()
        
        print("Приложение истории буфера обмена запущено")
        if self.hotkey_registered:
            print("✓ Горячая клавиша Ctrl+Alt+Z зарегистрирована")
            print("Нажмите Ctrl+Alt+Z для открытия истории")
        else:
            print("⚠ Горячая клавиша НЕ зарегистрирована!")
            print("Для работы горячих клавиш на Linux может потребоваться:")
            print("  1. Запуск с sudo: sudo python3 clipboard_history.py")
            print("  2. Или добавление в группу input: sudo usermod -a -G input $USER")
            print("     (после этого нужно перелогиниться)")
            print("  3. Или установить pynput: pip install pynput")
        print("Нажмите Ctrl+C для выхода")
        
        # Запускаем главный цикл
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            print("\nОстановка приложения...")
            self.stop()
    
    def register_hotkey(self):
        """Регистрация горячей клавиши (пробуем разные методы)"""
        # Метод 1: Используем keyboard (требует root на Linux)
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.add_hotkey('ctrl+alt+z', self.show_history_window)
                self.hotkey_registered = True
                print("✓ Горячая клавиша зарегистрирована через keyboard")
                return
            except Exception as e:
                print(f"⚠ Не удалось зарегистрировать через keyboard: {e}")
        
        # Метод 2: Используем pynput (может работать без root)
        if PYNPUT_AVAILABLE:
            try:
                # Создаем горячую клавишу
                hotkey = pynput_keyboard.HotKey(
                    pynput_keyboard.HotKey.parse('<ctrl>+<alt>+z'),
                    lambda: self.root.after(0, self.show_history_window)
                )
                
                # Создаем слушатель
                def on_press(key):
                    try:
                        hotkey.press(key)
                    except:
                        pass
                
                def on_release(key):
                    try:
                        hotkey.release(key)
                    except:
                        pass
                
                self.hotkey_listener = pynput_keyboard.Listener(
                    on_press=on_press,
                    on_release=on_release
                )
                self.hotkey_listener.start()
                self.hotkey_registered = True
                print("✓ Горячая клавиша зарегистрирована через pynput")
                return
            except Exception as e:
                print(f"⚠ Не удалось зарегистрировать через pynput: {e}")
                import traceback
                traceback.print_exc()
        
        # Если ничего не сработало
        print("✗ Не удалось зарегистрировать горячую клавишу")
        self.hotkey_registered = False
    
    def stop(self):
        """Остановка приложения"""
        self.monitoring = False
        
        # Останавливаем слушатель горячих клавиш
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except:
                pass
        
        if self.history_window:
            self.history_window.destroy()
        if self.root:
            self.root.quit()
        self.save_history()

def main():
    """Главная функция"""
    # Очистка истории при каждом запуске (при включении ноутбука)
    app = ClipboardHistory(max_history=100, clear_on_startup=True)
    app.start()

if __name__ == "__main__":
    main()

