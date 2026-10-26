from __future__ import annotations # Включает отложенную оценку аннотаций типов (поддержка ссылок на типы из будущего)

import json # Модуль для работы с форматом JSON (загрузка сгенерированных таблиц ДКА)
from dataclasses import dataclass # Декоратор для автоматического сгенерированного класса данных
from pathlib import Path # Объектно-ориентированная работа с путями файловой системы
from typing import List, Optional, Tuple # Типы для статической аннотации (списки, опциональные значения, кортежи)

TRAP_KIND = "TRAP" # Константа имени типа токена при попадании в ошибку/ловушку


@dataclass(frozen=True) # Декоратор иммаутабельного датакласса (запрет на изменение полей токена после создания)
class Token: # Класс для представления одного разобранного токена
    kind: str # Имя типа токена (например, "IDENT", "INT", "TRAP")
    lexeme: str # Текстовое значение (фрагмент исходной строки), соответствующее токену
    error: Optional[str] = None # Текст ошибки, если токен является ошибочным или попал в ловушку

    @property # Декоратор свойства для динамического вычисления состояния ошибки
    def is_error(self) -> bool: # Метод проверки, содержит ли токен сообщение об ошибке
        return self.error is not None # Возвращает True, если зафиксирована ошибка


class Lexer: # Класс лексического анализатора (лексера), работающий на сжатых таблицах ДКА
    def __init__(self, tables: dict): # Конструктор лексера, принимающий словарь с описанием ДКА
        self.char_class: List[int] = tables["char_class"] # Массив отображения ASCII-кодов (0..127) в ID классов эквивалентности
        self.other_class: int = tables["other_class"] # Идентификатор класса символов для не-ASCII символов (>= 128)
        self.trans: List[List[int]] = tables["transitions"] # Таблица переходов ДКА: trans[state][class_id] -> next_state
        self.start: int = tables["start"] # Номер начального состояния автомата
        self.trap: int = tables["trap"] # Номер состояния-ловушки (состояние неуспеха)
        self.accept: List[Optional[str]] = tables["accept"] # Список финишных состояний с именами распознаваемых токенов
        self.kind = {t["name"]: t["kind"] for t in tables["tokens"]} # Карта соответствия имени токена его категории (token, skip, error)

    @classmethod # Декоратор метода класса (альтернативный конструктор)
    def from_json(cls, path) -> "Lexer": # Метод создания экземпляра лексера из файла JSON с таблицами ДКА
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))) # Читает JSON-файл и передаёт словарь в __init__

    def _class(self, ch: str) -> int: # Вспомогательный метод определения класса символа
        c = ord(ch) # Получение числового кода Юникод-символа
        return self.char_class[c] if c < len(self.char_class) else self.other_class # Возвращает класс ASCII или other_class для не-ASCII

    def longest_match(self, text: str, pos: int) -> Tuple[Optional[str], int]: # Алгоритм поиска самого длинного совпадения (Maximal Munch)
        state, best, end = self.start, None, pos # Инициализация текущего состояния, лучшего найденного токена и его позиции
        for i in range(pos, len(len_text := text)): # Посимвольный проход по тексту начиная с текущей позиции pos
            state = self.trans[state][self._class(text[i])] # Вычисление нового состояния ДКА по классу текущего символа
            if state == self.trap: # Проверка на сваливание автомата в ловушку
                break # Прерывает дальнейший поиск, так как продолжение невозможно
            if self.accept[state] is not None: # Проверка, является ли текущее состояние принимающим (финишным)
                best, end = self.accept[state], i + 1 # Фиксирует наилучшее найденное имя токена и позицию конца лексемы
        return best, end # Возвращает имя распознанного токена высшего приоритета и индекс конца лексемы

    def tokenize(self, text: str, keep_skipped: bool = False) -> List[Token]: # Главный метод разбиения входного текста на токены
        tokens: List[Token] = [] # Итоговый список выделенных токенов
        pos = 0 # Указатель текущей позиции считывания в тексте
        while pos < len(text): # Цикл обработки пока не достигнут конец текста
            name, end = self.longest_match(text, pos) # Ищет самое длинное правило, совпадающее от текущей позиции
            if name is None: # Если ни одно правило не совпало (неизвестный символ / тупик)
                ch = text[pos] # Извлекает непрочитанный символ
                if ord(ch) >= 128: # Проверяет, является ли символ внедиапазонным не-ASCII
                    msg = f"символ U+{ord(ch):04X} вне алфавита ASCII → ловушка" # Формирует сообщение для символов не из ASCII
                else: # Если символ входит в ASCII
                    msg = f"нет перехода по символу {ch!r} → ловушка" # Сообщение о невозможности продолжить переход в ДКА
                tokens.append(Token(TRAP_KIND, ch, msg)) # Регистрирует ошибочный токен-ловушку
                pos += 1 # Продвигается на один символ вперед для продолжения разбора
                continue # Переходит к следующей итерации цикла
            lexeme = text[pos:end] # Выделяет подстроку-лексему найденного токена
            kind = self.kind[name] # Получает категорию токена (token, skip, error)
            if kind == "error": # Если правило помечено флагом @error
                tokens.append(Token(name, lexeme, f"недопустимая лексема {lexeme!r} ({name})")) # Записывает как явный токен ошибки
            elif kind == "token" or keep_skipped: # Если это стандартный токен или включен режим сохранения пробелов (@skip)
                tokens.append(Token(name, lexeme)) # Записывает корректный токен
            pos = end # Сдвигает указатель разбора на позицию окончания текущего токена
        return tokens # Возвращает сформированный список всех токенов