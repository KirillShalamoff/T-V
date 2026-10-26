# Пробелы и комментарии (пропускаются лексером)
WS           @skip  = [ \t\r\n]+
LINE_COMMENT @skip  = //[^\n]*

# Ключевые слова языка Funny (идут ПЕРЕД IDENT для приоритета в ДКА)
FUNCTION            = function
RETURNS             = returns
REQUIRES            = requires
ENSURES             = ensures
IF                  = if
ELSE                = else
WHILE               = while
ASSERT              = assert
ASSUME              = assume
TRUE                = true
FALSE               = false
OR                  = or
AND                 = and
NOT                 = not
INT_TYPE            = int
BOOL_TYPE           = bool

# Многосимвольные операторы (идут ПЕРЕД односимвольными для Maximal Munch)
IMPLIES             = ==>
EQ                  = ==
NEQ                 = !=
LE                  = <=
GE                  = >=
AND_SYM             = &&
OR_SYM              = \|\|

# Односимвольные операторы и разделители
ASSIGN              = =
LT                  = <
GT                  = >
PLUS                = \+
MINUS               = -
STAR                = \*
SLASH               = /
PERCENT             = %
BANG                = !
LPAREN              = \(
RPAREN              = \)
LBRACE              = \{
RBRACE              = \}
LBRACKET            = \[
RBRACKET            = \]
COLON               = :
SEMI                = ;
COMMA               = ,

# Ошибочные лексемы (число, слипшееся с идентификатором)
BAD_IDENT    @error = [0-9]+[a-zA-Z_][a-zA-Z0-9_]*

# Литералы и идентификаторы
INT                 = 0|[1-9][0-9]*
IDENT               = [a-zA-Z_][a-zA-Z0-9_]*
