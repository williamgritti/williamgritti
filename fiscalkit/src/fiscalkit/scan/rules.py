"""Detection rules for code that breaks when CNPJs become alphanumeric.

From July 2026, *Instrução Normativa RFB nº 2.229/2024* allows letters in the
first twelve positions of a CNPJ. Validation libraries have already adapted --
``brutils``, ``validate-docbr`` and ``fiscalkit`` all accept the new format. That
is not the migration problem.

The problem is the code around them: a ``^\\d{14}$`` regex guarding an API
boundary, a ``BIGINT`` column, an ``int()`` cast used to strip leading zeros. Each
one silently rejects or corrupts a valid CNPJ, and none of them is fixed by
upgrading a dependency. These rules find that code.

Every rule below is verified against a real alphanumeric CNPJ in the test suite:
each pattern must accept ``11222333000181`` and reject or corrupt
``12ABC34501DE35``. A rule that cannot demonstrate that difference is not a rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["RULES", "Rule", "Severity", "language_of", "rules_for_language"]

Severity = str

#: Certain to break: the pattern provably rejects or corrupts a valid CNPJ.
BREAKS: Severity = "breaks"
#: Probably breaks, but depends on how the value reaches this code.
RISKY: Severity = "risky"
#: Worth a human look; too context-dependent to call automatically.
REVIEW: Severity = "review"

SEVERITY_ORDER = {BREAKS: 0, RISKY: 1, REVIEW: 2}


@dataclass(frozen=True, slots=True)
class Rule:
    """One detectable pattern that does not survive the alphanumeric format."""

    id: str
    title: str
    severity: Severity
    pattern: re.Pattern[str]
    explanation: str
    fix: str
    languages: frozenset[str] | None = None
    #: When true, only report if "cnpj" appears nearby. Keeps precision high for
    #: patterns like ``\\d{14}`` that are meaningless without that context.
    needs_cnpj_context: bool = False
    #: An unambiguous textual rewrite, as ``(search, replace)`` pairs applied to
    #: the offending line. Present only where the correct edit follows from the
    #: pattern alone. A CNPJ cast to an integer has no mechanical fix -- the
    #: surrounding code has to stop treating it as a number -- so that rule
    #: deliberately carries none and ``--fix`` leaves it for a human.
    autofix: tuple[tuple[str, str], ...] | None = None

    @property
    def is_fixable(self) -> bool:
        """Whether this rule carries a mechanical rewrite."""
        return bool(self.autofix)

    def applies_to(self, language: str) -> bool:
        """Whether this rule should run against a file of *language*."""
        return self.languages is None or language in self.languages


def _c(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: Extension to language name. Only text formats worth scanning.
EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".sql": "sql",
    ".java": "java",
    ".kt": "kotlin",
    ".php": "php",
    ".go": "go",
    ".cs": "csharp",
    ".rb": "ruby",
    ".rs": "rust",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".vue": "javascript",
    # Schema and interface-definition formats. A CNPJ typed as an integer in one
    # of these propagates the defect into every generated client and stub.
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".prisma": "prisma",
    ".avsc": "json",
}


def language_of(filename: str) -> str | None:
    """Return the language for *filename*, or ``None`` if it is not scanned."""
    lowered = filename.lower()
    for ext, lang in EXTENSIONS.items():
        if lowered.endswith(ext):
            return lang
    return None


RULES: tuple[Rule, ...] = (
    # -- Numeric-only validation ------------------------------------------
    Rule(
        id="CNPJ001",
        title="Regex de CNPJ que aceita apenas dígitos",
        severity=BREAKS,
        pattern=_c(r"(?:\\d|\[0-9\])\s*\{\s*14\s*\}"),
        needs_cnpj_context=True,
        explanation=(
            "Uma regex numérica de 14 dígitos rejeita todo CNPJ alfanumérico. É a forma mais comum "
            "de um sistema passar a recusar documentos válidos."
        ),
        fix=(
            "Use [0-9A-Z]{12}[0-9]{2}: as doze primeiras posições aceitam letras e os dois dígitos "
            "verificadores continuam numéricos."
        ),
        autofix=((r"\d{14}", "[0-9A-Z]{12}[0-9]{2}"), ("[0-9]{14}", "[0-9A-Z]{12}[0-9]{2}")),
    ),
    Rule(
        id="CNPJ002",
        title="Máscara de CNPJ formatada que aceita apenas dígitos",
        severity=BREAKS,
        # Anchored on the "/0000" branch group, which is unique to the CNPJ mask.
        # An earlier version matched only the leading \d{2}\.\d{3}, and that
        # fires on version strings, dotted dates, coordinates and -- worst for a
        # Brazilian tool -- the CEP mask \d{2}\.\d{3}-\d{3}, which is in every
        # address form in the country. Context-gated as well, for the same reason.
        pattern=_c(r"(?:\\d|\[0-9\])\s*\{\s*3\s*\}\s*\\?/\s*(?:\\d|\[0-9\])\s*\{\s*4\s*\}"),
        needs_cnpj_context=True,
        explanation=(
            "Uma máscara 00.000.000/0000-00 montada com classes de dígito rejeita a forma "
            "alfanumérica, que tem exatamente a mesma pontuação."
        ),
        fix="Amplie as doze primeiras posições para [0-9A-Z] e mantenha as duas últimas numéricas.",
    ),
    Rule(
        id="CNPJ003",
        title="Verificação isdigit / isnumeric em CNPJ",
        severity=BREAKS,
        pattern=_c(r"cnpj\w*\s*(?:\.|->|::)\s*(?:isdigit|isnumeric|isdecimal)\s*\(\)"),
        explanation=(
            "isdigit() é falso para qualquer CNPJ com letra, então essa guarda passa a rejeitar "
            "documentos válidos a partir de julho de 2026."
        ),
        fix=(
            "Valide com um validador de CNPJ que conheça as regras de 2026, ou teste isalnum() "
            "somado a uma verificação explícita de que os dois últimos caracteres são dígitos."
        ),
    ),
    Rule(
        id="CNPJ004",
        title="Verificação ctype / Number em CNPJ",
        severity=BREAKS,
        pattern=_c(
            r"(?<![\w.])(?:ctype_digit|is_numeric|isNaN|Number|parseInt|parseFloat)"
            r"\s*\(\s*[^)]*cnpj"
        ),
        explanation=(
            "Converter um CNPJ para número quebra quando letras passam a ser válidas, e as duas "
            "formas de quebrar não são igualmente sobreviveis. Number() e isNaN() produzem NaN, e "
            "ctype_digit() devolve false: são falhas barulhentas. Já parseInt() trunca na primeira "
            "letra e devolve um número plausível, pois parseInt('12ABC34501DE35', 10) é 12. Esse "
            "valor chega ao banco parecendo legítimo e só é descoberto muito depois, se for."
        ),
        fix="Trate o CNPJ como string opaca. Ele é um identificador, nunca uma quantidade.",
    ),
    # -- Numeric storage and casting --------------------------------------
    Rule(
        id="CNPJ010",
        title="CNPJ convertido para inteiro",
        severity=BREAKS,
        # The lookbehind excludes a preceding word character so that "print("
        # does not match on the "int(" inside it. It deliberately allows a
        # preceding dot, because strconv.Atoi, Int32.Parse and Convert.ToInt64
        # are exactly the calls worth finding in Go, C# and Java.
        pattern=_c(
            r"(?:(?<!\w)(?:int|long|bigint|atoi|intval|to_number)\s*\(\s*[^)]{0,40}cnpj"
            r"|(?:Integer\.parseInt|Long\.parseLong|Int32\.Parse|Int64\.Parse"
            r"|Convert\.ToInt32|Convert\.ToInt64|strconv\.(?:Atoi|ParseInt))"
            r"\s*\(\s*[^)]{0,40}cnpj"
            r"|cnpj[^\n]{0,24}\.\s*to_i\b)"
        ),
        explanation=(
            "Converter para inteiro estoura ou trunca em um CNPJ alfanumérico, e já hoje descarta "
            "silenciosamente os zeros à esquerda."
        ),
        fix="Mantenha o CNPJ como string de ponta a ponta.",
    ),
    Rule(
        id="CNPJ011",
        title="Coluna de CNPJ declarada com tipo numérico",
        severity=BREAKS,
        pattern=_c(
            r"cnpj\w*\s+(?:big\s*int|bigint|int(?:eger)?|numeric|decimal|number|bigserial|long)\b"
        ),
        languages=frozenset({"sql"}),
        explanation=(
            "PostgreSQL, MySQL e tabelas STRICT do SQLite rejeitam um CNPJ alfanumérico de "
            "imediato. O comportamento padrão do SQLite é pior: ele aceita o valor e o grava como "
            "TEXT numa coluna declarada BIGINT, deixando as linhas antigas como inteiro e as novas "
            "como texto na mesma coluna, de modo que a falha só aparece depois, num JOIN, num "
            "ORDER BY ou numa comparação. De um jeito ou de outro isso é migração de schema, o "
            "item que exige o maior prazo de todos aqui."
        ),
        fix=(
            "Migre para CHAR(14) ou VARCHAR(14). Planeje o backfill e todas as chaves estrangeiras "
            "que referenciam esta coluna."
        ),
        autofix=(
            ("BIGINT", "CHAR(14)"),
            ("bigint", "CHAR(14)"),
            ("NUMERIC(14)", "CHAR(14)"),
            ("DECIMAL(14,0)", "CHAR(14)"),
        ),
    ),
    Rule(
        id="CNPJ012",
        title="CNPJ mapeado como campo inteiro no ORM",
        severity=BREAKS,
        # Two shapes: `cnpj = IntegerField()` (Python/ORM, name first) and
        # `private BigInteger cnpj;` or `public long Cnpj { get; set; }`
        # (Java/C#, type first). Only the first was matched before.
        pattern=_c(
            r"(?:cnpj\w*\s*[:=]\s*(?:models\.)?(?:Big)?"
            r"(?:Integer|Int|Number|Numeric|Decimal|Long)(?:Field|Column)?\b"
            r"|(?<!\w)(?:big)?(?:integer|int|int32|int64|long|number|numeric|decimal"
            r"|biginteger|bigdecimal)\s+cnpj\w*\s*[;={,)])"
        ),
        explanation="O ORM vai gerar uma coluna numérica, incapaz de armazenar letras.",
        fix="Use um campo de caractere com tamanho 14.",
        autofix=(
            ("models.BigIntegerField(", "models.CharField(max_length=14, "),
            ("models.IntegerField(", "models.CharField(max_length=14, "),
        ),
    ),
    Rule(
        id="CNPJ013",
        title="CNPJ preenchido com zeros à esquerda para voltar a 14 caracteres",
        severity=RISKY,
        # Receiver form (cnpj.zfill), chained form (String(x.cnpj).padStart)
        # and argument form (str_pad($cnpj, 14, ...)), which PHP uses.
        pattern=_c(
            r"(?:cnpj[^\n]{0,24}(?:\.|->|::)\s*(?:zfill|rjust|padStart|str_pad|PadLeft|padleft)\s*\("
            r"|(?:zfill|rjust|padStart|str_pad|PadLeft)\s*\(\s*[^)]{0,30}cnpj)"
        ),
        explanation=(
            "O preenchimento com zeros existe para consertar um CNPJ que foi armazenado como "
            "número. O preenchimento em si é inofensivo; o que ele revela sobre o armazenamento "
            "não é."
        ),
        fix="Descubra onde os zeros à esquerda se perderam. É ali que está o defeito.",
    ),
    # -- Length and formatting assumptions --------------------------------
    Rule(
        id="CNPJ020",
        title="CNPJ comparado com literal numérico",
        severity=RISKY,
        pattern=_c(r"cnpj\w*\s*(?:==|!=|===|!==|<>)\s*\d{6,}"),
        explanation=(
            "Comparar um CNPJ com um número puro significa que ele está sendo guardado como número."
        ),
        fix="Compare strings e normalize a caixa antes de comparar.",
    ),
    Rule(
        id="CNPJ021",
        title="CNPJ normalizado removendo tudo que não é dígito",
        severity=BREAKS,
        pattern=_c(
            r"(?:replace|sub|gsub|preg_replace|RegExp)\s*\(\s*[^)]{0,30}"
            r"(?:\[\^0-9\]|\[\^\\d\]|\\D)"
        ),
        needs_cnpj_context=True,
        explanation=(
            "Remover tudo que não é dígito apaga as letras de um CNPJ alfanumérico, produzindo um "
            "valor mais curto que falha na validação depois."
        ),
        fix="Remova apenas a pontuação: descarte [^0-9A-Z] depois de passar para maiúsculas.",
        autofix=(
            ("[^0-9]", "[^0-9A-Z]"),
            (r"[^\d]", "[^0-9A-Z]"),
            (r"\D", "[^0-9A-Z]"),
        ),
    ),
    Rule(
        id="CNPJ022",
        title="Dígitos verificadores calculados sem o mapeamento ASCII-48",
        severity=REVIEW,
        pattern=_c(r"(?:int|ord|charCodeAt|Integer\.parseInt)\s*\(\s*\w*\s*\[\s*i\s*\]"),
        needs_cnpj_context=True,
        explanation=(
            "Um laço de dígito verificador escrito à mão que converte cada caractere com int() em "
            "vez de ord(c) - 48 não consegue pontuar letras."
        ),
        fix=(
            "Mapeie cada caractere com ord(c) - 48, que reproduz exatamente o resultado numérico "
            "legado, de modo que um único caminho de código atende aos dois formatos."
        ),
    ),
    Rule(
        id="CNPJ014",
        title="CNPJ tipado como inteiro em schema ou especificação de API",
        severity=BREAKS,
        # OpenAPI, JSON Schema and Avro put the type on its own line under the
        # field name, so this is keyed on the type and gated on nearby context
        # rather than trying to match both on one line.
        pattern=_c(r"[\"']?type[\"']?\s*[:=]\s*[\"']?(?:integer|number|int32|int64|long)\b"),
        needs_cnpj_context=True,
        explanation=(
            "Um CNPJ declarado como inteiro numa especificação não fica na especificação: todo "
            "cliente, stub de servidor e validador gerado herda o tipo, então uma linha aqui vira "
            "o mesmo defeito em várias linguagens ao mesmo tempo."
        ),
        fix=(
            "Declare como string com maxLength 14. Mantenha qualquer restrição de pattern "
            "alfanumérica: ^[0-9A-Z]{12}[0-9]{2}$."
        ),
    ),
    Rule(
        id="CNPJ015",
        title="CNPJ declarado como campo inteiro, sem separador",
        severity=BREAKS,
        # Prisma, Protobuf IDL and Go struct tags write `cnpj Int` with only
        # whitespace between name and type, which the assignment forms miss.
        # The trailing exclusion keeps prose out. A declaration is followed by end
        # of line, an attribute, or punctuation; `print("cnpj integer")` is
        # followed by a quote, and is a sentence rather than a field.
        pattern=_c(
            r"(?<![\w.])cnpj\w*\s+(?:big)?int(?:eger|32|64)?\b"
            r"(?!\s*\()(?!\s*[\"'`])(?=\s*(?:$|[@?!\[\],;:=)]|\w))"
        ),
        # Scoped to the languages that actually write `cnpj Int` with only
        # whitespace between name and type. SQL is deliberately excluded: a
        # numeric column there is CNPJ011's, and matching both reported the same
        # line twice, which is noise a reader has to reconcile.
        languages=frozenset({"prisma", "graphql", "go"}),
        explanation=(
            "Um tipo de campo inteiro se propaga para o schema gerado e para a coluna de banco por "
            "trás dele."
        ),
        fix="Declare como string ou varchar de tamanho 14.",
    ),
    Rule(
        id="CNPJ023",
        title="CNPJ numérico de largura fixa em layout de arquivo",
        severity=REVIEW,
        pattern=_c(r"cnpj\w*\s*[:=,]\s*(?:9{6,}|0{6,})"),
        explanation=(
            "Cláusulas PIC no estilo COBOL e layouts de largura fixa que declaram o CNPJ como "
            "numérico não conseguem carregar letras."
        ),
        fix="Redeclare o campo como alfanumérico no layout e em todos os consumidores.",
    ),
)


def rules_for_language(language: str) -> tuple[Rule, ...]:
    """Return the rules that apply to *language*."""
    return tuple(rule for rule in RULES if rule.applies_to(language))
