import os
import shutil

import pathspec


def copy_files_and_create_structure():
    # Определяем пути относительно текущего файла export_files.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Поднимаемся на 2 уровня вверх: из app_bot/temp/ в корень проекта
    project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    dest_dir = os.path.join(script_dir, "exported_files")
    structure_file = "project_structure.txt"

    # Очищаем целевую директорию если она существует
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
        print(f"Целевая директория очищена: {dest_dir}")

    # Создаем целевую директорию
    os.makedirs(dest_dir)
    print(f"Создана новая целевая директория: {dest_dir}")

    # Загружаем правила из .gitignore
    gitignore_spec = None
    gitignore_path = os.path.join(project_root, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, encoding="utf-8") as f:
            gitignore_lines = f.read().splitlines()
        gitignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", gitignore_lines)

    # Функция для проверки скрытых папок
    def is_hidden_path(path, root_path):
        relative_path = os.path.relpath(path, root_path)
        path_parts = relative_path.split(os.sep)
        # Проверяем, есть ли в пути папки, начинающиеся с точки
        for part in path_parts:
            if part.startswith(".") and part != "." and part != "..":
                return True
        return False

    # Список для хранения структуры проекта
    structure = []
    copied_files = []

    # Проход по всем файлам и папкам в проекте
    for root, dirs, files in os.walk(project_root):
        # Удаляем скрытые папки из списка для обхода
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        # Пропускаем папку temp и её содержимое
        if "temp" in dirs:
            dirs.remove("temp")

        # Проверяем, не находимся ли мы в скрытой папке
        if is_hidden_path(root, project_root):
            continue

        for file in files:
            # Пропускаем скрытые файлы
            if file.startswith("."):
                continue

            # Пропускаем сам скрипт export_files.py
            if file == "export_files.py":
                continue

            src_file = os.path.join(root, file)
            relative_path = os.path.relpath(src_file, project_root)

            # Проверяем, не игнорируется ли файл в .gitignore
            if gitignore_spec and gitignore_spec.match_file(relative_path):
                continue

            # Определяем имя файла для сохранения
            if file == "__init__.py":
                # Получаем имя директории, в которой находится __init__.py
                dir_name = os.path.basename(root)
                dest_filename = f"__init__{dir_name}.py"
            else:
                dest_filename = file

            # Создаем уникальное имя файла для избежания конфликтов
            base_name, ext = os.path.splitext(dest_filename)
            counter = 1
            final_filename = dest_filename

            while os.path.exists(os.path.join(dest_dir, final_filename)):
                final_filename = f"{base_name}_{counter}{ext}"
                counter += 1

            dest_file = os.path.join(dest_dir, final_filename)

            try:
                # Копируем файл
                shutil.copy2(src_file, dest_file)

                # Добавляем в структуру
                if final_filename != file:
                    structure.append(f"{relative_path} -> {final_filename}")
                else:
                    structure.append(relative_path)

                copied_files.append(final_filename)

            except Exception as e:
                print(f"Ошибка при копировании {src_file}: {e}")

    # Записываем структуру проекта в txt файл
    structure_path = os.path.join(dest_dir, structure_file)
    with open(structure_path, "w", encoding="utf-8") as f:
        f.write("СТРУКТУРА ПРОЕКТА\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Корень проекта: {project_root}\n")
        f.write(f"Всего скопировано файлов: {len(copied_files)}\n")
        f.write(f"Целевая папка: {dest_dir}\n\n")
        f.write("ПРАВИЛА ПЕРЕИМЕНОВАНИЯ:\n")
        f.write("- __init__.py -> __init__<имя_папки>.py\n")
        f.write("- При конфликтах имен добавляется номер\n\n")
        f.write("ИСКЛЮЧЕНИЯ:\n")
        f.write("- Скрытые файлы и папки (начинающиеся с точки)\n")
        f.write("- Файлы из .gitignore\n")
        f.write("- Папка temp\n")
        f.write("- Файл export_files.py\n\n")
        f.write("ИСХОДНЫЕ ПУТИ ФАЙЛОВ:\n")
        f.write("-" * 30 + "\n")

        for line in sorted(structure):
            f.write(line + "\n")

    print("Копирование завершено!")
    print(f"Корень проекта: {project_root}")
    print(f"Скопировано файлов: {len(copied_files)}")
    print(f"Файлы сохранены в: {dest_dir}")
    print(f"Структура проекта: {structure_path}")


# Запуск функции
if __name__ == "__main__":
    copy_files_and_create_structure()
