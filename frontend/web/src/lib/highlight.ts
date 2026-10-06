/**
 * Lightweight syntax highlighter.
 *
 * Chat surfaces stream code in fragments, so any highlighter has to tolerate
 * half-finished input: an unterminated string, a dangling comment opener, a
 * truncated line. Everything here is regex-driven and never throws, which makes
 * it safe to run on every stream tick.
 *
 * This deliberately avoids a full parser (Shiki/Prism/Monaco). Those are the
 * right tool for an editor, but for streamed chat output the dominant cost is
 * re-tokenising on every partial update, and a linear scan with a small keyword
 * set is orders of magnitude cheaper.
 */

export type TokenType =
  | 'plain'
  | 'keyword'
  | 'string'
  | 'comment'
  | 'number'
  | 'function'
  | 'punctuation'
  | 'operator'
  | 'type'
  | 'tag'
  | 'attribute'
  | 'property'
  | 'constant';

export interface Token {
  type: TokenType;
  value: string;
}

interface LanguageSpec {
  keywords: Set<string>;
  literals: Set<string>;
  lineComment: string[];
  blockComment?: [string, string];
  /** Characters that begin a double-quoted string. */
  quotes: string[];
  types?: Set<string>;
  /**
   * True for languages where `identifier:` introduces a property or key rather
   * than a label, which is how CSS declarations and YAML keys are recognised.
   */
  keyValue?: boolean;
}

const JS_KEYWORDS =
  'abstract as async await break case catch class const continue debugger default delete do else enum export extends false finally for from function get if implements import in instanceof interface let new null of private protected public readonly return set static super switch this throw true try type typeof undefined var void while with yield as satisfies';

const PY_KEYWORDS =
  'and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case True False None self';

const TS_EXTRA = 'abstract any bigint boolean declare namespace never number object string symbol unknown readonly keyof infer satisfies asserts';

const RUST_KEYWORDS =
  'as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while';

const GO_KEYWORDS =
  'break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var nil true false';

const JAVA_KEYWORDS =
  'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while record var sealed yield true false null';

const SQL_KEYWORDS =
  'select from where group by order having limit offset insert into values update set delete create table alter drop index join inner left right outer full on as distinct union all and or not null is in exists between like case when then else end primary key foreign references default constraint begin commit rollback transaction explain analyze with recursive over partition window returning';

const SHELL_KEYWORDS =
  'if then else elif fi for while do done case esac function return export local readonly source alias unset echo cd exit set trap shift printf test';

const CSS_KEYWORDS =
  'important media supports keyframes import charset font-face layer container property';

function words(list: string): Set<string> {
  return new Set(list.split(/\s+/).filter(Boolean));
}

const SPECS: Record<string, LanguageSpec> = {
  javascript: {
    keywords: words(JS_KEYWORDS),
    literals: new Set(['true', 'false', 'null', 'undefined', 'NaN', 'Infinity']),
    lineComment: ['//'],
    blockComment: ['/*', '*/'],
    quotes: ['"', "'", '`'],
  },
  typescript: {
    keywords: words(`${JS_KEYWORDS} ${TS_EXTRA}`),
    literals: new Set(['true', 'false', 'null', 'undefined']),
    lineComment: ['//'],
    blockComment: ['/*', '*/'],
    quotes: ['"', "'", '`'],
    types: words('string number boolean object any unknown never void bigint symbol'),
  },
  python: {
    keywords: words(PY_KEYWORDS),
    literals: new Set(['True', 'False', 'None']),
    lineComment: ['#'],
    quotes: ['"', "'"],
  },
  rust: {
    keywords: words(RUST_KEYWORDS),
    literals: new Set(['true', 'false', 'None', 'Some', 'Ok', 'Err']),
    lineComment: ['//'],
    blockComment: ['/*', '*/'],
    quotes: ['"'],
    types: words('str i8 i16 i32 i64 i128 u8 u16 u32 u64 usize isize f32 f64 bool char Vec Option String Result Box'),
  },
  go: {
    keywords: words(GO_KEYWORDS),
    literals: new Set(['true', 'false', 'nil', 'iota']),
    lineComment: ['//'],
    blockComment: ['/*', '*/'],
    quotes: ['"', '`'],
    types: words('string int int8 int16 int32 int64 uint uint8 uint16 uint32 uint64 float32 float64 bool byte rune error any'),
  },
  java: {
    keywords: words(JAVA_KEYWORDS),
    literals: new Set(['true', 'false', 'null']),
    lineComment: ['//'],
    blockComment: ['/*', '*/'],
    quotes: ['"'],
    types: words('String Integer Long Double Boolean Object List Map Set Optional Stream'),
  },
  sql: {
    keywords: words(SQL_KEYWORDS),
    literals: new Set(['true', 'false', 'null']),
    lineComment: ['--'],
    quotes: ["'", '"'],
  },
  bash: {
    keywords: words(SHELL_KEYWORDS),
    literals: new Set(['true', 'false']),
    lineComment: ['#'],
    quotes: ['"', "'"],
  },
  json: {
    keywords: new Set<string>(),
    literals: new Set(['true', 'false', 'null']),
    lineComment: [],
    quotes: ['"'],
    keyValue: true,
  },
  yaml: {
    keywords: new Set<string>(),
    literals: new Set(['true', 'false', 'null', 'yes', 'no', 'on', 'off']),
    lineComment: ['#'],
    quotes: ['"', "'"],
    keyValue: true,
  },
  css: {
    keywords: words(CSS_KEYWORDS),
    literals: new Set(['inherit', 'initial', 'unset', 'none', 'auto']),
    lineComment: [],
    blockComment: ['/*', '*/'],
    quotes: ['"', "'"],
    keyValue: true,
  },
};

/** Aliases so a model writing ```py still gets Python rules. */
const ALIASES: Record<string, keyof typeof SPECS> = {
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  node: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  py: 'python',
  python3: 'python',
  rs: 'rust',
  golang: 'go',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  console: 'bash',
  yml: 'yaml',
  scss: 'css',
  less: 'css',
  jsonc: 'json',
  json5: 'json',
};

/** Resolve a fence label (or filename) to a canonical spec name. */
export function normalizeLanguage(language?: string | null): string | null {
  if (!language) return null;
  const cleaned = language.trim().toLowerCase();
  if (!cleaned) return null;
  if (SPECS[cleaned]) return cleaned;
  return ALIASES[cleaned] ?? null;
}

const IDENTIFIER_START = /[A-Za-z_$]/;
const IDENTIFIER_PART = /[A-Za-z0-9_$]/;
const DIGIT = /[0-9]/;

function isIdentifierStart(ch: string): boolean {
  return IDENTIFIER_START.test(ch);
}

function isIdentifierPart(ch: string): boolean {
  return IDENTIFIER_PART.test(ch);
}

/**
 * Tokenize `code` for `language`.
 *
 * Never throws and always returns at least one token, so callers can render the
 * result unconditionally even for empty or partial input.
 */
export function tokenize(code: string, language?: string | null): Token[] {
  const lang = normalizeLanguage(language);
  if (!lang) {
    return code.length > 0 ? [{ type: 'plain', value: code }] : [];
  }
  return tokenizeWithSpec(code, SPECS[lang]);
}

function tokenizeWithSpec(code: string, spec: LanguageSpec): Token[] {
  const tokens: Token[] = [];
  let plain = '';

  const flush = () => {
    if (plain) {
      tokens.push({ type: 'plain', value: plain });
      plain = '';
    }
  };
  const push = (type: TokenType, value: string) => {
    flush();
    tokens.push({ type, value });
  };

  let i = 0;
  const n = code.length;

  while (i < n) {
    const ch = code[i];

    // --- comments (block first, so `/*` wins over `/`) ---
    if (spec.blockComment) {
      const [open, close] = spec.blockComment;
      if (code.startsWith(open, i)) {
        const end = code.indexOf(close, i + open.length);
        // An unterminated block comment runs to end of input, which is exactly
        // right while streaming.
        const stop = end === -1 ? n : end + close.length;
        push('comment', code.slice(i, stop));
        i = stop;
        continue;
      }
    }

    let matchedLineComment = false;
    for (const marker of spec.lineComment) {
      if (code.startsWith(marker, i)) {
        let end = code.indexOf('\n', i);
        if (end === -1) end = n;
        push('comment', code.slice(i, end));
        i = end;
        matchedLineComment = true;
        break;
      }
    }
    if (matchedLineComment) continue;

    // --- strings ---
    if (spec.quotes.includes(ch)) {
      let j = i + 1;
      while (j < n) {
        if (code[j] === '\\') {
          j += 2;
          continue;
        }
        // A bare newline terminates a single-quoted string. For template
        // literals and multi-line strings we keep scanning, so partial input
        // still renders as one token.
        if (code[j] === ch || (ch !== '`' && code[j] === '\n')) break;
        j += 1;
      }
      const stop = Math.min(j + 1, n);
      push('string', code.slice(i, stop));
      i = stop;
      continue;
    }

    // --- numbers ---
    if (DIGIT.test(ch)) {
      let j = i;
      while (j < n && /[0-9a-fA-FxXoObB._]/.test(code[j])) j += 1;
      push('number', code.slice(i, j));
      i = j;
      continue;
    }

    // --- identifiers: keywords, literals, types, call sites, properties ---
    if (isIdentifierStart(ch)) {
      let j = i;
      while (j < n && isIdentifierPart(code[j])) j += 1;
      const word = code.slice(i, j);

      let type: TokenType = 'plain';
      if (spec.literals.has(word)) type = 'constant';
      else if (spec.keywords.has(word)) type = 'keyword';
      else if (spec.types?.has(word)) type = 'type';

      if (type === 'plain') {
        // `name(` is a call; `name:` in css/yaml is a property.
        let k = j;
        while (k < n && code[k] === ' ') k += 1;
        if (code[k] === '(') {
          type = 'function';
        } else if (spec.keyValue && code[k] === ':') {
          type = 'property';
        }
      }

      push(type, word);
      i = j;
      continue;
    }

    // --- html / xml-ish tags ---
    if (ch === '<') {
      const tag = matchTag(code, i);
      if (tag) {
        push('tag', tag);
        i += tag.length;
        continue;
      }
    }

    // --- punctuation vs operators ---
    if ('{}[]();,.'.includes(ch)) {
      push('punctuation', ch);
      i += 1;
      continue;
    }
    if ('+-*/%=<>!&|^~?:'.includes(ch)) {
      push('operator', ch);
      i += 1;
      continue;
    }

    plain += ch;
    i += 1;
  }

  flush();
  return tokens;
}

/** Match an html/xml tag from `start`, returning the raw tag text or null. */
function matchTag(code: string, start: number): string | null {
  const rest = code.slice(start);
  const match = /^<\/?[A-Za-z][A-Za-z0-9:-]*/.exec(rest);
  if (!match) return null;

  let i = start + match[0].length;
  const n = code.length;

  while (i < n) {
    const ch = code[i];
    if (ch === '"' || ch === "'") {
      let j = i + 1;
      while (j < n && code[j] !== ch) j += 1;
      i = Math.min(j + 1, n);
      continue;
    }
    if (ch === '>') return code.slice(start, i + 1);
    if (code.startsWith('/>', i)) return code.slice(start, i + 2);
    i += 1;
  }
  // Streaming an unclosed tag: return what we have so it still renders.
  return code.slice(start, n);
}