# IRCSPro

Plataforma de estudos da legislação do **Imposto de Renda** (IRPF / IRPJ / IRRF)
e da **Contribuição Social sobre o Lucro Líquido (CSLL)**.

App estático (roda direto no navegador, sem servidor), construído sobre o mesmo
framework do [ReformaPro](https://lclzgit.github.io/reformapro/): busca por
relevância, mapa da estrutura das normas (Livro › Título › Capítulo), leitor com
anotações que ficam salvas no navegador, glossário e modo escuro.

## Como usar

Abra o `index.html` no navegador — ou publique no GitHub Pages e acesse
`https://lclzgit.github.io/irpro/`.

Módulos:

| Módulo | O que faz |
|--------|-----------|
| 🔍 **Busca** | Busca por palavras‑chave em todas as fontes, ranqueada por relevância, com filtro por norma. |
| 🗺️ **Mapa** | Navega pela estrutura (Livro / Título / Capítulo / artigos). |
| 📖 **Leitor** | Lê o texto integral e adiciona anotações pessoais (`localStorage`). |
| 📌 **Anotações** | Reúne todas as anotações; exporta/importa em JSON. |

## Arquivos

```
index.html            App (HTML + CSS + JS embutido; carrega os dados de data.js)
data.js               Base de dados das legislações (window.IRPRO_DATA) — GERADO
data/<fonte>.json     Texto integral já extraído de cada norma (fonte da verdade)
build_data.py         Monta o data.js a partir de data/, sementes e/ou download
tools/pdf_to_json.py  Converte o PDF oficial de uma norma em data/<fonte>.json
```

Pipeline dos dados:

```
PDF oficial ──tools/pdf_to_json.py──▶ data/<fonte>.json ──build_data.py──▶ data.js ──▶ app
```

> As anotações ficam no `localStorage` do domínio. Como IRCSPro e ReformaPro
> compartilhariam o mesmo domínio (`lclzgit.github.io`), as chaves aqui usam o
> prefixo `irp_` (o ReformaPro usa `rp_`), então as anotações **não colidem**.

## Formato dos dados (`data.js`)

```js
window.IRPRO_DATA = {
  meta: { date, app, note },
  sources: [ { key, short, name, sub, icon, url } ],   // catálogo de normas
  chunks:  [ { s, a, t } ],                            // s=fonte(key), a=artigo, t=texto
  structure: [ { source, articles: [ { art, livro, titulo, capitulo, preview, s } ] } ]
};
```

- `chunks` é o que a **Busca** e o **Leitor** exibem.
- `structure` é o que o **Mapa** e a navegação do Leitor usam.
- `sources[].key` deve ser igual ao `chunk.s` correspondente.

Toda a interface (pills do menu, filtros de fonte, cards do leitor, filtros das
anotações) é montada **a partir de `SOURCES`** — para incluir/remover uma norma,
basta editar o catálogo e regerar o `data.js`.

## Populando as legislações

### Texto integral já importado (de PDFs oficiais → `data/`)

| Fonte | Artigos |
|-------|---------|
| **CTN** (Lei 5.172/66) | 211 (texto integral) |
| **DL 1.598/77** | 89 (texto integral) |
| **Lei 15.079/24** | 43 (texto integral) |
| **IN RFB 2.329/26** | 2 (altera a IN RFB 2.228/2024) |

Para adicionar uma norma a partir do PDF oficial:

```bash
pip install pymupdf
python3 tools/pdf_to_json.py caminho/da/lei.pdf --key "Lei 9.430/96"
python3 build_data.py --offline          # regenera o data.js
```

> ⚠️ PDFs **escaneados (imagem)** não têm camada de texto e não podem ser
> extraídos sem OCR — foi o caso do PDF da Lei 12.973/14 enviado.

### Dispositivos-chave conferidos à mão (semente)

Para as fontes ainda sem PDF, o `data.js` traz **texto real, conferido à mão**,
dos dispositivos fundamentais:

| Fonte | Artigos com texto verificado |
|-------|------------------------------|
| **CF/88** | art. 145 (§1º) · art. 153 (III e §2º) |
| **CTN** | arts. 43 a 45 (fato gerador, base de cálculo, contribuinte) |
| **DL 1.598/77** | art. 6º (lucro real; adições e exclusões) |
| **Lei 7.689/88** | arts. 1º e 2º (instituição e base de cálculo da CSLL) |
| **Lei 9.249/95** | art. 3º (alíquota + adicional) · art. 9º (JCP) · art. 10 (isenção de lucros/dividendos) |
| **Lei 9.316/96** | art. 1º (CSLL não dedutível) |
| **Lei 9.430/96** | art. 1º (apuração trimestral) |

As demais normas (Lei 8.981/95, Lei 12.973/14, Lei 15.079/24, LC 224,
IN RFB 1.700/17 e a norma LegisWeb) trazem um **placeholder** com o link oficial,
aguardando importação do texto integral.

Para importar o texto real, rode num ambiente **com acesso à internet**:

```bash
python3 build_data.py            # baixa todas as fontes e regenera data.js
python3 build_data.py --offline  # regenera só com placeholders + semente CTN
python3 build_data.py --only "CTN,Lei 9.249/95"
```

O parser é orientado ao HTML do **Planalto** (a maior parte das fontes). Fontes
de outros sites (`normaslegais`, `legisweb`) podem exigir ajuste manual —
**revise o resultado** antes de publicar. Se o download de uma fonte falhar, ela
volta ao placeholder e o app continua funcionando.

> ⚠️ **Nota sobre este ambiente.** O `build_data.py` **não** pôde ser executado
> aqui: a política de rede desta sessão bloqueia o acesso a `planalto.gov.br` e
> aos demais sites (403). Por isso o `data.js` foi entregue com a semente do CTN
> + placeholders. Rode o script na sua máquina para baixar o texto completo.

## Normas incluídas no catálogo

Constituição Federal/88 · CTN (Lei 5.172/66) · DL 1.598/77 · Lei 7.689/88 (CSLL) ·
Lei 8.981/95 · Lei 9.249/95 · Lei 9.316/96 · Lei 9.430/96 · Lei 12.973/14 ·
Lei 15.079/24 · LC 224 · IN RFB 1.700/17 · (LegisWeb 496991 — a identificar).

> Sempre confira o **texto oficial vigente** no Planalto / Receita Federal. Este
> app é ferramenta de estudo, não fonte oficial.
