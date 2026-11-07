"""トルモン用の小さなYAMLパーサー（標準ライブラリのみ）。

YAMLの全仕様ではなく、このプロジェクトで決めた書き方（サブセット）だけを扱う。
  使える：  キー: 値 ／ "- " で始まるリスト ／ 半角スペースのインデント ／ # コメント
            文字列（ダブルクオート推奨・シングルクオート・クオートなし）／ 数値 ／ true・false ／ null
            空リスト [] と 1行のリスト [a, b]
  使えない：アンカー(&)・エイリアス(*)・タグ(!)・複数行ブロック(| >)・フロー形式の辞書 {}・タブ文字
使えない書き方を見つけたら、行番号つきの YamlError で止める（黙って誤読しない）。
"""

import json
import re

__all__ = ["YamlError", "load", "dump"]


class YamlError(ValueError):
    def __init__(self, message, lineno=None):
        self.lineno = lineno
        super().__init__(f"{lineno}行目: {message}" if lineno else message)


# ---------------------------------------------------------------- 読み込み

def _strip_comment(s):
    """クオートの外にある # 以降を取り除く（# の直前は行頭か空白のときだけコメント扱い）。"""
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote == '"':
            if c == "\\":
                i += 2
                continue
            if c == '"':
                quote = None
        elif quote == "'":
            if c == "'":
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i]
        i += 1
    return s


def _tokenize(text):
    lines = []
    for no, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise YamlError("インデントにタブ文字は使えません（半角スペースを使ってください）", no)
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip(" "))
        lines.append([indent, body.strip(), no])
    return lines


def _find_colon(s):
    """クオートの外にある「: 」または末尾の「:」の位置。なければ -1。"""
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote == '"':
            if c == "\\":
                i += 2
                continue
            if c == '"':
                quote = None
        elif quote == "'":
            if c == "'":
                quote = None
        elif c in "\"'" and (i == 0):
            quote = c
        elif c == ":" and (i + 1 == len(s) or s[i + 1] == " "):
            return i
        i += 1
    return -1


_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


def _split_flow(inner, no):
    items, buf, quote = [], "", None
    i = 0
    while i < len(inner):
        c = inner[i]
        if quote == '"' and c == "\\":
            buf += inner[i : i + 2]
            i += 2
            continue
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "[]{}":
            raise YamlError("1行リストの中に [ ] { } は書けません", no)
        elif c == ",":
            items.append(buf)
            buf = ""
            i += 1
            continue
        buf += c
        i += 1
    if quote:
        raise YamlError("クオートが閉じていません", no)
    if buf.strip() or items:
        items.append(buf)
    return [_scalar(x.strip(), no) for x in items]


def _scalar(s, no):
    if s == "":
        return None
    c = s[0]
    if c == '"':
        if len(s) < 2 or not s.endswith('"'):
            raise YamlError("ダブルクオートが閉じていません", no)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            raise YamlError("ダブルクオートの文字列が読めません（\\ の使い方を確認）", no)
    if c == "'":
        if len(s) < 2 or not s.endswith("'"):
            raise YamlError("シングルクオートが閉じていません", no)
        return s[1:-1].replace("''", "'")
    if c == "[":
        if not s.endswith("]"):
            raise YamlError("[ ] が閉じていません", no)
        return _split_flow(s[1:-1], no)
    if c in "&*!|>{%@`":
        raise YamlError(f"「{c}」で始まる書き方には対応していません（文字列ならダブルクオートで囲む）", no)
    low = s.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    return s


def _key(s, no):
    k = _scalar(s, no)
    if not isinstance(k, str):
        k = str(k) if k is not None else ""
    if k == "":
        raise YamlError("キーが空です", no)
    return k


class _Parser:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    def peek(self):
        return self.lines[self.i] if self.i < len(self.lines) else None

    def block(self, indent):
        indent_, content, _ = self.peek()
        if content == "-" or content.startswith("- "):
            return self.seq(indent)
        return self.mapping(indent)

    def child(self, parent_indent, no, allow_same_indent_seq=False):
        """キーや「- 」の後ろが空のとき、次の行からの入れ子を読む。"""
        nxt = self.peek()
        if nxt is None:
            return None
        if nxt[0] > parent_indent:
            return self.block(nxt[0])
        if allow_same_indent_seq and nxt[0] == parent_indent and (nxt[1] == "-" or nxt[1].startswith("- ")):
            return self.seq(parent_indent)
        return None

    def mapping(self, indent):
        result = {}
        while True:
            line = self.peek()
            if line is None or line[0] < indent:
                return result
            ind, content, no = line
            if ind > indent:
                raise YamlError("インデントがそろっていません", no)
            if content == "-" or content.startswith("- "):
                return result
            pos = _find_colon(content)
            if pos < 0:
                raise YamlError("「キー: 値」の形になっていません", no)
            key = _key(content[:pos].strip(), no)
            if key in result:
                raise YamlError(f"キー「{key}」が重複しています", no)
            rest = content[pos + 1 :].strip()
            self.i += 1
            if rest == "":
                result[key] = self.child(indent, no, allow_same_indent_seq=True)
            else:
                result[key] = _scalar(rest, no)

    def seq(self, indent):
        result = []
        while True:
            line = self.peek()
            if line is None or line[0] < indent:
                return result
            ind, content, no = line
            if ind > indent:
                raise YamlError("インデントがそろっていません", no)
            if not (content == "-" or content.startswith("- ")):
                return result
            rest = content[1:].lstrip(" ")
            if rest == "":
                self.i += 1
                result.append(self.child(indent, no))
                continue
            sub_indent = ind + (len(content) - len(rest))
            if not rest.startswith("[") and _find_colon(rest) >= 0:
                # 「- key: value」→ 同じ要素の続きのキーは sub_indent にそろう
                self.lines[self.i] = [sub_indent, rest, no]
                result.append(self.mapping(sub_indent))
            else:
                self.i += 1
                result.append(_scalar(rest, no))


def load(text):
    """サブセットYAMLの文字列を dict / list / 値 に変換する。"""
    if text.startswith("﻿"):
        text = text[1:]
    lines = _tokenize(text)
    if not lines:
        return None
    if lines[0][1] == "---":
        lines = lines[1:]
    p = _Parser(lines)
    first = p.peek()
    if first[0] != 0:
        raise YamlError("1行目はインデントなしで始めてください", first[2])
    if len(lines) == 1 and _find_colon(first[1]) < 0 and not first[1].startswith("-"):
        return _scalar(first[1], first[2])
    try:
        data = p.block(0)
    except RecursionError:
        raise YamlError("入れ子が深すぎます", first[2])
    except ValueError as e:                     # 例：桁が多すぎる数字（Python の上限）
        if isinstance(e, YamlError):
            raise
        raise YamlError(f"読めない値があります（{e}）", first[2])
    if p.peek() is not None:
        raise YamlError("インデントがそろっていません", p.peek()[2])
    return data


# ---------------------------------------------------------------- 書き出し

_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")


def _dump_scalar(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    raise TypeError(f"YAMLに書けない型です: {type(v).__name__}")


def _dump_key(k):
    return k if _PLAIN_KEY.match(k) else json.dumps(k, ensure_ascii=False)


def _dump(obj, indent, out):
    pad = " " * indent
    if isinstance(obj, dict):
        if not obj:
            raise TypeError("空の辞書は書けません")
        for k, v in obj.items():
            if isinstance(v, dict) and v:
                out.append(f"{pad}{_dump_key(k)}:")
                _dump(v, indent + 2, out)
            elif isinstance(v, list) and v:
                out.append(f"{pad}{_dump_key(k)}:")
                _dump(v, indent + 2, out)
            elif isinstance(v, list):
                out.append(f"{pad}{_dump_key(k)}: []")
            else:
                out.append(f"{pad}{_dump_key(k)}: {_dump_scalar(v)}")
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict) and v:
                sub = []
                _dump(v, indent + 2, sub)
                sub[0] = f"{pad}- " + sub[0][indent + 2 :]
                out.extend(sub)
            elif isinstance(v, list) and v:
                out.append(f"{pad}-")
                _dump(v, indent + 2, out)
            elif isinstance(v, list):
                out.append(f"{pad}- []")
            else:
                out.append(f"{pad}- {_dump_scalar(v)}")
    else:
        out.append(pad + _dump_scalar(obj))


def dump(obj):
    """dict / list をサブセットYAMLの文字列にする（文字列は必ずダブルクオート）。"""
    out = []
    _dump(obj, 0, out)
    return "\n".join(out) + "\n"
