KW_FUNCTION  = function
KW_RETURNS   = returns
KW_WHILE     = while
KW_IF        = if
KW_ELSE      = else
KW_ASSERT    = assert
KW_ASSUME    = assume
KW_INVARIANT = invariant
KW_LENGTH    = length

IDENT        = [A-Za-z_][A-Za-z0-9_]*
INT          = 0|[1-9][0-9]*
INT_LEADING_ZERO @error = 0[0-9]+

WS      @skip = [ \t\r\n]+
COMMENT @skip = //[^\r\n]*

EQ     = ==
NE     = !=
LE     = <=
GE     = >=
LT     = <
GT     = >
ASSIGN = =
PLUS   = \+
MINUS  = -
STAR   = \*
SLASH  = /

LPAREN   = \(
RPAREN   = \)
LBRACKET = \[
RBRACKET = \]
LBRACE   = \{
RBRACE   = \}
COMMA    = ,
SEMI     = ;
COLON    = :
