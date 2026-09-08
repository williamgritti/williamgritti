# Launch content — ready to post

Everything here is written to be pasted with minimal editing. Every technical
claim was verified by execution during this session.

Nothing here says any library is unprepared, because that was tested twice and
is false both times. **All five libraries checked support the alphanumeric
CNPJ.** One of them, `@brazilian-utils/brazilian-utils`, requires opting in with
`{ version: 2 }` and defaults to numeric-only for backwards compatibility -- so
its default rejects an alphanumeric CNPJ while the library itself is entirely
capable of validating one. That distinction matters and must not be flattened
into "it is broken".

**The honest angle, and the only one used below.** Five libraries were tested by
execution and all five support the alphanumeric CNPJ: `brutils` and
`validate-docbr` in Python, `cpf-cnpj-validator`, `validation-br` and
`@brazilian-utils/brazilian-utils` in JavaScript. The last one gates it behind
`{ version: 2 }`, so its *default* still rejects an alphanumeric CNPJ.

The useful, checkable point is therefore about defaults, not readiness: your
library probably handles this already, but check whether it needs a flag.

And the point that carries the whole piece: even a fully ready library does not
make a *system* ready, because what breaks is the code around the validator, and
no dependency upgrade touches any of it.

---

## 1. Technical article — the anchor piece

Post on dev.to, Medium or your own site first, so everything else can link to it.

> **Título:** Seu código quebra em julho de 2026 e não é culpa da sua biblioteca de CNPJ
>
> Em julho de 2026 o CNPJ passa a aceitar letras. A Instrução Normativa RFB nº
> 2.229/2024 mantém 14 posições, mas as doze primeiras passam a aceitar `A-Z`
> além de `0-9`. Os dois últimos dígitos continuam numéricos.
>
> A primeira coisa que todo mundo faz é conferir a biblioteca de validação.
> Testei cinco, rodando de verdade: **todas as cinco suportam o alfanumérico.**
> `brutils` e `validate-docbr` em Python; `cpf-cnpj-validator`, `validation-br` e
> `@brazilian-utils/brazilian-utils` em JavaScript.
>
> Uma pegadinha: a `@brazilian-utils` exige opt-in. `isValidCNPJ(cnpj)` recusa um
> CNPJ alfanumérico; `isValidCNPJ(cnpj, { version: 2 })` aceita. O padrão continua
> numérico por retrocompatibilidade. Vale conferir se a sua também tem uma flag
> dessas.
>
> Mas é exatamente aí que mora o perigo. **Você atualiza a dependência, o teste
> passa, e você acha que terminou.**
>
> Não terminou. O que quebra é o código em volta do validador.
>
> ### O que realmente quebra
>
> Peguei um CNPJ legado válido (`11222333000181`) e um alfanumérico válido
> (`12ABC34501DE35`) e rodei os dois contra os padrões que existem em qualquer
> sistema brasileiro:
>
> | Padrão | Legado | Alfanumérico |
> |---|---|---|
> | `^\d{14}$` | aceita | **rejeita** |
> | `cnpj.isdigit()` | aceita | **rejeita** |
> | `int(cnpj)` | aceita | **estoura** |
> | coluna `BIGINT` | cabe | **não armazena** |
> | `re.sub(r"\D", "", cnpj)` | intacto | **corrompe em silêncio** |
>
> O último é o pior. Ele não levanta exceção. Ele devolve um valor mais curto e
> errado, que vai falhar na validação em outro lugar, horas depois, com uma
> mensagem que não tem nada a ver com a causa.
>
> Nenhum desses é resolvido por `pip install --upgrade`. Estão no seu código, não
> na dependência.
>
> ### O de maior prazo é o banco
>
> Se o CNPJ está numa coluna `BIGINT` — e está, em muito sistema legado, porque
> "é só número mesmo" — a migração não é trocar uma regex. É `ALTER TABLE`,
> backfill, e toda chave estrangeira que aponta pra ela. Esse é o item que precisa
> começar primeiro, e é o que ninguém descobre até tentar gravar o primeiro CNPJ
> com letra.
>
> ### Como achar isso no seu projeto
>
> Escrevi um scanner pra isso:
>
> ```bash
> pip install fiscalkit
> fiscalkit scan .
> ```
>
> ```
> QUEBRA app/fornecedor.py:4  [CNPJ001] Regex de CNPJ que aceita apenas dígitos
>        CNPJ_RE = re.compile(r"^\d{14}$")
>        correção: Use [0-9A-Z]{12}[0-9]{2}: as doze primeiras posições aceitam letras e os
>                  dois dígitos verificadores continuam numéricos.
>
> QUEBRA app/fornecedor.py:8  [CNPJ012] CNPJ mapeado como campo inteiro no ORM
>        cnpj = models.BigIntegerField(unique=True)
>        correção: Use um campo de caractere com tamanho 14.
>
> QUEBRA schema.sql:3  [CNPJ011] Coluna de CNPJ declarada com tipo numérico
>        cnpj BIGINT NOT NULL UNIQUE
>        correção: Migre para CHAR(14) ou VARCHAR(14). Planeje o backfill e todas as chaves
>                  estrangeiras que referenciam esta coluna.
>
> 2 arquivo(s) analisado(s), 3 ocorrência(s): 3 quebra, 0 risco, 0 rever
> ```
>
> E ele não para no diagnóstico. Nas regras em que a correção é mecânica, ele
> escreve o patch:
>
> ```bash
> fiscalkit scan . --diff   # mostra o patch, no formato do git apply
> fiscalkit scan . --fix    # aplica
> ```
>
> ```diff
> --- a/fornecedor.py
> +++ b/fornecedor.py
> @@ -2,8 +2,8 @@
>  
>  
>  def normalizar(valor):
> -    return re.sub(r"\D", "", valor)
> +    return re.sub(r"[^0-9A-Z]", "", valor)
>  
>  
>  def validar(cnpj):
> -    return bool(re.match(r"^\d{14}$", cnpj))
> +    return bool(re.match(r"^[0-9A-Z]{12}[0-9]{2}$", cnpj))
> ```
>
> Só quatro das quatorze regras têm correção automática, e isso é de propósito.
> `int(cnpj)` não dá pra consertar editando aquela linha: o código em volta é que
> precisa parar de tratar CNPJ como número. Chutar ali geraria um diff plausível
> que muda o comportamento em silêncio, que é exatamente o que essa ferramenta
> existe pra evitar. Essas ficam reportadas e sem patch.
>
> São 14 regras em Python, JavaScript/TypeScript, SQL, Java, PHP, Go, C# e Ruby,
> mais os formatos de schema que geram esse código: OpenAPI/JSON Schema, Protobuf,
> Prisma e GraphQL. Sai com código diferente de zero só quando a quebra é certa,
> então dá pra usar como gate de build. Tem GitHub Action e saída SARIF, que
> coloca o achado anotado na linha do PR.
>
> Cada regra tem um teste que prova que o padrão aceita o CNPJ legado e rejeita ou
> corrompe o alfanumérico. Regra que não demonstra essa diferença não entra.
>
> É MIT, o código está em github.com/williamgritti/fiscalkit, e se você achar um
> padrão que ele não pega, abre uma issue — é exatamente o tipo de contribuição
> que interessa.
>
> Julho de 2026 não vai ser adiado por você não ter olhado.
>
> ---
>
> *A ferramenta é MIT e vai continuar sendo. Se ela te poupou uma tarde de
> `grep`, tem um [Ko-fi](https://ko-fi.com/SEU_HANDLE) aqui — sem paywall, sem
> versão pro, sem newsletter.*

---

## 2. Reddit — r/brdev

Post as text, not a link. Link posts get ignored there.

> **Título:** Testei 5 libs de CNPJ pro alfanumérico de 2026. Todas passam — uma só com opt-in. E o problema maior nem é a lib.
>
> Fiz o teste que todo mundo faz: joguei um CNPJ alfanumérico válido em cinco
> libs, com os casos de borda junto (DV errado, base adulterada, letra na posição
> do DV). **Todas as cinco acertaram**: `brutils`, `validate-docbr`,
> `cpf-cnpj-validator`, `validation-br` e `@brazilian-utils/brazilian-utils`.
>
> Detalhe que custou meia hora: na `@brazilian-utils` é opt-in.
> `isValidCNPJ(cnpj)` recusa alfanumérico, `isValidCNPJ(cnpj, { version: 2 })`
> aceita — o padrão segue numérico por retrocompatibilidade. Confere se a sua tem
> flag parecida.
>
> Aí testei o que tem em volta do validador, que é onde eu trabalho de verdade:
>
> - `^\d{14}$` → rejeita
> - `.isdigit()` → rejeita
> - `int(cnpj)` → estoura
> - coluna `BIGINT` → nem armazena
> - `re.sub(r"\D","",cnpj)` → **corrompe calado**, sem exceção nenhuma
>
> Esse último me preocupa mais que todos os outros juntos, porque não falha na
> hora. Devolve um valor mais curto e errado que só vai dar problema depois.
>
> Fiz um scanner que acha esses padrões (`pip install fiscalkit`,
> `fiscalkit scan .`). MIT, 14 regras, 8 linguagens (mais OpenAPI, Protobuf,
> Prisma e GraphQL), com Action e SARIF pra anotar no PR.
>
> Nas regras em que a correção é mecânica ele ainda escreve o patch
> (`--diff` mostra, `--fix` aplica). São só 4 das 14, de propósito: `int(cnpj)`
> não se conserta naquela linha, e um diff chutado ali mudaria comportamento em
> silêncio.
>
> Quem aí já mexeu na coluna do banco? Tô curioso pra saber se tem gente que já
> migrou de `BIGINT` ou se todo mundo tá deixando pra junho de 2026.

---

## 3. LinkedIn

Shorter, and the CTA is the conversation, not the install.

> Em julho de 2026 o CNPJ aceita letras (IN RFB 2.229/2024).
>
> A primeira reação é conferir a biblioteca de validação. Testei cinco: todas
> suportam. Uma (`@brazilian-utils/brazilian-utils`) só com opt-in — o padrão
> ainda é numérico.
>
> Ou seja, a sua provavelmente já está pronta — e é justamente por isso que é
> perigoso. Você atualiza a dependência, o teste passa, e acha que acabou.
>
> O que quebra é o resto:
>
> → `^\d{14}$` na borda da API
> → `int(cnpj)` pra tirar zero à esquerda
> → a coluna `BIGINT` no banco
> → `re.sub(r"\D","",cnpj)`, que não dá erro: só corrompe
>
> Nenhum resolvido por atualizar dependência.
>
> O do banco é o que precisa começar antes: `ALTER TABLE`, backfill, e todas as
> FKs que apontam pra coluna.
>
> Publiquei um scanner open source que acha esses padrões em Python, JS/TS, SQL,
> Java, PHP, Go, C# e Ruby: `pip install fiscalkit && fiscalkit scan .`
>
> Onde a correção é mecânica, ele escreve o patch (`--fix`). Onde não é, ele
> reporta e não chuta.
>
> Se você roda sistema fiscal e quer saber o tamanho do estrago antes de junho,
> me chama.

---

## 4. Instagram — carrossel de 10 slides

For the Fiscal Tech audience. Keep the visual language you already use.

1. **JULHO DE 2026** / O CNPJ vai aceitar letras. / Seu sistema já sabe disso?
2. A IN RFB 2.229/2024 mantém 14 posições. / As 12 primeiras aceitam A-Z. / Os 2 dígitos finais continuam numéricos.
3. "Mas minha lib já atualizou." / Testei 5: todas suportam. / Uma só com opt-in — confere a flag.
4. **E é por isso que é perigoso.** / Você atualiza, o teste passa, / e acha que terminou.
5. O que quebra é o código em volta. / Nenhum deles é dependência.
6. `^\d{14}$` → REJEITA um CNPJ válido
7. `int(cnpj)` → ESTOURA / coluna BIGINT → NEM ARMAZENA
8. `re.sub(r"\D","",cnpj)` / **Esse não dá erro.** / Ele corrompe calado. / E falha depois, longe da causa.
9. O do banco é o mais urgente: / ALTER TABLE + backfill + todas as FKs. / Isso não se faz em junho.
10. `pip install fiscalkit` / `fiscalkit scan .` / Acha, e onde dá, corrige com `--fix`. / Open source, MIT. / Link na bio.

**Legenda:** Em julho de 2026 o CNPJ passa a aceitar letras. Testei cinco
bibliotecas de validação: todas suportam, uma só com opt-in. Mas o problema maior
é o código em volta delas: regex
numérica, cast pra inteiro, coluna BIGINT. Nada disso se resolve atualizando
dependência. Fiz um scanner open source que acha esses padrões no seu projeto.
Link na bio. #cnpj #devbr #python #fiscal #ir2026

---

## Sequencing

1. Publish the package (`./release.sh publish`) — every post links to something
   installable, or the post is wasted.
2. Article first, so the others have an anchor to link.
3. r/brdev the same day, LinkedIn the next morning, Instagram after that.
4. Answer every comment in the first 48 hours. On r/brdev especially, the replies
   are where the credibility is won, and the questions tell you which rule to
   write next.

## What not to do

- Do not post the same text everywhere. Each platform gets its own version above.
- Do not claim any library is unprepared. All five tested support the
  alphanumeric CNPJ; `@brazilian-utils/brazilian-utils` merely requires
  `{ version: 2 }` and defaults to numeric-only. Calling that "not ready" is
  wrong, unfair to its maintainers, and checkable in seconds. I made exactly that
  mistake here before running the option.
- Do not lead with consulting. Lead with the finding; the work follows from it.
- **The Ko-fi line goes in the article only.** Not on r/brdev, where a donation
  ask on a first post reads as self-promotion and costs you the thread that was
  the whole point. Not on LinkedIn, where the call to action is already the
  conversation. The article is your own turf and a footer there is unremarkable.
- Replace `SEU_HANDLE` before posting, or delete the line. A Ko-fi link that
  404s in front of the only audience that matters is worse than no link.
- Do not post before the package installs. A broken `pip install` in front of the
  only audience that matters is not recoverable in the same news cycle.
