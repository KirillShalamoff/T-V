import itertools  # Итераторные функции для генерации комбинаций символов и последовательностей
import json  # Модуль для работы с форматом данных JSON (сохранение и загрузка таблиц ДКА)
import random  # Генератор псевдослучайных чисел для генерации случайных тестовых строк
import re  # Модуль регулярных выражений Python (используется как эталонное сравнение)
import sys  # Системный модуль для управления путями поиска модулей
import tempfile  # Модуль для создания временных файлов и директорий при тестировании экспорта
import unittest  # Встроенный фреймворк для написания и запуска модульных тестов
from pathlib import Path  # Объектно-ориентированная работа с путями файловой системы

# Добавление директории текущего файла в sys.path для импорта локальных модулей
sys.path.insert(0, str(Path(__file__).resolve().parent))

import funnylex as fx  # Импорт основного модуля лексического генератора
from funnylex import (  # Импорт основных функций, типов и констант из модуля funnylex
    DEFAULT_CASES,  # Набор встроенных эталонных тестов по умолчанию
    NUM_SYMBOLS,  # Общее количество обрабатываемых символов алфавита (256 байтов/ASCII)
    OTHER,  # Специальный класс символов для обозначения не-ASCII и внеалфавитных символов
    RegexError,  # Исключение при синтаксических ошибках в регулярном выражении
    SpecError,  # Исключение при ошибках синтаксиса файла спецификации токенов
    build,  # Функция сборки всей системы (спецификации, НКА, ДКА, сжатые таблицы)
    build_nfa,  # Построение НКА (NFA) из регулярных выражений по алгоритму Томпсона
    hopcroft_minimize,  # Минимизация ДКА по алгоритму Хопкрофта
    load_cases,  # Загрузка тестовых примеров из JSON-файлов
    moore_class_count,  # Подсчет количества классов эквивалентности Мура (для проверки минимальности)
    parse_regex,  # Разбор строки регулярного выражения в синтаксическое дерево (AST)
    parse_spec,  # Разбор спецификации правил токенизации
    reachable_states,  # Поиск всех достижимых состояний автомата из начального
    run_cases,  # Выполнение токенизации на наборе тестов и проверка результатов
    subset_construction,  # Детерминизация НКА в ДКА (алгоритм построения подмножеств)
)
from lexer import Lexer  # Импорт основного класса лексического анализатора

RES = build()  # Предварительная сборка эталонного ДКА и таблиц из спецификации по умолчанию
SAMPLE = "fiwelsa_Z0197 \t\r\n/=<>!+-*()[]{},;:.é"  # Алфавитная выборка символов для тестирования


def reference(specs, text):  # Эталонная функция поиска токена с помощью стандартного модуля `re`
    if any(ord(ch) >= 128 for ch in text):  # Проверка на наличие не-ASCII символов (коды >= 128)
        return None  # Любой символ вне ASCII делает строку невалидной для данного алфавита
    for i, sp in enumerate(specs):  # Перебор спецификаций токенов в порядке их приоритета
        if re.fullmatch(sp.regex, text):  # Проверка полного совпадения строки с регулярным выражением токена
            return i  # Возвращает индекс первого совпавшего правила
    return None  # Возвращает None, если ни одно правило не совпало


def strings(alphabet, max_len, n_random=3000, seed=42):  # Генератор тестовых строк (детерминированных и случайных)
    for n in range(max_len + 1):  # Перебор длин строк от 0 до max_len включительно
        for t in itertools.product(alphabet, repeat=n):  # Полное декартово произведение символов алфавита длины n
            yield "".join(t)  # Генерация всех возможных комбинаций символов заданной длины
    rnd = random.Random(seed)  # Инициализация генератора с фиксированным зерном для воспроизводимости
    extra = ["function", "returns", "while", "assert", "assume", "invariant", "length", "//", "0", "=="]  # Ключевые слова
    for _ in range(n_random):  # Цикл генерации n_random случайных комбинаций
        parts = [
            rnd.choice(extra) if rnd.random() < 0.3 else rnd.choice(alphabet)  # С вероятностью 30% выбор синтаксического слова
            for _ in range(rnd.randint(0, 6))  # Случайная длина составной строки от 0 до 6 элементов
        ]
        yield "".join(parts)  # Возврат сгенерированной случайной строки


class RegexParserTests(unittest.TestCase):  # Набор модульных тестов парсера регулярных выражений
    def test_errors(self):  # Тестирование обработки синтаксически неверных регулярных выражений
        for bad in ["(a", "a)", "[a", "*a", "a|+", "[z-a]", "é", "\\x9", "\\", "[]"]:  # Список заведомо некорректных регулярных выражений
            with self.assertRaises(RegexError, msg=bad):  # Проверка генерации исключения RegexError
                parse_regex(bad)  # Разбор регулярного выражения должен завершаться ошибкой

    def test_features(self):  # Тестирование корректности поддержки разного синтаксиса регулярных выражений
        cases = {  # Словарь: "регулярное выражение" -> список валидных строк для проверки
            "a|b": ["a", "b"],  # Альтернация (оператор ИЛИ)
            "ab*": ["a", "abbb"],  # Звезда Клини (0 и более повторений)
            "a+": ["a", "aa"],  # Плюс Клини (1 и более повторений)
            "a?b": ["b", "ab"],  # Опциональный символ (0 или 1 повторение)
            "[^a]": ["b", "\n"],  # Отрицание символьного класса (любой символ кроме 'a')
            "\\d\\w\\s": ["1_ "],  # Встроенные классы: цифра, буквенно-цифровой символ, пробел
            "\\x41": ["A"],  # Символ по его шестнадцатеричному коду ASCII
            "()a": ["a"],  # Пустая скобочная группа
            "[a\\-z]": ["-", "a", "z"],  # Экранированный дефис внутри символьного класса
            ".": ["x", "\t"],  # Точка (любой символ, кроме перевода строки)
        }
        for rx, good in cases.items():  # Перебор всех тестовых регулярных выражений
            dfa = hopcroft_minimize(subset_construction(build_nfa([parse_regex(rx)])))  # Построение минимизированного ДКА
            for s in good:  # Проверка каждой ожидаемой строки
                self.assertEqual(dfa.match(s), 0, (rx, s))  # Строка должна успешно распознаваться автоматом (индекс 0)
        dfa = hopcroft_minimize(subset_construction(build_nfa([parse_regex("[a\\-z]")])))  # Проверка экранированного дефиса
        self.assertIsNone(dfa.match("b"))  # 'b' не совпадает, так как '-' экранирован и диапазон [a-z] не сформирован
        dfa = hopcroft_minimize(subset_construction(build_nfa([parse_regex(".")])))  # ДКА для одиночной точки
        self.assertIsNone(dfa.match("\n"))  # Символ перевода строки '\n' не должен совпадать с точкой


class PerTokenEquivalence(unittest.TestCase):  # Тесты эквивалентности представлений каждого отдельного токена
    def test_each_token(self):  # Проверка каждого правила токена по отдельности
        for sp in RES.specs:  # Итерация по всем спецификациям токенов из собранного ресурса
            nfa = build_nfa([sp.ast])  # Построение НКА для одного токена
            dfa = subset_construction(nfa)  # Преобразование НКА в ДКА
            mdfa = hopcroft_minimize(dfa)  # Минимизация ДКА по алгоритму Хопкрофта
            self.assertEqual(moore_class_count(mdfa), mdfa.num_states, sp.name)  # Проверка минимальности автомата
            for s in strings(SAMPLE, 2, n_random=400):  # Генерация набора коротких тестовых строк
                exp = 0 if reference([sp], s) == 0 else None  # Ожидаемый результат эталонной функции
                self.assertEqual(nfa.match(s), exp, (sp.name, s))  # Проверка работы НКА
                self.assertEqual(dfa.match(s), exp, (sp.name, s))  # Проверка работы ДКА
                self.assertEqual(mdfa.match(s), exp, (sp.name, s))  # Проверка работы минимизированного ДКА


class CombinedAutomaton(unittest.TestCase):  # Тесты для объединенного автомата всех токенов
    def test_equivalence_with_reference(self):  # Тест эквивалентности работы автомата эталонной функции `re`
        for s in strings(SAMPLE, 3):  # Генерация тестовых строк длины до 3 символов
            exp = reference(RES.specs, s)  # Определение ожидаемого номера токена через re.fullmatch
            self.assertEqual(RES.nfa.match(s), exp, repr(s))  # Сравнение с результатами НКА
            self.assertEqual(RES.dfa.match(s), exp, repr(s))  # Сравнение с результатами ДКА
            self.assertEqual(RES.min_dfa.match(s), exp, repr(s))  # Сравнение с результатами минимизированного ДКА

    def test_min_is_minimal(self):  # Тест минимальности и достижимости состояний
        m = RES.min_dfa  # Ссылка на минимизированный ДКА
        self.assertEqual(moore_class_count(m), m.num_states)  # Количество классов Мура должно совпадать с числом состояний
        self.assertEqual(moore_class_count(RES.dfa), m.num_states)  # Исходный ДКА при подсчете классов равен минимизированному
        self.assertEqual(len(reachable_states(m)), m.num_states)  # Все состояния автомата должны быть достижимы из начального
        self.assertLessEqual(m.num_states, RES.dfa.num_states)  # Число состояний минимизированного ДКА <= числа состояний исходного

    def test_complete_and_trap(self):  # Проверка свойств полноты ДКА и состояния-ловушки (trap state)
        m = RES.min_dfa  # Ссылка на минимизированный ДКА
        for row in m.trans:  # Проход по строкам таблицы переходов (по каждому состоянию)
            self.assertEqual(len(row), NUM_SYMBOLS)  # Каждая строка переходов должна покрывать весь алфавит символов
            self.assertEqual(row[OTHER], m.trap)  # Переходы по символу OTHER обязаны вести в ловушку
        self.assertTrue(all(t == m.trap for t in m.trans[m.trap]))  # Все переходы из ловушки замкнуты на саму себя
        self.assertNotIn(m.trap, m.accept)  # Состояние-ловушка не должно быть принимающим (финишным)
        self.assertEqual(sum(1 for s in range(m.num_states)  # Проверка единственности тупикового непринимающего состояния
                             if all(t == s for t in m.trans[s]) and s not in m.accept), 1)

    def test_keyword_priority(self):  # Тестирование приоритета ключевых слов перед идентификаторами
        names = [sp.name for sp in RES.specs]  # Список имен всех токенов
        for kw in ["function", "returns", "while", "if", "else", "assert", "assume",
                   "invariant", "length"]:  # Перебор ключевых слов
            self.assertEqual(names[RES.min_dfa.match(kw)], "KW_" + kw.upper())  # Ключевое слово распознается как соответствующий KW_*
            self.assertEqual(names[RES.min_dfa.match(kw + "x")], "IDENT")  # Слово с суффиксом распознается как идентификатор


class ExportTests(unittest.TestCase):  # Тестирование экспорта таблиц ДКА и сериализации
    def test_compressed_table_equals_full(self):  # Тест эквивалентности сжатой таблицы переходов и полной матрицы ДКА
        t = RES.tables  # Сжатые таблицы ДКА в формате словаря
        m = RES.min_dfa  # Исходный минимальный ДКА
        for s in range(m.num_states):  # Проход по всем состояниям ДКА
            for a in range(NUM_SYMBOLS):  # Проход по всем возможным ASCII/байтовым кодам символов
                cls = t["char_class"][a] if a < 128 else t["other_class"]  # Определение класса эквивалентности для символа
                self.assertEqual(t["transitions"][s][cls], m.trans[s][a])  # Переход в сжатой таблице совпадает с полным ДКА

    def test_artifacts_roundtrip(self):  # Тестирование сохранения и повторного чтения JSON-файла с таблицами
        with tempfile.TemporaryDirectory() as d:  # Создание изолированной временной директории
            d = Path(d)  # Обертка пути во временную директорию
            fx.write_json(RES.tables, d / "dfa.json")  # Сохранение сгенерированных таблиц в JSON
            self.assertEqual(json.loads((d / "dfa.json").read_text("utf-8")), RES.tables)  # Проверка корректности загрузки данных


class CaseFileTests(unittest.TestCase):  # Тестирование токенизатора на наборах входных тестов
    def test_cases_json(self):  # Запуск всех тестов из файла случаев по умолчанию
        results = run_cases(Lexer(RES.tables), load_cases(DEFAULT_CASES))  # Выполнение токенизации тестовых наборов
        for r in results:  # Проход по результатам каждого теста
            with self.subTest(r["name"]):  # Использование подтестов unittest для детального отчета
                self.assertEqual(r["status"], "PASS", r)  # Проверка, что тест завершился со статусом PASS


class SpecTests(unittest.TestCase):  # Тестирование парсера файлов спецификаций токенов
    def test_bad_specs(self):  # Проверка вызова ошибок на некорректных спецификациях
        for bad in ["", "X", "lower = a", "A = a\nA = b", "A @zzz = a", "A = (", "TRAP = a", "A ="]:  # Ошибочные строки спецификаций
            with self.assertRaises(SpecError, msg=bad):  # Ожидается исключение SpecError
                parse_spec(bad)  # Разбор синтаксически неверной спецификации

    def test_custom_spec(self):  # Проверка корректного разбора аннотаций (например, @skip)
        specs = parse_spec("# c\nAB = ab\nA_S @skip = a+\n")  # Разбор двухстрочной спецификации с комментарием
        self.assertEqual([(s.name, s.kind) for s in specs], [("AB", "token"), ("A_S", "skip")])  # Проверка полученных типов токенов


if __name__ == "__main__":  # Точка входа для прямого запуска файла с тестами
    unittest.main()  # Запуск встроенного запускчика тестов unittest