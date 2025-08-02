import os
import shutil

import pathspec


def copy_files_and_create_structure():
    # Определяем пути относительно текущего файла
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Поднимаемся на 1 уровень вверх: из test/ в корень проекта
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    map_backend_dir = os.path.join(project_root, "map_backend")
    dest_dir = os.path.join(script_dir, "export_files_map_backend")
    structure_file = "project_structure.txt"

    # Проверяем существование папки map_backend
    if not os.path.exists(map_backend_dir):
        print(f"Папка map_backend не найдена: {map_backend_dir}")
        return

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

    # Проход по всем файлам и папкам в map_backend
    for root, dirs, files in os.walk(map_backend_dir):
        # Удаляем скрытые папки из списка для обхода
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        # Проверяем, не находимся ли мы в скрытой папке
        if is_hidden_path(root, map_backend_dir):
            continue

        for file in files:
            # Пропускаем скрытые файлы
            if file.startswith("."):
                continue

            src_file = os.path.join(root, file)
            relative_path = os.path.relpath(src_file, map_backend_dir)

            # Проверяем, не игнорируется ли файл в .gitignore
            if gitignore_spec:
                # Создаем путь относительно корня проекта для проверки .gitignore
                project_relative_path = os.path.relpath(src_file, project_root)
                if gitignore_spec.match_file(project_relative_path):
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
                    structure.append(f"map_backend/{relative_path} -> {final_filename}")
                else:
                    structure.append(f"map_backend/{relative_path}")

                copied_files.append(final_filename)

            except Exception as e:
                print(f"Ошибка при копировании {src_file}: {e}")

    # Записываем структуру проекта в txt файл
    structure_path = os.path.join(dest_dir, structure_file)
    with open(structure_path, "w", encoding="utf-8") as f:
        f.write("СТРУКТУРА ПРОЕКТА MAP_BACKEND\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Исходная папка: {map_backend_dir}\n")
        f.write(f"Всего скопировано файлов: {len(copied_files)}\n")
        f.write(f"Целевая папка: {dest_dir}\n\n")
        f.write("ПРАВИЛА ПЕРЕИМЕНОВАНИЯ:\n")
        f.write("- __init__.py -> __init__<имя_папки>.py\n")
        f.write("- При конфликтах имен добавляется номер\n\n")
        f.write("ИСКЛЮЧЕНИЯ:\n")
        f.write("- Скрытые файлы и папки (начинающиеся с точки)\n")
        f.write("- Файлы из .gitignore\n\n")
        f.write("ИСХОДНЫЕ ПУТИ ФАЙЛОВ:\n")
        f.write("-" * 30 + "\n")

        for line in sorted(structure):
            f.write(line + "\n")

    print("Копирование map_backend завершено!")
    print(f"Исходная папка: {map_backend_dir}")
    print(f"Скопировано файлов: {len(copied_files)}")
    print(f"Файлы сохранены в: {dest_dir}")
    print(f"Структура проекта: {structure_path}")


# Запуск функции
if __name__ == "__main__":
    copy_files_and_create_structure()
