# Launch content — ready to post

Everything here is written to be pasted with minimal editing. Every technical
claim was verified by execution during this session; nothing asserts a
competitor is broken, because that claim was tested and is false.

**The honest angle, and the only one used below:** validation libraries already
handle the alphanumeric CNPJ. `brutils`, `validate-docbr` and `cnpj-alfanumerico`
all get it right. What breaks is the code *around* the validator, and no
dependency upgrade touches it. That is true, verifiable in ten seconds, and it is
what makes the scanner worth existing.

Do not claim the libraries are unprepared. A Brazilian developer will check, find
you wrong, and stop reading.

---

## 1. Technical article — the anchor piece

Post on dev.to, Medium or your own site first, so everything else can link to it.

> **Título:** Seu código quebra em julho de 2026 e não é culpa da sua biblioteca de CNPJ
>
> Em julho de 2026 o CNPJ passa a aceitar letras. A Instrução Normativa RFB nº
> 2.229/2024 mantém 14 posições, mas as doze primeiras passam a aceitar `A-Z`
> além de `0-9`. Os dois últimos dígitos continuam numéricos.
>
> A primeira coisa que todo mundo faz é conferir a biblioteca de validação. E aí
> vem a boa notícia: **elas já estão prontas.** `brutils`, `validate-docbr` e
> `cnpj-alfanumerico` implementam a regra corretamente — testei as três contra um
> CNPJ alfanumérico válido, contra dígitos verificadores errados, contra uma base
> adulterada e contra uma letra na posição do DV. Todas acertaram todos os casos.
>
> É exatamente por isso que esse problema é perigoso. **Você atualiza a
> dependência, o teste passa, e você acha que terminou.**
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
> QUEBRA app/fornecedor.py:8  [CNPJ012] CNPJ mapeado como campo inteiro no ORM
>        cnpj = models.BigIntegerField(unique=True)
>        correcao: Use um campo de caractere de tamanho 14.
>
> QUEBRA schema.sql:3  [CNPJ011] Coluna CNPJ declarada como tipo numérico
>        cnpj BIGINT NOT NULL UNIQUE,
> ```
>
> São 12 regras em Python, JavaScript/TypeScript, SQL, Java, PHP, Go, C# e Ruby.
> Sai com código diferente de zero só quando a quebra é certa, então dá pra usar
> como gate de build. Tem GitHub Action e saída SARIF, que coloca o achado
> anotado na linha do PR.
>
> Cada regra tem um teste que prova que o padrão aceita o CNPJ legado e rejeita ou
> corrompe o alfanumérico. Regra que não demonstra essa diferença não entra.
>
> É MIT, o código está em github.com/williamgritti/fiscalkit, e se você achar um
> padrão que ele não pega, abre uma issue — é exatamente o tipo de contribuição
> que interessa.
>
> Julho de 2026 não vai ser adiado por você não ter olhado.

---

## 2. Reddit — r/brdev

Post as text, not a link. Link posts get ignored there.

> **Título:** Testei se as libs de CNPJ estão prontas pro alfanumérico de 2026. Estão. O problema é outro.
>
> Fiz o teste que todo mundo faz: peguei `brutils`, `validate-docbr` e
> `cnpj-alfanumerico` e joguei um CNPJ alfanumérico válido nelas. Passaram todas,
> inclusive nos casos de borda (DV errado, base adulterada, letra na posição do
> DV).
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
> `fiscalkit scan .`). MIT, 12 regras, 8 linguagens, com Action e SARIF pra anotar
> no PR.
>
> Quem aí já mexeu na coluna do banco? Tô curioso pra saber se tem gente que já
> migrou de `BIGINT` ou se todo mundo tá deixando pra junho de 2026.

---

## 3. LinkedIn

Shorter, and the CTA is the conversation, not the install.

> Em julho de 2026 o CNPJ aceita letras (IN RFB 2.229/2024).
>
> A primeira reação é conferir a biblioteca de validação. Testei as principais:
> já estão prontas.
>
> É justamente por isso que é perigoso. Você atualiza a dependência, o teste
> passa, e acha que acabou.
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
> Se você roda sistema fiscal e quer saber o tamanho do estrago antes de junho,
> me chama.

---

## 4. Instagram — carrossel de 10 slides

For the Fiscal Tech audience. Keep the visual language you already use.

1. **JULHO DE 2026** / O CNPJ vai aceitar letras. / Seu sistema já sabe disso?
2. A IN RFB 2.229/2024 mantém 14 posições. / As 12 primeiras aceitam A-Z. / Os 2 dígitos finais continuam numéricos.
3. "Mas minha biblioteca já atualizou." / Já. Testei três delas. / Todas passaram.
4. **E é por isso que é perigoso.** / Você atualiza, o teste passa, / e acha que terminou.
5. O que quebra é o código em volta. / Nenhum deles é dependência.
6. `^\d{14}$` → REJEITA um CNPJ válido
7. `int(cnpj)` → ESTOURA / coluna BIGINT → NEM ARMAZENA
8. `re.sub(r"\D","",cnpj)` / **Esse não dá erro.** / Ele corrompe calado. / E falha depois, longe da causa.
9. O do banco é o mais urgente: / ALTER TABLE + backfill + todas as FKs. / Isso não se faz em junho.
10. `pip install fiscalkit` / `fiscalkit scan .` / Open source, MIT. / Link na bio.

**Legenda:** Em julho de 2026 o CNPJ passa a aceitar letras. As bibliotecas de
validação já estão prontas — testei. O problema é o código em volta delas: regex
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
- Do not claim any library is unprepared. It is false and it is checkable.
- Do not lead with consulting. Lead with the finding; the work follows from it.
- Do not post before the package installs. A broken `pip install` in front of the
  only audience that matters is not recoverable in the same news cycle.
