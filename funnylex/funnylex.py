from __future__ import annotations # Включает отложенную оценку аннотаций типов (поддержка ссылок на типы в будущем)

import argparse # Модуль для парсинга аргументов командной строки
import json # Модуль для работы с данными в формате JSON
import re # Модуль для работы с регулярными выражениями Python
import sys # Модуль для взаимодействия с системой (выход из программы, параметры среды)
import time # Модуль для измерения времени выполнения операций
from collections import deque # Двусторонняя очередь для быстрого обхода графа в ширину (BFS)
from dataclasses import dataclass, field # Декораторы и функции для удобного создания классов данных
from pathlib import Path # Класс для объективно-ориентированной работы с путями файловой системы
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple, Union # Набор типов для статической аннотации

from lexer import TRAP_KIND, Lexer # Импорт константы ловушки и класса лексера из внешнего модуля lexer.py

ALPHABET_SIZE = 128 # Размер базового алфавита ASCII (коды 0..127)
ASCII: FrozenSet[int] = frozenset(range(ALPHABET_SIZE)) # Неизменяемое множество всех кодов ASCII символов
OTHER = ALPHABET_SIZE # Специальный индекс-символ для представления любых не-ASCII символов
NUM_SYMBOLS = ALPHABET_SIZE + 1 # Полный размер алфавита автомата (128 ASCII + 1 OTHER)

ROOT = Path(__file__).resolve().parent # Абсолютный путь к директории текущего скрипта
DEFAULT_SPEC = ROOT / "funny.lex" # Путь по умолчанию к файлу спецификации токенов
DEFAULT_CASES = ROOT / "cases.json" # Путь по умолчанию к файлу с тестовыми кейсами
DEFAULT_OUT = ROOT / "build" # Путь по умолчанию к директории сгенерированных файлов


class RegexError(ValueError): # Пользовательское исключение для синтаксических ошибок в регулярных выражениях
    pass # Пустое тело класса


class SpecError(ValueError): # Пользовательское исключение для ошибок формата файла спецификации лексера
    pass # Пустое тело класса


@dataclass(frozen=True) # Иммаутбл-датакласс для узла пустой строки (эпсилон) в AST
class Epsilon:
    pass # Тело класса пустое, так как у эпсилон нет параметров


@dataclass(frozen=True) # Иммаутбл-датакласс для узла набора символов в AST
class CharSet:
    chars: FrozenSet[int] # Множество кодов символов, входящих в данный класс


@dataclass(frozen=True) # Иммаутбл-датакласс для операции конкатенации двух поддеревьев AST
class Concat:
    left: "Node" # Левый операнд конкатенации
    right: "Node" # Правый операнд конкатенации


@dataclass(frozen=True) # Иммаутбл-датакласс для операции альтернативы (выбор "|") в AST
class Alt:
    left: "Node" # Левая ветка альтернативы
    right: "Node" # Правая ветка альтернативы


@dataclass(frozen=True) # Иммаутбл-датакласс для замыкания Клини (повторение 0 и более раз "*") в AST
class Star:
    inner: "Node" # Внутреннее выражаемое поддерево


@dataclass(frozen=True) # Иммаутбл-датакласс для плюсовой трансляции (повторение 1 и более раз "+") в AST
class Plus:
    inner: "Node" # Внутреннее выражаемое поддерево


@dataclass(frozen=True) # Иммаутбл-датакласс для опционального элемента (повторение 0 или 1 раз "?") в AST
class Opt:
    inner: "Node" # Внутреннее выражаемое поддерево


Node = Union[Epsilon, CharSet, Concat, Alt, Star, Plus, Opt] # Определение типа Node как объединения всех видов узлов AST

_DIGITS = frozenset(range(ord("0"), ord("9") + 1)) # Множество ASCII-кодов цифр от '0' до '9'
_WORD = (_DIGITS | frozenset(range(ord("A"), ord("Z") + 1))
         | frozenset(range(ord("a"), ord("z") + 1)) | {ord("_")}) # Множество ASCII-кодов букв, цифр и подчёркивания
_SPACE = frozenset({9, 10, 11, 12, 13, 32}) # Множество ASCII-кодов пробельных символов (\t, \n, \v, \f, \r, пробел)
SIMPLE_ESCAPES = {"n": 10, "t": 9, "r": 13, "f": 12, "v": 11, "0": 0} # Маппинг управляющих эскейп-символов в их коды
CLASS_ESCAPES = {
    "d": _DIGITS, "D": ASCII - _DIGITS,
    "w": _WORD, "W": ASCII - _WORD,
    "s": _SPACE, "S": ASCII - _SPACE,
} # Маппинг специальных символьных классов (\d, \D, \w, \W, \s, \S) в соответствующие множества


class _RegexParser: # Парсер регулярного выражения методом рекурсивного спуска для получения AST
    def __init__(self, src: str):
        self.src = src # Исходная строка регулярного выражения
        self.pos = 0 # Указатель текущей позиции в строке

    def error(self, msg: str):
        raise RegexError(f"{msg} (позиция {self.pos} в {self.src!r})") # Вызывает ошибку с детализацией позиции

    def peek(self):
        return self.src[self.pos] if self.pos < len(self.src) else None # Читает текущий символ без перемещения указателя

    def next(self) -> str:
        ch = self.peek() # Считывает символ
        if ch is None:
            self.error("неожиданный конец выражения") # Бросает ошибку, если неожиданно достигнут конец строки
        self.pos += 1 # Продвигает указатель вперед
        return ch # Возвращает символ

    def code(self, ch: str) -> int:
        if ord(ch) >= ALPHABET_SIZE:
            self.error(f"символ {ch!r} вне алфавита ASCII") # Проверяет, что символ находится в пределах ASCII (0..127)
        return ord(ch) # Возвращает числовой код символа

    def parse(self) -> Node:
        node = self.alt() # Запускает разбор с корня грамматики (альтернативы)
        if self.pos != len(self.src):
            self.error(f"лишний символ {self.peek()!r} (несбалансированная ')'?)") # Ошибка, если после полного разбора остались символы
        return node # Возвращает итоговое дерево AST

    def alt(self) -> Node:
        node = self.concat() # Разбирает левую часть альтернативы (конкатенацию)
        while self.peek() == "|": # Пока идет разделитель ветвления '|'
            self.pos += 1 # Пропускает '|'
            node = Alt(node, self.concat()) # Связывает текущее поддерево и следующее через Alt
        return node # Возвращает узел альтернативы

    def concat(self) -> Node:
        node = None # Аккумулятор для сцепления элементов
        while self.peek() is not None and self.peek() not in "|)": # Пока не конец выражений или не закрывающая скобка/разделитель
            item = self.repeat() # Разбирает элемент с возможным квантификатором
            node = item if node is None else Concat(node, item) # Последовательно связывает элементы через Concat
        return node if node is not None else Epsilon() # Если подвыражение пустое, возвращает Epsilon

    def repeat(self) -> Node:
        node = self.atom() # Разбирает базовый атом
        while self.peek() is not None and self.peek() in "*+?": # При наличии квантификаторов *, +, ?
            node = {"*": Star, "+": Plus, "?": Opt}[self.next()](node) # Оборачивает узел в соответствующую структуру Star/Plus/Opt
        return node # Возвращает модифицированный квантификатором узел

    def atom(self) -> Node:
        ch = self.next() # Получает следующий символ
        if ch == "(": # Обработка группировки скобками
            node = self.alt() # Рекурсивно разбирает внутрискобочное выражение
            if self.peek() != ")": # Проверяет наличие закрывающей скобки
                self.error("ожидалась ')'")
            self.pos += 1 # Пропускает ')'
            return node # Возвращает поддерево скобочной группы
        if ch == "[": # Обработка символьного класса [...]
            return CharSet(self.char_class()) # Разбирает класс и возвращает CharSet
        if ch == ".": # Точка — любой ASCII символ кроме перевода строки
            return CharSet(ASCII - {10}) # Возвращает множество всех кодов кроме '\n' (код 10)
        if ch == "\\": # Экранирование символа
            return CharSet(self.escape()) # Разбирает эскейп-последовательность
        if ch in "*+?": # Ошибка при одиночном квантификаторе без операнда слева
            self.error(f"квантификатор {ch!r} без операнда")
        return CharSet(frozenset({self.code(ch)})) # Простой одиночный символ оборачивается в CharSet

    def escape(self) -> FrozenSet[int]:
        if self.peek() is None:
            self.error("незавершённая escape-последовательность") # Проверяет обрыв строки после '\'
        ch = self.next() # Читает символ после слэша
        if ch in SIMPLE_ESCAPES:
            return frozenset({SIMPLE_ESCAPES[ch]}) # Возвращает управляющий символ (\n, \t и т.д.)
        if ch in CLASS_ESCAPES:
            return CLASS_ESCAPES[ch] # Возвращает предустановленный класс символов (\d, \w и т.д.)
        if ch == "x": # Разбор 16-ричного кодирования \xHH
            digits = self.src[self.pos:self.pos + 2] # Выделяет 2 символа
            try:
                value = int(digits, 16) # Конвертирует из HEX в целое число
            except ValueError:
                value = -1 # Сигнал о некорректном формате
            if len(digits) != 2 or not 0 <= value < ALPHABET_SIZE:
                self.error("ожидалось \\xHH с кодом 00..7F") # Ошибка при неверном диапазоне или длине
            self.pos += 2 # Пропускает прочитанные HEX цифры
            return frozenset({value}) # Возвращает прочитанный код
        return frozenset({self.code(ch)}) # Обычный экранированный символ (например, '\+')

    def class_atom(self) -> FrozenSet[int]:
        ch = self.next() # Читает символ внутри квадратных скобок
        return self.escape() if ch == "\\" else frozenset({self.code(ch)}) # Если слэш — разбирает эскейп, иначе обычный символ

    def char_class(self) -> FrozenSet[int]:
        negate = self.peek() == "^" # Проверяет на инверсию класса [^...]
        if negate:
            self.pos += 1 # Пропускает '^'
        chars = set() # Аккумулятор символов класса
        first = True # Флаг первого символа (символ ']' в начале интерпретируется как символ)
        while True:
            ch = self.peek() # Смотрит текущий символ
            if ch is None:
                self.error("незакрытый '['") # Ошибка обрыва символьного класса
            if ch == "]" and not first:
                self.pos += 1 # Пропускает ']'
                break # Завершает сбор класса
            first = False # Сбрасывает флаг первого символа
            lo = self.class_atom() # Разбирает левую границу возможного диапазона
            if (self.peek() == "-" and self.pos + 1 < len(self.src)
                    and self.src[self.pos + 1] != "]"): # Если следует гифен '-' и за ним не ']'
                self.pos += 1 # Пропускает '-'
                hi = self.class_atom() # Разбирает правую границу диапазона
                if len(lo) != 1 or len(hi) != 1:
                    self.error("границы диапазона должны быть одиночными символами") # Нельзя строить диапазон над множествами типа \d
                a, b = min(lo), min(hi) # Получает числовые границы
                if a > b:
                    self.error(f"пустой диапазон {chr(a)!r}-{chr(b)!r}") # Левая граница должна быть меньше или равна правой
                chars.update(range(a, b + 1)) # Добавляет весь диапазон кодов символов
            else:
                chars |= lo # Добавляет одиночный символ/множество в класс
        result = ASCII - chars if negate else frozenset(chars) # Инвертирует относительно ASCII при флаговом '^'
        if not result:
            self.error("пустой класс символов") # Класс символов не может быть пустым
        return result # Возвращает итоговое множество кодов символов


def parse_regex(src: str) -> Node:
    return _RegexParser(src).parse() # Функция-обёртка для парсинга регулярки в AST


@dataclass
class TokenSpec: # Класс спецификации описания одного токена
    name: str # Имя токена (например, IDENT)
    regex: str # Исходная строка регулярного выражения
    kind: str # Тип действия (token, skip, error)
    ast: Node # Построенное AST регулярного выражения


_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$") # Регулярка для проверки валидности имени токена


def parse_spec(text: str, source: str = "<spec>") -> List[TokenSpec]:
    specs: List[TokenSpec] = [] # Список распарсенных токенов
    names = set() # Множество имён для контроля уникальности
    for lineno, raw in enumerate(text.splitlines(), 1): # Читает файл спецификации построчно
        line = raw.strip() # Очищает от краевых пробелов
        if not line or line.startswith("#"): # Пропускает пустые строки и комментарии
            continue
        where = f"{source}:{lineno}" # Префикс для вывода локализации ошибки
        if "=" not in line:
            raise SpecError(f"{where}: ожидалось 'ИМЯ [@флаг] = regex'") # Проверка наличия знака присваивания
        head, regex = line.split("=", 1) # Делит строку на заголовок и регулярку
        regex = regex.strip() # Очищает регулярку от лишних пробелов
        words = head.split() # Разбивает левую часть на элементы
        if not words:
            raise SpecError(f"{where}: не указано имя токена")
        name, flags = words[0], words[1:] # Извлекает имя токена и его флаги
        if not _NAME_RE.match(name):
            raise SpecError(f"{where}: недопустимое имя токена {name!r}") # Проверяет имя на соответствие _NAME_RE
        if name in names or name == TRAP_KIND:
            raise SpecError(f"{where}: имя {name!r} уже занято") # Проверяет уникальность имени токена
        kind = "token" # Значение категории токена по умолчанию
        for flag in flags: # Валидация и парсинг флагов
            if flag not in ("@skip", "@error"):
                raise SpecError(f"{where}: неизвестный флаг {flag!r}")
            kind = flag[1:] # Сохраняет "skip" или "error" без символа '@'
        if not regex:
            raise SpecError(f"{where}: пустое регулярное выражение")
        try:
            ast = parse_regex(regex) # Преобразует регулярку в AST
        except RegexError as exc:
            raise SpecError(f"{where}: {exc}") from None # Оборачивает ошибку парсинга регулярки в SpecError
        names.add(name) # Добавляет имя токена в список занятых
        specs.append(TokenSpec(name, regex, kind, ast)) # Сохраняет готовую спецификацию
    if not specs:
        raise SpecError(f"{source}: нет ни одного токена") # Ошибка, если спецификация пустая
    return specs # Возвращает список спецификаций токенов


def load_spec(path) -> List[TokenSpec]:
    path = Path(path) # Оборачивает путь в объект Path
    return parse_spec(path.read_text(encoding="utf-8"), str(path)) # Загружает содержимое файла и парсит его


class NFA: # Класс Недетерминированного Конечного Автомата (НКА)
    def __init__(self):
        self.eps: List[List[int]] = [] # Таблица эпсилон-переходов: eps[state] = [target_state1, ...]
        self.edge: List[Optional[Tuple[FrozenSet[int], int]]] = [] # Таблица переходов по символам: edge[state] = (symbols, target_state)
        self.accept: Dict[int, int] = {} # Таблица финишных состояний: state -> index_token
        self.start: int = -1 # Индекс начального состояния

    def __len__(self) -> int:
        return len(self.eps) # Общее число состояний НКА

    def add_state(self) -> int:
        self.eps.append([]) # Добавляет список для эпсилон-переходов нового состояния
        self.edge.append(None) # Добавляет пустое место под символьный переход
        return len(self.eps) - 1 # Возвращает индекс нового состояния

    def fragment(self, node: Node) -> Tuple[int, int]: # Алгоритм Томпсона построения фрагмента НКА по AST
        if isinstance(node, Concat): # Конкатенация
            s1, f1 = self.fragment(node.left) # Фрагмент левой части
            s2, f2 = self.fragment(node.right) # Фрагмент правой части
            self.eps[f1].append(s2) # Связывает финиш левого фрагмента со стартом правого через ε-переход
            return s1, f2 # Возвращает новые старт и финиш
        s, f = self.add_state(), self.add_state() # Создает пару узлов старта и финиша
        if isinstance(node, Epsilon): # Пустая строка
            self.eps[s].append(f) # Добавляет прямой ε-переход
        elif isinstance(node, CharSet): # Символьный класс
            self.edge[s] = (node.chars, f) # Переход из s в f по символам из множества
        elif isinstance(node, Alt): # Альтернатива (|)
            for part in (node.left, node.right):
                s1, f1 = self.fragment(part) # Строит фрагмент ветви
                self.eps[s].append(s1) # Разветвляет старт на ветку
                self.eps[f1].append(f) # Сводит финиш ветки в общий финиш
        elif isinstance(node, (Star, Plus, Opt)): # Квантификаторы повторения
            s1, f1 = self.fragment(node.inner) # Строит фрагмент внутреннего выражения
            self.eps[s].append(s1) # Вход во внутренний фрагмент
            if not isinstance(node, Plus):
                self.eps[s].append(f) # Обход фрагмента для Star и Opt
            if not isinstance(node, Opt):
                self.eps[f1].append(s1) # Зацикливание из финиша в старт для Star и Plus
            self.eps[f1].append(f) # Выход из внутреннего фрагмента в общий финиш
        else:
            raise TypeError(f"неизвестный узел AST: {node!r}")
        return s, f # Возвращает точки входа и выхода фрагмента

    def epsilon_closure(self, states: Iterable[int]) -> FrozenSet[int]: # Вычисление эпсилон-замыкания множества состояний
        seen = set(states) # Множество всех достижимых состояний по ε-переходам
        stack = list(seen) # Стек для обхода графа
        while stack:
            for t in self.eps[stack.pop()]: # Проверяет все ε-выходы текущего состояния
                if t not in seen:
                    seen.add(t) # Фиксирует новое состояние
                    stack.append(t) # Помещает в стек для раскрытия его выходов
        return frozenset(seen) # Возвращает итоговое ε-замыкание

    def move(self, states: Iterable[int], symbol: int) -> set: # Переходы из заданных состояний по конкретному символу
        return {e[1] for e in (self.edge[s] for s in states) if e is not None and symbol in e[0]}

    def match(self, text: str) -> Optional[int]: # Прогоняет строку по НКА
        current = self.epsilon_closure([self.start]) # Вычисляет начальное ε-замыкание
        for ch in text:
            current = self.epsilon_closure(self.move(current, ord(ch))) # Переход по символу + ε-замыкание
            if not current:
                return None # Не дошли до конца
        tokens = [self.accept[s] for s in current if s in self.accept] # Сбор токенов из финишных состояний
        return min(tokens) if tokens else None # Приоритет отдаётся токену с меньшим индексом


def build_nfa(asts: Sequence[Node]) -> NFA: # Объединение AST всех правил токенов в единый НКА
    nfa = NFA() # Инициализация НКА
    nfa.start = nfa.add_state() # Создание единой начальной точки
    for index, ast in enumerate(asts):
        s, f = nfa.fragment(ast) # Построение НКА для каждого токена
        nfa.eps[nfa.start].append(s) # Связывание единого старта со стартом правила ε-переходом
        nfa.accept[f] = index # Регистрация принимающего состояния с индексом токена
    return nfa # Возвращает объединённый НКА


def symbol_of(ch: str) -> int: # Отображает символ в код ASCII или индекс OTHER
    return ord(ch) if ord(ch) < ALPHABET_SIZE else OTHER


@dataclass
class DFA: # Класс Детерминированного Конечного Автомата (ДКА)
    trans: List[List[int]] # Двумерная таблица переходов: trans[state][symbol_index] -> target_state
    start: int # Стартовое состояние
    trap: int # Состояние-ловушка (состояние неуспеха)
    accept: Dict[int, int] = field(default_factory=dict) # Карта финишных состояний: state -> index_token

    @property
    def num_states(self) -> int:
        return len(self.trans) # Количество состояний ДКА

    def match(self, text: str) -> Optional[int]: # Симуляция работы ДКА на строке
        state = self.start # Начинает со стартового состояния
        for ch in text:
            state = self.trans[state][symbol_of(ch)] # Переход по символу
        return self.accept.get(state) # Возвращает токен, если состояние финишное


def subset_construction(nfa: NFA) -> DFA: # Детерминизация НКА -> ДКА (Алгоритм построения подмножеств)
    start_set = nfa.epsilon_closure([nfa.start]) # Вычисляет эпсилон-замыкание старта НКА
    sets: List[FrozenSet[int]] = [start_set, frozenset()] # Список состояний ДКА (0 - старт, 1 - ловушка)
    index: Dict[FrozenSet[int], int] = {start_set: 0, frozenset(): 1} # Отображение: множество НКА -> состояние ДКА
    trans: List[List[int]] = [] # Таблица переходов будущего ДКА
    i = 0
    while i < len(sets): # Пока остаются необработанные состояния ДКА
        row = [1] * NUM_SYMBOLS # Инициализирует переходы ловушками (state=1)
        moves: List[set] = [set() for _ in range(ALPHABET_SIZE)] # Сбор переходов по всем символам ASCII
        for s in sets[i]:
            e = nfa.edge[s]
            if e is not None:
                for c in e[0]:
                    moves[c].add(e[1]) # Записывает доступные состояния НКА по символу c
        cache: Dict[FrozenSet[int], FrozenSet[int]] = {} # Кэш вычислительной функции эпсилон-замыканий
        for c in range(ALPHABET_SIZE):
            m = frozenset(moves[c]) # Переходы по символу c
            if not m:
                continue
            if m not in cache:
                cache[m] = nfa.epsilon_closure(m) # Вычисляет closure при отсутствии в кэше
            u = cache[m]
            if u not in index:
                index[u] = len(sets) # Регистрирует новое уникальное состояние ДКА
                sets.append(u)
            row[c] = index[u] # Сохраняет переход в строку таблицы
        trans.append(row) # Добавляет сформированную строку переходов
        i += 1
    accept = {} # Определение принимающих состояний ДКА
    for state, nfa_states in enumerate(sets):
        tokens = [nfa.accept[s] for s in nfa_states if s in nfa.accept] # Находит токены принимающих НКА состояний
        if tokens:
            accept[state] = min(tokens) # Присваивает токен с минимальным индексом (высший приоритет)
    return DFA(trans=trans, start=0, trap=1, accept=accept) # Возвращает сформированный ДКА


def reachable_states(dfa: DFA) -> List[int]: # Поиск всех достижимых из старта состояний ДКА (BFS)
    order, seen = [dfa.start], {dfa.start} # Список порядка и сет посещенных состояний
    queue = deque(order) # Очередь обхода
    while queue:
        for t in dfa.trans[queue.popleft()]: # Обходит выходы текущего состояния
            if t not in seen:
                seen.add(t) # Регистрирует новое состояние
                order.append(t)
                queue.append(t) # Добавляет в очередь
    return order # Возвращает порядок достижимых состояний


def hopcroft_minimize(dfa: DFA) -> DFA: # Минимизация ДКА по алгоритму Хопкрофта
    states = reachable_states(dfa) # Исключает недостижимые состояния
    groups: Dict[int, set] = {} # Разделяет состояния по классам финишных токенов (-1 для непринимающих)
    for s in states:
        groups.setdefault(dfa.accept.get(s, -1), set()).add(s)
    partition: List[FrozenSet[int]] = [frozenset(g) for g in groups.values()] # Начальное разбиение автомата
    work = set(partition) # Очередь сплиттеров (рабочий набор)
    inv: List[Dict[int, List[int]]] = [dict() for _ in range(NUM_SYMBOLS)] # Обратные переходы: symbol -> target_state -> [source_states]
    for s in states:
        for a, t in enumerate(dfa.trans[s]):
            inv[a].setdefault(t, []).append(s) # Строит обратные связи для ускорения сплитинга

    while work: # Алгоритм разделения эквивалентных групп
        splitter = work.pop() # Достаёт сплиттер
        for a in range(NUM_SYMBOLS):
            x = set() # Состояния, ведущие в сплиттер по символу a
            for t in splitter:
                x.update(inv[a].get(t, ()))
            if not x:
                continue
            refined: List[FrozenSet[int]] = [] # Новое разбиение
            for y in partition:
                inter = y & x # Пересечение множеств
                if inter and len(inter) < len(y): # Если класс делится на части
                    diff = y - inter # Оставшаяся часть
                    refined += [inter, diff] # Разделяет на два новых класса
                    if y in work:
                        work.discard(y)
                        work.update((inter, diff)) # Обновляет рабочий набор сплиттеров
                    else:
                        work.add(inter if len(inter) <= len(diff) else diff) # Добавляет меньшую часть в сплиттеры
                else:
                    refined.append(y) # Оставляет класс как есть
            partition = refined # Применяет новое разбиение

    block_of = {s: b for b, block in enumerate(partition) for s in block} # Таблица: состояние -> номер его эквивалентного блока
    rep = {b: min(block) for b, block in enumerate(partition)} # Выбор представителя от каждого блока
    new_id = {block_of[dfa.start]: 0} # Перенумерация состояний, где старт = 0
    queue = deque([block_of[dfa.start]])
    while queue: # Каноническая перенумерация через BFS для компактности
        for t in dfa.trans[rep[queue.popleft()]]:
            tb = block_of[t]
            if tb not in new_id:
                new_id[tb] = len(new_id) # Назначает следующий номер состояния
                queue.append(tb)
    trans = [[] for _ in new_id] # Таблица переходов минимального ДКА
    accept = {} # Принимающие состояния нового ДКА
    for b, nid in new_id.items():
        s = rep[b]
        trans[nid] = [new_id[block_of[t]] for t in dfa.trans[s]] # Построение новых переходов
        if s in dfa.accept:
            accept[nid] = dfa.accept[s] # Перенос отметок финишных токенов
    return DFA(trans=trans, start=0, trap=new_id[block_of[dfa.trap]], accept=accept) # Возвращает скомпонованный минимальный ДКА


def moore_class_count(dfa: DFA) -> int: # Подсчёт числа классов эквивалентности алгоритмом Мура
    states = reachable_states(dfa) # Сбор всех достижимых состояний
    label = {s: dfa.accept.get(s, -1) for s in states} # Первичная разметка по токенам
    count = len(set(label.values())) # Стартовое количество уникальных классов
    while True:
        signature: Dict[tuple, int] = {} # Словарь сигнатур (текущая метка + переходы)
        new_label = {s: signature.setdefault((label[s], tuple(label[t] for t in dfa.trans[s])),
                                             len(signature)) for s in states} # Генерация новых меток
        if len(signature) == count:
            return count # Возвращает количество классов при стабилизации
        count, label = len(signature), new_label # Переход к следующей итерации


def _fmt(c: int) -> str: # Вспомогательное форматирование кодов символов для человекочитаемого отчета
    special = {9: "\\t", 10: "\\n", 13: "\\r", 32: "␠"} # Экранирование спецификаторов whitespace
    if c in special:
        return special[c]
    if 33 <= c < 127:
        return "\\" + chr(c) if chr(c) in "\\]-^" else chr(c) # Экранирует управляющие символы классов
    return f"\\x{c:02x}" # Вывод непечатных символов в HEX


def describe(symbols: Sequence[int]) -> str: # Формирует текстовое описание набора символов (например, [a-z])
    codes = sorted(s for s in symbols if s < ALPHABET_SIZE) # Сортировка ASCII кодов
    parts, i = [], 0
    while i < len(codes): # Сворачивание непрерывных последовательностей кодов в диапазон
        j = i
        while j + 1 < len(codes) and codes[j + 1] == codes[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{_fmt(codes[i])}-{_fmt(codes[j])}") # Записывает в формате 'start-end'
        else:
            parts.extend(_fmt(c) for c in codes[i:j + 1]) # Перечисляет символы через запятую
        i = j + 1
    text = "".join(parts)
    text = f"[{text}]" if len(codes) > 1 else text # Оборачивает в [...] если элементов несколько
    if OTHER in symbols:
        text = (text + " + " if text else "") + "<non-ASCII>" # Добавляет отметку о присутствии не-ASCII символов
    return text # Возвращает итоговую строку описание класса


def to_tables(dfa: DFA, specs: Sequence[TokenSpec]) -> dict: # Упаковка ДКА в экспортную JSON-структуру с компрессией алфавита
    column_id: Dict[tuple, int] = {} # Поиск дублирующихся столбцов таблицы переходов
    class_of: List[int] = [] # Отображение: символ -> ID символьного класса
    members: List[List[int]] = [] # Список символов, входящих в каждый класс
    for a in range(NUM_SYMBOLS):
        cid = column_id.setdefault(tuple(row[a] for row in dfa.trans), len(column_id)) # Дедупликация столбцов переходов
        if cid == len(members):
            members.append([]) # Создает запись нового класса
        members[cid].append(a) # Заносит символ в текущий класс
        class_of.append(cid) # Фиксирует привязку класса
    return { # Возвращает словарь автомата с готовыми экспортными полями
        "format": "funnylex-dfa/1",
        "alphabet": "ASCII (0..127) + OTHER для всего остального",
        "tokens": [{"name": s.name, "kind": s.kind, "regex": s.regex} for s in specs],
        "num_states": dfa.num_states,
        "num_classes": len(members),
        "start": dfa.start,
        "trap": dfa.trap,
        "char_class": class_of[:ALPHABET_SIZE],
        "other_class": class_of[OTHER],
        "classes": [describe(m) for m in members],
        "transitions": [[row[m[0]] for m in members] for row in dfa.trans],
        "accept": [specs[dfa.accept[s]].name if s in dfa.accept else None
                   for s in range(dfa.num_states)],
    }


def write_json(tables: dict, path: Path) -> None:
    path.write_text(json.dumps(tables, ensure_ascii=False, indent=1) + "\n", encoding="utf-8") # Сохраняет JSON в файл


@dataclass
class BuildResult: # Датакласс хранения промежуточных и итоговых структур процесса сборки
    specs: List[TokenSpec]
    nfa: NFA
    dfa: DFA
    min_dfa: DFA
    tables: dict
    stats: dict


def build(spec_path=DEFAULT_SPEC) -> BuildResult: # Полный цикл компиляции спецификации в сжатый ДКА
    t0 = time.perf_counter() # Фиксация времени старта
    specs = load_spec(spec_path) # 1. Загрузка спецификаций
    nfa = build_nfa([s.ast for s in specs]) # 2. Генерация объединенного НКА
    dfa = subset_construction(nfa) # 3. Преобразование НКА -> ДКА
    min_dfa = hopcroft_minimize(dfa) # 4. Минимизация ДКА
    tables = to_tables(min_dfa, specs) # 5. Генерация сжатых таблиц
    stats = { # Сбор сводной статистики по этапам
        "tokens": len(specs),
        "nfa_states": len(nfa),
        "dfa_states": dfa.num_states,
        "min_dfa_states": min_dfa.num_states,
        "alphabet_symbols": NUM_SYMBOLS,
        "char_classes": tables["num_classes"],
        "table_cells_full": min_dfa.num_states * NUM_SYMBOLS,
        "table_cells_compressed": min_dfa.num_states * tables["num_classes"],
        "build_seconds": round(time.perf_counter() - t0, 3),
    }
    return BuildResult(specs, nfa, dfa, min_dfa, tables, stats) # Возвращает результат сборки


def load_cases(path) -> List[dict]: # Загружает тесты из JSON и достраивает покрытие для всех ASCII символов
    data = json.loads(Path(path).read_text(encoding="utf-8")) # Чтение файла тестов
    cases = [dict(c, group="manual") for c in data["cases"]] # Добавление ручных кейсов с группой "manual"
    cov = data.get("ascii_coverage") # Получение таблицы покрытия ASCII
    if cov:
        default = cov.get("@default", TRAP_KIND) # Определение дефолтного результата для неперечисленных символов
        mapping = {}
        for kind, chars in cov.items():
            if kind == "@default":
                continue
            for ch in chars:
                if ord(ch) >= 128 or ch in mapping:
                    raise ValueError(f"ascii_coverage: символ {ch!r} некорректен или повторяется") # Валидация ASCII символов
                mapping[ch] = kind
        for code in range(128): # Автоматическая генерация тестов на каждый из 128 ASCII символов
            ch = chr(code)
            kind = mapping.get(ch, default)
            cases.append({"name": f"ascii {code:3d} {ch!r}", "input": ch,
                          "expect": [] if kind == "@skip" else [[kind, ch]],
                          "negative": kind == TRAP_KIND, "group": "ascii-coverage"})
    return cases # Возвращает полный список тестов


def run_cases(lexer: Lexer, cases: List[dict]) -> List[dict]: # Прогоняет все тесты через лексер
    results = []
    for case in cases:
        tokens = lexer.tokenize(case["input"]) # Токенизация входной строки
        got = [[t.kind, t.lexeme] for t in tokens] # Извлечение результата в виде списков [вид, лексема]
        has_error = any(t.is_error for t in tokens) # Проверка наличия ошибки лексера
        ok = got == case["expect"] and has_error == case["negative"] # Сопоставление результата с ожиданием
        results.append({"name": case["name"], "group": case["group"],
                        "input": case["input"], "negative": case["negative"],
                        "expect": case["expect"], "got": got,
                        "errors": [t.error for t in tokens if t.is_error],
                        "status": "PASS" if ok else "FAIL"}) # Запись результатов прогона
    return results # Возвращает список отчетов по каждому тесту


def cmd_build(args) -> int: # Команда CLI: сборка автомата и вывод сводки
    res = build(args.spec) # Запускает сборку
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True) # Создает выходную директорию
    write_json(res.tables, out / "dfa.json") # Сохраняет dfa.json
    s = res.stats # Выводит метрики
    print(f"токенов: {s['tokens']}")
    print(f"НКА:             {s['nfa_states']:4d} состояний")
    print(f"ДКА:             {s['dfa_states']:4d} состояний (вкл. ловушку)")
    print(f"минимальный ДКА: {s['min_dfa_states']:4d} состояний (вкл. ловушку, trap={res.tables['trap']})")
    print(f"классов символов: {s['char_classes']} (из {NUM_SYMBOLS})")
    print(f"автомат записан в {out / 'dfa.json'}")
    return 0 # Успешный код завершения


def cmd_test(args) -> int: # Команда CLI: прогон тестов
    lexer = Lexer(json.loads(json.dumps(build(args.spec).tables))) # Строит автомат и создает лексер
    results = run_cases(lexer, load_cases(args.cases)) # Прогоняет кейсы
    for r in results:
        if r["group"] == "ascii-coverage" and r["status"] == "PASS" and not args.verbose:
            continue # Пропускает вывод пройденных ASCII-тестов при отсутствии флага -v
        sign = "-" if r["negative"] else "+"
        got = " ".join(f"{k}:{l!r}" if k in ("IDENT", "INT", TRAP_KIND) or r["negative"] else k
                       for k, l in r["got"]) or "∅"
        shown = repr(r["input"])
        shown = shown if len(shown) <= 28 else shown[:25] + "..." # Форматирует длину строки ввода
        print(f"{r['status']} [{sign}] {r['name']:<34} {shown:<28} → {got}") # Выводит строку статуса теста
        if r["status"] == "FAIL":
            print(f"        ожидалось: {r['expect']}") # При провале печатает ожидаемое значение
    passed = sum(r["status"] == "PASS" for r in results) # Количество пройденных тестов
    pos = [r for r in results if not r["negative"]] # Положительные тесты
    neg = [r for r in results if r["negative"]] # Отрицательные тесты
    cov = [r for r in results if r["group"] == "ascii-coverage"] # Тесты покрытия
    print()
    print(f"ASCII-покрытие: {sum(r['status'] == 'PASS' for r in cov)}/{len(cov)} символов "
          f"(показаны только провалы; -v для всех)")
    print(f"положительных: {sum(r['status'] == 'PASS' for r in pos)}/{len(pos)}, "
          f"отрицательных: {sum(r['status'] == 'PASS' for r in neg)}/{len(neg)}")
    print(f"ИТОГО: {passed}/{len(results)} PASS") # Итоговый отчет
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_results.json").write_text(
        json.dumps({"passed": passed, "total": len(results), "results": results},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8") # Сохраняет результаты тестов в JSON
    return 0 if passed == len(results) else 1 # Возвращает 0 только если все тесты прошел PASS


def cmd_lex(args) -> int: # Команда CLI: токенизация входной строки или файла
    lexer = Lexer.from_json(args.tables) if args.tables else Lexer(build(args.spec).tables) # Загружает или собирает лексер
    text = args.expr if args.expr is not None else \
        Path(args.file).read_bytes().decode("utf-8", errors="replace") # Получает текст для анализа из -e или из файла
    tokens = lexer.tokenize(text, keep_skipped=args.all) # Разбирает текст на токены
    for t in tokens:
        print(f"{t.kind:<16} {t.lexeme!r}" + (f"   ! {t.error}" if t.is_error else "")) # Печатает полученный список токенов
    return 1 if any(t.is_error for t in tokens) else 0 # Возвращает 1, если была хоть одна ошибка токенизации


def main(argv=None) -> int: # Главная функция разбора аргументов командной строки и маршрутизации
    p = argparse.ArgumentParser(prog="python funnylex.py",
                                description="regex → НКА → ДКА → min ДКА для языка Funny") # Парсер параметров
    p.add_argument("--spec", default=str(DEFAULT_SPEC), help="файл с регулярками токенов") # Общий флаг спецификации
    sub = p.add_subparsers(dest="cmd", required=True) # Добавляет подкоманды

    b = sub.add_parser("build", help="построить автомат и экспортировать таблицы") # Подкоманда 'build'
    b.add_argument("--out", default=str(DEFAULT_OUT))
    b.set_defaults(func=cmd_build)

    for name, func, hlp in (("test", cmd_test, "прогнать cases.json через ДКА"),
                            ("all", lambda ns: cmd_build(ns) or cmd_test(ns), "build + test")): # Подкоманды 'test' и 'all'
        t = sub.add_parser(name, help=hlp)
        t.add_argument("--cases", default=str(DEFAULT_CASES))
        t.add_argument("--out", default=str(DEFAULT_OUT))
        t.add_argument("-v", "--verbose", action="store_true")
        t.set_defaults(func=func)

    lx = sub.add_parser("lex", help="разбить строку/файл на токены") # Подкоманда 'lex'
    src = lx.add_mutually_exclusive_group(required=True) # Ограничитель: либо строка (-e), либо файл
    src.add_argument("-e", "--expr", help="входная строка")
    src.add_argument("file", nargs="?", help="входной файл")
    lx.add_argument("--tables", help="готовый dfa.json вместо сборки")
    lx.add_argument("--all", action="store_true", help="показывать и skip-токены")
    lx.set_defaults(func=cmd_lex)

    args = p.parse_args(argv) # Выполняет разбор переданных CLI аргументов
    return args.func(args) # Вызывает функцию соответствующего обработчика подкоманды


if __name__ == "__main__": # Точка входа при прямом запуске файла
    sys.exit(main()) # Вызывает main() и передает его результат ОС