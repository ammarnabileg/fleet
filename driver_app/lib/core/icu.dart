import 'package:intl/intl.dart';

/// ICU messages as gen-l10n reads them (apostrophes are plain text): text, {name}, {name, number|date|time[, style]},
/// {name, plural|selectordinal, [offset:n] selector{message} ...} and {name, select, value{message} ... other{...}}.
/// Used for the strings downloaded from the dashboard: each is parsed and checked against the built-in English
/// message before it is used, and formatted here. Only text: nothing in a message is ever executed.
class IcuMessage {
  IcuMessage._(this._nodes, this.args);

  final List<_Node> _nodes;

  /// The arguments the message uses: name -> kind (simple, number, date, time, plural, select).
  final Map<String, String> args;

  static final _cache = <String, IcuMessage?>{};

  /// The parsed message, or null when it does not parse (cached either way).
  static IcuMessage? tryParse(String text) => _cache.putIfAbsent(text, () {
    try {
      return parse(text);
    } on FormatException {
      return null;
    }
  });

  static IcuMessage parse(String text) {
    final p = _Parser(text);
    final nodes = p.message(0, nested: false);
    return IcuMessage._(nodes, p.args);
  }

  /// null when [text] is a valid message with exactly the arguments of [reference] (the built-in English), else the
  /// reason, as the server says it ("invalid:...", "missing:{a}", "unknown:{b}", "kind:{c}", "empty").
  static String? check(String text, String? reference) {
    if (text.trim().isEmpty) return 'empty';
    final IcuMessage message;
    try {
      message = parse(text);
    } on FormatException catch (e) {
      return 'invalid:${e.message}';
    }
    if (reference == null) return null;
    final expected = tryParse(reference)?.args ?? const <String, String>{};
    final missing = expected.keys.where((k) => !message.args.containsKey(k)).toList()..sort();
    if (missing.isNotEmpty) return 'missing:${missing.map((n) => '{$n}').join(', ')}';
    final unknown = message.args.keys.where((k) => !expected.containsKey(k)).toList()..sort();
    if (unknown.isNotEmpty) return 'unknown:${unknown.map((n) => '{$n}').join(', ')}';
    for (final e in expected.entries) {
      final kind = message.args[e.key];
      if ((e.value == 'plural' || e.value == 'select') && kind != e.value && kind != 'simple') return 'kind:{${e.key}}';
    }
    return null;
  }

  /// The text with [values] put in; [locale] picks the plural form.
  String format(Map<String, Object?> values, String locale) {
    final out = StringBuffer();
    _write(_nodes, values, locale, null, out);
    return out.toString();
  }

  static void _write(List<_Node> nodes, Map<String, Object?> values, String locale, num? hash, StringBuffer out) {
    for (final n in nodes) {
      switch (n) {
        case _Text(:final text):
          out.write(text);
        case _Hash():
          out.write(hash == null ? '#' : _num(hash));
        case _Arg(:final name):
          out.write('${values[name] ?? ''}');
        case _Plural(:final name, :final offset, :final options):
          final raw = values[name];
          final count = raw is num ? raw : num.tryParse('$raw') ?? 0;
          final shown = count - offset;
          final exact = options['=${count is int ? count : count.toString()}'];
          final chosen =
              exact ??
              Intl.pluralLogic<List<_Node>?>(
                shown,
                locale: locale,
                zero: options['zero'],
                one: options['one'],
                two: options['two'],
                few: options['few'],
                many: options['many'],
                other: options['other'],
              ) ??
              options['other']!;
          _write(chosen, values, locale, shown, out);
        case _Select(:final name, :final options):
          _write(options['${values[name]}'] ?? options['other']!, values, locale, hash, out);
      }
    }
  }

  static String _num(num n) => n == n.roundToDouble() ? n.toInt().toString() : n.toString();
}

sealed class _Node {}

class _Text extends _Node {
  _Text(this.text);
  final String text;
}

class _Hash extends _Node {}

class _Arg extends _Node {
  _Arg(this.name);
  final String name;
}

class _Plural extends _Node {
  _Plural(this.name, this.offset, this.options);
  final String name;
  final int offset;
  final Map<String, List<_Node>> options;
}

class _Select extends _Node {
  _Select(this.name, this.options);
  final String name;
  final Map<String, List<_Node>> options;
}

class _Parser {
  _Parser(this.s);

  final String s;
  int i = 0;
  final args = <String, String>{};
  static final _name = RegExp(r'[A-Za-z_][A-Za-z0-9_]*');
  static const _pluralSelectors = {'zero', 'one', 'two', 'few', 'many', 'other'};
  static const _simple = {'number', 'date', 'time'};

  Never fail(String reason) => throw FormatException('$reason@$i');

  void ws() {
    while (i < s.length && s[i].trim().isEmpty) {
      i++;
    }
  }

  List<_Node> message(int depth, {required bool nested, bool inPlural = false}) {
    if (depth > 6) fail('too_deep');
    final nodes = <_Node>[];
    final text = StringBuffer();
    void flush() {
      if (text.isNotEmpty) nodes.add(_Text(text.toString()));
      text.clear();
    }

    while (i < s.length) {
      final c = s[i];
      if (c == '{') {
        flush();
        i++;
        nodes.add(argument(depth));
      } else if (c == '}') {
        if (nested) {
          flush();
          return nodes;
        }
        fail('unexpected_close');
      } else if (c == '#' && inPlural) {
        flush();
        nodes.add(_Hash());
        i++;
      } else {
        text.write(c);
        i++;
      }
    }
    if (nested) fail('unclosed');
    flush();
    return nodes;
  }

  String name() {
    ws();
    final m = _name.matchAsPrefix(s, i);
    if (m == null) fail('bad_name');
    i = m.end;
    return m[0]!;
  }

  void expect(String ch) {
    ws();
    if (i >= s.length || s[i] != ch) {
      fail(switch (ch) {
        '{' => 'expected_open',
        '}' => 'expected_close',
        _ => 'expected_comma',
      });
    }
    i++;
  }

  _Node argument(int depth) {
    final n = name();
    ws();
    if (i < s.length && s[i] == '}') {
      i++;
      _arg(n, 'simple');
      return _Arg(n);
    }
    expect(',');
    final kind = name();
    if (_simple.contains(kind)) {
      _arg(n, kind);
      ws();
      if (i < s.length && s[i] == ',') {
        i++;
        final start = i;
        while (i < s.length && s[i] != '{' && s[i] != '}') {
          i++;
        }
        if (s.substring(start, i).trim().isEmpty) fail('bad_style');
      }
      expect('}');
      return _Arg(n);
    }
    if (kind == 'plural' || kind == 'selectordinal' || kind == 'select') {
      final select = kind == 'select';
      _arg(n, select ? 'select' : 'plural');
      expect(',');
      var offset = 0;
      ws();
      if (!select && s.startsWith('offset:', i)) {
        i += 'offset:'.length;
        ws();
        final m = RegExp(r'\d+').matchAsPrefix(s, i);
        if (m == null) fail('bad_offset');
        offset = int.parse(m[0]!);
        i = m.end;
      }
      final options = <String, List<_Node>>{};
      while (true) {
        ws();
        if (i >= s.length) fail('unclosed');
        if (s[i] == '}') {
          i++;
          break;
        }
        String selector;
        if (!select && s[i] == '=') {
          final m = RegExp(r'=\d+').matchAsPrefix(s, i);
          if (m == null) fail('bad_selector');
          selector = m[0]!;
          i = m.end;
        } else {
          selector = name();
          if (!select && !_pluralSelectors.contains(selector)) fail('bad_selector');
        }
        if (options.containsKey(selector)) fail('duplicate_selector');
        expect('{');
        options[selector] = message(depth + 1, nested: true, inPlural: !select);
        i++; // the option's closing brace
      }
      if (!options.containsKey('other')) fail('missing_other');
      return select ? _Select(n, options) : _Plural(n, offset, options);
    }
    fail('bad_type');
  }

  void _arg(String name, String kind) {
    final known = args[name];
    if (known != null && known != kind && known != 'simple' && kind != 'simple') fail('argument_kinds');
    if (known == null || known == 'simple') args[name] = kind;
  }
}
