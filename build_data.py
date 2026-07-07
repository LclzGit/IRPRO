#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data.py — gera o arquivo `data.js` consumido pelo IRCSPro.

O IRCSPro é um app estático (HTML + data.js). Este script monta o `data.js`
a partir do catálogo de fontes abaixo, quebrando o texto de cada norma em
artigos no formato que o app espera:

    window.IRPRO_DATA = {
      meta:      { date, app, note },
      sources:   [ {key, short, name, sub, icon, url} ],
      chunks:    [ {s, a, t} ],                         # s=fonte, a=artigo, t=texto
      structure: [ {source, articles:[{art,livro,titulo,capitulo,preview,s}]} ]
    }

Cada fonte pode ter uma SEMENTE verificada (artigos-chave conferidos à mão) e,
quando há acesso à internet, pode ser ENRIQUECIDA com o texto integral baixado
do site oficial.

Uso:
    python3 build_data.py                 # baixa o texto integral e regenera data.js
    python3 build_data.py --offline       # usa só as sementes + placeholders
    python3 build_data.py --only "Lei 9.249/95,Lei 9.430/96"

Notas:
  * Só depende da biblioteca padrão do Python 3.
  * O parser é orientado ao HTML do Planalto (maioria das fontes). Fontes de
    outros sites (normaslegais, legisweb) podem precisar de ajuste manual.
  * Se o download de uma fonte falhar, ela cai na semente (se houver) ou num
    placeholder — o app continua funcionando.
  * CF/88 e CTN são "curados": trazem só os dispositivos relevantes ao IR e NÃO
    são baixados automaticamente (evita puxar a Constituição/o Código inteiros).
  * Confira sempre o texto oficial vigente. Ferramenta de estudo, não fonte oficial.
"""
import sys, os, re, json, html, io, time, argparse
import urllib.request, urllib.error

# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de fontes (key, short, name, sub, icon, url)
# `key` é gravado em cada chunk (chunk.s) — mantenha estável.
# ─────────────────────────────────────────────────────────────────────────────
SOURCES = [
    ("CF/88", "CF/88", "Constituição Federal de 1988",
     "Texto integral — 250 artigos + ADCT (fonte: base comunitária Vade-Mecum)",
     "📕", "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"),
    ("CTN", "CTN", "Código Tributário Nacional",
     "Lei nº 5.172/1966 — texto integral",
     "📕", "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"),
    ("DL 1.598/77", "DL 1.598", "Decreto-Lei nº 1.598/1977",
     "Base do IRPJ / lucro real e escrituração", "📜",
     "https://www.planalto.gov.br/ccivil_03/decreto-lei/del1598.htm"),
    ("Lei 7.689/88", "Lei 7.689", "Lei nº 7.689/1988",
     "Institui a Contribuição Social sobre o Lucro (CSLL)", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l7689.htm"),
    ("Lei 8.981/95", "Lei 8.981", "Lei nº 8.981/1995",
     "Legislação tributária federal — IRPJ, IRPF e CSLL", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l8981.htm"),
    ("Lei 9.249/95", "Lei 9.249", "Lei nº 9.249/1995",
     "IRPJ e CSLL — alíquota, JCP, isenção de lucros/dividendos", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l9249.htm"),
    ("Lei 9.316/96", "Lei 9.316", "Lei nº 9.316/1996",
     "Veda a dedução da CSLL na apuração do lucro real", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l9316.htm"),
    ("Lei 9.430/96", "Lei 9.430", "Lei nº 9.430/1996",
     "IRPJ/CSLL, preços de transferência (texto por OCR — revisar)", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l9430compilada.htm"),
    ("Lei 12.973/14", "Lei 12.973", "Lei nº 12.973/2014",
     "Adequação às normas contábeis / fim do RTT (texto por OCR — revisar)", "📜",
     "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12973.htm"),
    ("Lei 15.079/24", "Lei 15.079", "Lei nº 15.079/2024",
     "Adicional da CSLL — tributação mínima global (Regras GloBE / Pilar 2)", "📜",
     "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/lei/l15079.htm"),
    ("LC 224", "LC 224", "Lei Complementar nº 224/2025",
     "Redução de benefícios/incentivos fiscais federais; altera a LRF e outras LCs",
     "📘", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp224.htm"),
    ("IN RFB 1.700/17", "IN 1.700", "Instrução Normativa RFB nº 1.700/2017",
     "Regulamenta a apuração do IRPJ e da CSLL", "📋",
     "https://www.normaslegais.com.br/legislacao/instrucao-normativa-rfb-1700-2017.htm"),
    ("IN RFB 2.329/26", "IN 2.329", "Instrução Normativa RFB nº 2.329/2026",
     "Altera a IN RFB 2.228/2024 (Adicional da CSLL / regras GloBE)", "📋", ""),
    ("LegisWeb 496991", "LegisWeb", "Norma a identificar (LegisWeb 496991)",
     "Confirmar a norma na importação", "🔖",
     "https://www.legisweb.com.br/legislacao/?id=496991"),
]

# Fontes curadas: usam SÓ a semente (não são baixadas automaticamente).
SEED_ONLY = {"CF/88", "CTN"}

# ─────────────────────────────────────────────────────────────────────────────
# SEMENTES verificadas — dispositivos-chave conferidos manualmente.
# Estrutura: key -> [ (art, texto, (livro, titulo, capitulo)) ]
# ─────────────────────────────────────────────────────────────────────────────
CF_CTX = ("TÍTULO VI — Da Tributação e do Orçamento",
          "CAPÍTULO I — Do Sistema Tributário Nacional")
CTN_CTX = ("LIVRO PRIMEIRO — Sistema Tributário Nacional",
           "TÍTULO III — Impostos",
           "CAPÍTULO III — Impostos sobre o Patrimônio e a Renda")

SEED = {
    "CF/88": [
        ("Art. 145",
         "Art. 145. A União, os Estados, o Distrito Federal e os Municípios poderão instituir os seguintes tributos:\n"
         "I - impostos;\n"
         "II - taxas, em razão do exercício do poder de polícia ou pela utilização, efetiva ou potencial, de serviços públicos específicos e divisíveis, prestados ao contribuinte ou postos a sua disposição;\n"
         "III - contribuição de melhoria, decorrente de obras públicas.\n"
         "§ 1º Sempre que possível, os impostos terão caráter pessoal e serão graduados segundo a capacidade econômica do contribuinte, facultado à administração tributária, especialmente para conferir efetividade a esses objetivos, identificar, respeitados os direitos individuais e nos termos da lei, o patrimônio, os rendimentos e as atividades econômicas do contribuinte.",
         (CF_CTX[0], CF_CTX[1], "SEÇÃO I — Dos Princípios Gerais")),
        ("Art. 153",
         "Art. 153. Compete à União instituir impostos sobre:\n"
         "I - importação de produtos estrangeiros;\n"
         "II - exportação, para o exterior, de produtos nacionais ou nacionalizados;\n"
         "III - renda e proventos de qualquer natureza;\n"
         "IV - produtos industrializados;\n"
         "V - operações de crédito, câmbio e seguro, ou relativas a títulos ou valores mobiliários;\n"
         "VI - propriedade territorial rural;\n"
         "VII - grandes fortunas, nos termos de lei complementar.\n"
         "§ 2º O imposto previsto no inciso III:\n"
         "I - será informado pelos critérios da generalidade, da universalidade e da progressividade, na forma da lei.",
         (CF_CTX[0], CF_CTX[1], "SEÇÃO III — Dos Impostos da União")),
    ],
    "CTN": [
        ("Art. 43",
         "Art. 43. O imposto, de competência da União, sobre a renda e proventos de qualquer natureza tem como fato gerador a aquisição da disponibilidade econômica ou jurídica:\n"
         "I - de renda, assim entendido o produto do capital, do trabalho ou da combinação de ambos;\n"
         "II - de proventos de qualquer natureza, assim entendidos os acréscimos patrimoniais não compreendidos no inciso anterior.\n"
         "§ 1º A incidência do imposto independe da denominação da receita ou do rendimento, da localização, condição jurídica ou nacionalidade da fonte, da origem e da forma de percepção. (Incluído pela Lcp nº 104, de 2001)\n"
         "§ 2º Na hipótese de receita ou de rendimento oriundos do exterior, a lei estabelecerá as condições e o momento em que se dará sua disponibilidade, para fins de incidência do imposto referido neste artigo. (Incluído pela Lcp nº 104, de 2001)",
         CTN_CTX),
        ("Art. 44",
         "Art. 44. A base de cálculo do imposto é o montante, real, arbitrado ou presumido, da renda ou dos proventos tributáveis.",
         CTN_CTX),
        ("Art. 45",
         "Art. 45. Contribuinte do imposto é o titular da disponibilidade a que se refere o artigo 43, sem prejuízo de atribuir a lei essa condição ao possuidor, a qualquer título, dos bens produtores de renda ou dos proventos tributáveis.\n"
         "Parágrafo único. A lei pode atribuir à fonte pagadora da renda ou dos proventos tributáveis a condição de responsável pelo imposto cuja retenção e recolhimento lhe caibam.",
         CTN_CTX),
    ],
    "DL 1.598/77": [
        ("Art. 6",
         "Art. 6º - Lucro real é o lucro líquido do exercício ajustado pelas adições, exclusões ou compensações prescritas ou autorizadas pela legislação tributária.\n"
         "§ 1º - O lucro líquido do exercício é a soma algébrica de lucro operacional (art. 11), dos resultados não operacionais e das participações, e deverá ser determinado com observância dos preceitos da lei comercial.\n"
         "§ 2º - Na determinação do lucro real serão adicionados ao lucro líquido do exercício:\n"
         "a) os custos, despesas, encargos, perdas, provisões, participações e quaisquer outros valores deduzidos na apuração do lucro líquido que, de acordo com a legislação tributária, não sejam dedutíveis na determinação do lucro real;\n"
         "b) os resultados, rendimentos, receitas e quaisquer outros valores não incluídos na apuração do lucro líquido que, de acordo com a legislação tributária, devam ser computados na determinação do lucro real.\n"
         "§ 3º - Na determinação do lucro real poderão ser excluídos do lucro líquido do exercício:\n"
         "a) os valores cuja dedução seja autorizada pela legislação tributária e que não tenham sido computados na apuração do lucro líquido do exercício;\n"
         "b) os resultados, rendimentos, receitas e quaisquer outros valores incluídos na apuração do lucro líquido que, de acordo com a legislação tributária, não sejam computados no lucro real;\n"
         "c) os prejuízos de exercícios anteriores, observado o disposto no artigo 64.",
         ("", "TÍTULO I — Imposto sobre o Lucro das Pessoas Jurídicas", "Lucro Real")),
    ],
    "Lei 7.689/88": [
        ("Art. 1",
         "Art. 1º Fica instituída contribuição social sobre o lucro das pessoas jurídicas, destinada ao financiamento da seguridade social.",
         ("", "Contribuição Social sobre o Lucro", "")),
        ("Art. 2",
         "Art. 2º A base de cálculo da contribuição é o valor do resultado do exercício, antes da provisão para o imposto de renda.",
         ("", "Contribuição Social sobre o Lucro", "")),
    ],
    "Lei 9.249/95": [
        ("Art. 3",
         "Art. 3º A alíquota do imposto de renda das pessoas jurídicas é de quinze por cento.\n"
         "§ 1º A parcela do lucro real, presumido ou arbitrado, que exceder o valor resultante da multiplicação de R$ 20.000,00 (vinte mil reais) pelo número de meses do respectivo período de apuração, sujeita-se à incidência de adicional de imposto de renda à alíquota de dez por cento.\n"
         "§ 2º O disposto no parágrafo anterior aplica-se, inclusive, nos casos de incorporação, fusão ou cisão e de extinção da pessoa jurídica pelo encerramento da liquidação.\n"
         "§ 3º O disposto neste artigo aplica-se, igualmente, à pessoa jurídica que explore atividade rural de que trata a Lei nº 8.023, de 12 de abril de 1990.\n"
         "§ 4º O valor do adicional será recolhido integralmente, não sendo permitidas quaisquer deduções.",
         ("", "IRPJ — Disposições Gerais", "")),
        ("Art. 9",
         "Art. 9º A pessoa jurídica poderá deduzir, para efeitos da apuração do lucro real, os juros pagos ou creditados individualizadamente a titular, sócios ou acionistas, a título de remuneração do capital próprio, calculados sobre as contas do patrimônio líquido e limitados à variação, pro rata dia, da Taxa de Juros de Longo Prazo - TJLP.\n"
         "§ 1º O efetivo pagamento ou crédito dos juros fica condicionado à existência de lucros, computados antes da dedução dos juros, ou de lucros acumulados e reservas de lucros, em montante igual ou superior ao valor de duas vezes os juros a serem pagos ou creditados.",
         ("", "Juros sobre o Capital Próprio", "")),
        ("Art. 10",
         "Art. 10. Os lucros ou dividendos calculados com base nos resultados apurados a partir do mês de janeiro de 1996, pagos ou creditados pelas pessoas jurídicas tributadas com base no lucro real, presumido ou arbitrado, não ficarão sujeitos à incidência do imposto de renda na fonte, nem integrarão a base de cálculo do imposto de renda do beneficiário, pessoa física ou jurídica, domiciliado no País ou no exterior.",
         ("", "Lucros e Dividendos", "")),
    ],
    "Lei 9.316/96": [
        ("Art. 1",
         "Art. 1º O valor da contribuição social sobre o lucro líquido não poderá ser deduzido para efeito de determinação do lucro real, nem de sua própria base de cálculo.\n"
         "Parágrafo único. Os valores da contribuição social a que se refere este artigo, registrados como custo ou despesa, deverão ser adicionados ao lucro líquido do respectivo período de apuração para efeito de determinação do lucro real e de sua própria base de cálculo.",
         ("", "CSLL — não dedutibilidade", "")),
    ],
    "Lei 9.430/96": [
        ("Art. 1",
         "Art. 1º A partir do ano-calendário de 1997, o imposto de renda das pessoas jurídicas será determinado com base no lucro real, presumido, ou arbitrado, por períodos de apuração trimestrais, encerrados nos dias 31 de março, 30 de junho, 30 de setembro e 31 de dezembro de cada ano-calendário, observada a legislação vigente, com as alterações desta Lei.",
         ("", "Apuração do IRPJ e da CSLL", "")),
    ],
}

HEADING_RE = re.compile(
    r'^(LIVRO|T[ÍI]TULO|CAP[ÍI]TULO|SUBSE[ÇC][ÃA]O|SE[ÇC][ÃA]O)\b', re.IGNORECASE)
ART_RE = re.compile(r'^Art\.?\s*(\d+)\s*([ºªoa\.\-]?)\s*(-?[A-Z]?)', re.IGNORECASE)


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (IRPro build_data.py)",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def html_to_text(doc):
    m = re.search(r'<body[^>]*>(.*)</body>', doc, re.IGNORECASE | re.DOTALL)
    if m:
        doc = m.group(1)
    doc = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', doc, flags=re.IGNORECASE | re.DOTALL)
    doc = re.sub(r'<br\s*/?>', '\n', doc, flags=re.IGNORECASE)
    doc = re.sub(r'</p>|</div>|</tr>|</h[1-6]>', '\n', doc, flags=re.IGNORECASE)
    doc = re.sub(r'<[^>]+>', '', doc)
    doc = html.unescape(doc).replace('\xa0', ' ')
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in doc.split('\n')]
    return [ln for ln in lines if ln]


def parse(lines, key):
    """Best-effort split of legal text into articles + structural context."""
    livro = titulo = capitulo = ""
    chunks, arts = [], []
    cur_art, cur_buf = None, []

    def flush():
        if cur_art and cur_buf:
            text = "\n".join(cur_buf).strip()
            if text:
                chunks.append({"s": key, "a": cur_art, "t": text})
                arts.append({"art": cur_art, "livro": livro, "titulo": titulo,
                             "capitulo": capitulo, "preview": text[:110], "s": key})

    for ln in lines:
        h = HEADING_RE.match(ln)
        if h:
            flush(); cur_art, cur_buf = None, []
            word = h.group(1).upper()
            if word.startswith("LIVRO"):
                livro, titulo, capitulo = ln, "", ""
            elif word.startswith(("TÍTULO", "TITULO")):
                titulo, capitulo = ln, ""
            elif word.startswith(("CAPÍTULO", "CAPITULO")):
                capitulo = ln
            continue
        a = ART_RE.match(ln)
        if a:
            flush()
            num = a.group(1); suf = (a.group(3) or "").upper()
            cur_art = "Art. " + num + (suf if suf.startswith("-") else "")
            cur_buf = [ln]
        elif cur_art:
            cur_buf.append(ln)
    flush()
    return chunks, arts


def from_seed(key):
    chunks, arts = [], []
    for art, text, ctx in SEED[key]:
        livro, titulo, capitulo = (ctx + ("", "", ""))[:3]
        chunks.append({"s": key, "a": art, "t": text})
        arts.append({"art": art, "livro": livro, "titulo": titulo,
                     "capitulo": capitulo, "preview": text[:110], "s": key})
    return chunks, arts


def placeholder(key, name, sub, url):
    art = "(a preencher)"
    text = ("Conteúdo ainda não importado.\n\n"
            f"Fonte: {name} — {sub}.\n"
            f"Texto oficial: {url}\n\n"
            "Rode `python3 build_data.py` (num ambiente com acesso à internet) "
            "para baixar e converter o texto desta norma para o formato do app.")
    return ([{"s": key, "a": art, "t": text}],
            [{"art": art, "livro": "", "titulo": name, "capitulo": "",
              "preview": "Conteúdo ainda não importado — rode build_data.py.", "s": key}])


def seed_or_placeholder(key, name, sub, url):
    return from_seed(key) if key in SEED else placeholder(key, name, sub, url)


# ── Conteúdo local já extraído (data/<slug>.json) ────────────────────────────
# Prioridade máxima: quando existe o JSON da fonte, ele é a base do app.
# Cada registro: {art, livro, titulo, capitulo, text, preview}.
# Estes arquivos foram gerados a partir dos PDFs oficiais (ver tools/pdf_to_json.py).
def _slug(key):
    return re.sub(r'[^A-Za-z0-9]+', '_', key).strip('_')

def local_json(key):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", _slug(key) + ".json")
    if not os.path.exists(path):
        return None
    recs = json.load(io.open(path, encoding="utf-8"))
    chunks = [{"s": key, "a": r["art"], "t": r["text"]} for r in recs]
    arts = [{"art": r["art"], "livro": r.get("livro", ""),
             "titulo": r.get("titulo", ""), "capitulo": r.get("capitulo", ""),
             "preview": r.get("preview", r["text"][:110]), "s": key} for r in recs]
    return chunks, arts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="não baixa nada")
    ap.add_argument("--only", default="", help="keys separadas por vírgula")
    ap.add_argument("--out", default="data.js")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    chunks, structure = [], []
    for key, short, name, sub, icon, url in SOURCES:
        lj = local_json(key)
        fetchable = (not args.offline) and (key not in SEED_ONLY) and \
                    (not only or key in only)
        if lj is not None:
            c, a = lj
            print(f"• {key}: {len(c)} artigos (data/{_slug(key)}.json)", file=sys.stderr)
        elif fetchable:
            try:
                print(f"↓ {key}: {url}", file=sys.stderr)
                c, a = parse(html_to_text(fetch(url)), key)
                if not c:
                    raise ValueError("nenhum artigo reconhecido")
                print(f"  ✓ {len(c)} artigos", file=sys.stderr)
                time.sleep(1)
            except Exception as e:
                print(f"  ✗ falhou ({e}) — usando semente/placeholder", file=sys.stderr)
                c, a = seed_or_placeholder(key, name, sub, url)
        else:
            c, a = seed_or_placeholder(key, name, sub, url)
        chunks += c
        structure.append({"source": key, "articles": a})

    data = {
        "meta": {"date": time.strftime("%Y-%m-%d"), "app": "IRCSPro",
                 "note": "Base de estudo das legislações de IR/CSLL. Confira sempre "
                         "o texto oficial vigente no Planalto/Receita Federal."},
        "sources": [{"key": k, "short": sh, "name": n, "sub": s, "icon": ic, "url": u}
                    for (k, sh, n, s, ic, u) in SOURCES],
        "chunks": chunks,
        "structure": structure,
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    out = ("// IRCSPro — base de dados das legislações de IR/CSLL.\n"
           "// Gerado por build_data.py. Formato documentado no topo de build_data.py.\n"
           "window.IRPRO_DATA = " + body + ";\n")
    with io.open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\n✓ {args.out}: {len(chunks)} chunks, {len(structure)} fontes", file=sys.stderr)


if __name__ == "__main__":
    main()
