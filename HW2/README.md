# HW2_Parser — Синтаксический анализатор языка Funny (LL(1) + AST + Лексер)

Проект выполнен строго по структуре и требованиям презентации `HW2.pptx` и интегрирован с генератором ДКА из `HW1` (`funnylex.py`, `lexer.py`).

## Структура проекта
```text
HW2_Parser/
├── README.md              # инструкция по сборке, запуску и примеры
├── REPORT.md              # метрики, отклонения и ответы на 7 вопросов защиты
├── grammar.txt            # финальная LL(1)-грамматика и таблица FIRST/FOLLOW
├── funny.lex              # спецификация токенов для генератора ДКА
├── funnylex.py            # генератор минимального ДКА из HW1
├── lexer.py               # лексер с позициями (line, col) и методами next_token() / peek()
├── ast_nodes.py           # узлы AST (Program, Function, Block, Assign, If, While, Assert, Assume...)
├── parser.py              # LL(1)-парсер рекурсивным спуском с режимом паники error_recover()
├── main.py                # CLI для разбора программ и запуска snapshot-тестов
└── tests/
    ├── pos_*.funny        # 7 позитивных тестов из презентации
    ├── neg_*.funny        # 6 негативных тестов из презентации
    └── expected/          # эталонные JSON/S-expr snapshots и сообщения об ошибках
```

## Быстрый старт

### 1. Запуск всех позитивных и негативных тестов (Snapshot Testing)
```bash
python main.py test
```

### 2. Разбор программы из строки (вывод AST в JSON, S-выражении или деревом)
```bash
# Вывод в формате JSON:
python main.py parse --format json -e "function f(x, y) returns r requires x > 0 { r = x + y; }"

# Вывод в формате S-выражения:
python main.py parse --format sexpr -e "function f(a) returns r { r = a[0]; a[1] = r; }"

# Человеко-читаемое дерево с координатами узлов:
python main.py parse --format tree -e "function f(x) returns r { if (x > 0) { r = x; } else { r = 0; } }"
```

### 3. Разбор файла `.funny`
```bash
python main.py parse tests/pos_04_if_else.funny --format tree
```
