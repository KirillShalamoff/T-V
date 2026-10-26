from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ast_nodes import format_tree
from funnylex import DEFAULT_SPEC, build
from lexer import Lexer
from parser import parse_text

ROOT = Path(__file__).resolve().parent
TESTS_DIR = ROOT / "tests"
EXPECTED_DIR = TESTS_DIR / "expected"


def cmd_parse(args) -> int:
    lexer = Lexer.from_json(args.tables) if args.tables else Lexer(build(args.spec).tables)
    text = args.expr if args.expr is not None else Path(args.file).read_text(encoding="utf-8")
    program, errors = parse_text(text, lexer=lexer)

    if args.format == "json":
        payload = {
            "ok": len(errors) == 0,
            "ast": program.to_dict(),
            "errors": [e.to_dict() for e in errors],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == "sexpr":
        print(program.to_sexpr())
        for e in errors:
            print(str(e), file=sys.stderr)
    else:
        print(format_tree(program))
        for e in errors:
            print(str(e), file=sys.stderr)

    return 1 if errors else 0


def cmd_test(args) -> int:
    lexer = Lexer(build(args.spec).tables)
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    test_files = sorted(TESTS_DIR.glob("*.funny"))
    passed = 0

    for tf in test_files:
        is_neg = tf.name.startswith("neg_")
        code = tf.read_text(encoding="utf-8")
        prog, errors = parse_text(code, lexer=lexer)
        snapshot = {
            "file": tf.name,
            "negative": is_neg,
            "ok": (len(errors) > 0) if is_neg else (len(errors) == 0),
            "sexpr": prog.to_sexpr(),
            "ast": prog.to_dict(),
            "errors": [str(e) for e in errors],
            "error_details": [e.to_dict() for e in errors],
        }
        exp_path = EXPECTED_DIR / f"{tf.stem}.json"
        if args.update or not exp_path.exists():
            exp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        expected = json.loads(exp_path.read_text(encoding="utf-8"))
        status_ok = (
            snapshot["ok"] is True
            and snapshot["sexpr"] == expected["sexpr"]
            and snapshot["errors"] == expected["errors"]
        )
        if status_ok:
            passed += 1
            sign = "-" if is_neg else "+"
            detail = snapshot["errors"][0] if is_neg else snapshot["sexpr"]
            print(f"PASS [{sign}] {tf.name:<34} -> {detail}")
        else:
            print(f"FAIL [!] {tf.name:<34}")
            print(f"   got:      errors={snapshot['errors']}, sexpr={snapshot['sexpr']}")
            print(f"   expected: errors={expected['errors']}, sexpr={expected['sexpr']}")

    print(f"\nИТОГО: {passed}/{len(test_files)} PASS")
    return 0 if passed == len(test_files) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python main.py",
        description="HW2: Синтаксический анализатор языка Funny (LL(1) + AST + интеграция с лексером)",
    )
    ap.add_argument("--spec", default=str(DEFAULT_SPEC), help="путь к funny.lex")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="разобрать файл или строку и вывести AST")
    src = p_parse.add_mutually_exclusive_group(required=True)
    src.add_argument("-e", "--expr", help="входная строка с программой на Funny")
    src.add_argument("file", nargs="?", help="путь к .funny файлу")
    p_parse.add_argument("--tables", help="готовый dfa.json")
    p_parse.add_argument("--format", choices=("json", "sexpr", "tree"), default="json")
    p_parse.set_defaults(func=cmd_parse)

    p_test = sub.add_parser("test", help="прогнать позитивные и негативные тесты из tests/")
    p_test.add_argument("-u", "--update", action="store_true", help="обновить эталонные snapshots в tests/expected/")
    p_test.set_defaults(func=cmd_test)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
