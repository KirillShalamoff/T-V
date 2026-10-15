# HW1. Лексер Funny: regex → НКА → ДКА → минимальный ДКА

Python ≥ 3.8, без внешних зависимостей.

| Файл | Что внутри |
|---|---|
| `funnylex.py` | весь построитель: парсер регулярок, НКА Томпсона, ДКА подмножествами, Хопкрофт, экспорт, CLI |
| `lexer.py` | табличный лексер (maximal munch) — отдельно, чтобы подключать в лексер проекта (T0) без построителя |
| `test_funnylex.py` | юнит-тесты автоматов |
| `funny.lex` | регулярки токенов (порядок строк = приоритет) |
| `cases.json` | позитивные/негативные тесты: вход + ожидаемые токены, покрытие всех 128 ASCII |
| `build/` | сгенерированные `dfa.json` и `test_results.json` |
| `REPORT.md` | отчёт |

## Запуск

```bash
python funnylex.py build          # построить автомат, записать build/dfa.json
python funnylex.py test           # прогнать cases.json через ДКА (exit 1 при провале)
python funnylex.py test -v        # то же, показывая все 128 ASCII-проверок
python funnylex.py all            # build + test
python -m unittest test_funnylex -v

python funnylex.py lex -e "if (x >= 01) { y = x; }"
python funnylex.py lex program.fn --all                 # файл, вместе с WS/COMMENT
python funnylex.py lex -e "x != y" --tables build/dfa.json
python funnylex.py --spec other.lex build
```

## Что появляется в `build/`

| Файл | Что внутри |
|---|---|
| `dfa.json` | минимальный ДКА: `start`, `trap`, `transitions[state][class]`, `accept[state]`, `char_class[0..127]` + `other_class`, описание классов и токенов |
| `test_results.json` | статусы всех тестов: вход, ожидаемое, полученное, PASS/FAIL |

## Подключение в лексер проекта (T0)

```python
from lexer import Lexer
lexer = Lexer.from_json("build/dfa.json")
for tok in lexer.tokenize(source):
    if tok.is_error: ...                        # tok.kind: "TRAP" / "INT_LEADING_ZERO", tok.error — текст
    else: ...                                   # tok.kind: "IDENT", "KW_IF", "LE", ...
```

Позиции не поддерживаются (это HW2); `longest_match` уже возвращает смещение конца лексемы.

## Формат `funny.lex`

```
ИМЯ [@skip|@error] = регулярное выражение
```
Синтаксис: литералы, `\n \t \r \xHH`, `\d \w \s`, `[a-z]`, `[^...]`, `.`, `( )`, `|`, `*`, `+`, `?`, экранирование `\+ \( \[`.
Символы вне ASCII запрещены. `@skip` — распознаётся, но не выдаётся (WS, COMMENT). `@error` — распознаётся целиком
и выдаётся как ошибка. Строки на `#` — комментарии.

## Принятые решения

- **Конфликты токенов** — longest match, при равной длине побеждает токен, объявленный раньше
  (`if` → `KW_IF`, `iff`/`if_`/`functions` → `IDENT`).
- **`01`, `00`, `007`** — токен `INT_LEADING_ZERO @error = 0[0-9]+`: лексема съедается целиком и выдаётся ошибка.
- **Ловушка** — явное непринимающее поглощающее состояние. В неё ведут все символы вне ASCII (отдельный символ
  алфавита `OTHER`) и ASCII-символы без перехода (`! & | @ # $ % ^ ~ ` ' " ? . \`, управляющие кроме `\t \r \n`, DEL).
  Лексер выдаёт `TRAP` с этим символом и продолжает со следующего.
- **Non-ASCII внутри комментария** — тоже ловушка, алфавит по спецификации ASCII.
- `:` добавлен как `COLON` (для `x: int`); убрать — удалить строку из `funny.lex`.
- `int`, `return` и т.п. в задании не перечислены — это `IDENT`; новое ключевое слово = строка выше `IDENT`.
