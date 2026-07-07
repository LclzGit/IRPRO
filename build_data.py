#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data.py — gera o arquivo `data.js` consumido pelo IR Pro.

O IR Pro é um app estático (HTML + data.js). Este script monta o `data.js`
a partir do catálogo de fontes abaixo, baixando o texto oficial de cada norma
e quebrando-o em artigos no formato que o app espera:

    window.IRPRO_DATA = {
      meta:      { date, app, note },
      sources:   [ {key, short, name, sub, icon, url} ],
      chunks:    [ {s, a, t} ],                         # s=fonte, a=artigo, t=texto
      structure: [ {source, articles:[{art,livro,titulo,capitulo,preview,s}]} ]
    }

Uso:
    python3 build_data.py                 # baixa tudo e regenera data.js
    python3 build_data.py --offline       # não baixa nada (placeholders + semente CTN)
    python3 build_data.py --only CTN,Lei 9.249/95

Observações:
  * Depende só da biblioteca padrão do Python 3.
  * O parser é orientado ao HTML do Planalto (a maioria das fontes). Fontes de
    outros sites (normaslegais, legisweb) podem precisar de ajuste manual —
    reveja o resultado antes de publicar.
  * Se o download de uma fonte falhar, ela recebe um placeholder (o app continua
    funcionando) e o CTN mantém a semente verificada abaixo.
"""
import sys, re, json, html, io, time, argparse
import urllib.request, urllib.error

# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de fontes (key, short, name, sub, icon, url)
# `key` é o identificador gravado em cada chunk (chunk.s) — mantenha estável.
# ─────────────────────────────────────────────────────────────────────────────
SOURCES = [
    ("CF/88", "CF/88", "Constituição Federal de 1988",
     "Dispositivos sobre o imposto de renda (art. 153, III e §2º; art. 150; art. 195)",
     "📕", "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"),
    ("CTN", "CTN", "Código Tributário Nacional",
     "Lei nº 5.172/1966 (compilado) — arts. 43 a 45: imposto sobre a renda",
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
     "IRPJ e CSLL — apuração, JCP, isenção de lucros/dividendos", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l9249.htm"),
    ("Lei 9.316/96", "Lei 9.316", "Lei nº 9.316/1996",
     "Veda a dedução da CSLL na apuração do lucro real", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l9316.htm"),
    ("Lei 9.430/96", "Lei 9.430", "Lei nº 9.430/1996 (compilada)",
     "Legislação tributária federal — IRPJ/CSLL, preços de transferência", "📜",
     "https://www.planalto.gov.br/ccivil_03/leis/l9430compilada.htm"),
    ("Lei 12.973/14", "Lei 12.973", "Lei nº 12.973/2014",
     "Adequação da legislação tributária às normas contábeis (fim do RTT)", "📜",
     "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12973.htm"),
    ("Lei 15.079/24", "Lei 15.079", "Lei nº 15.079/2024",
     "Adicional da CSLL — tributação mínima global (Regras GloBE / Pilar 2)", "📜",
     "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/lei/l15079.htm"),
    ("LC 224", "LC 224", "Lei Complementar nº 224",
     "A confirmar na importação (lcp224)", "📘",
     "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp224.htm"),
    ("IN RFB 1.700/17", "IN 1.700", "Instrução Normativa RFB nº 1.700/2017",
     "Regulamenta a apuração do IRPJ e da CSLL", "📋",
     "https://www.normaslegais.com.br/legislacao/instrucao-normativa-rfb-1700-2017.htm"),
    ("LegisWeb 496991", "LegisWeb", "Norma a identificar (LegisWeb 496991)",
     "Confirmar a norma na importação", "🔖",
     "https://www.legisweb.com.br/legislacao/?id=496991"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Semente verificada — CTN arts. 43 a 45 (imposto sobre a renda).
# Texto conferido manualmente; serve de conteúdo real mesmo sem internet.
# ─────────────────────────────────────────────────────────────────────────────
CTN_CTX = ("LIVRO PRIMEIRO — Sistema Tributário Nacional",
           "TÍTULO III — Impostos",
           "CAPÍTULO III — Impostos sobre o Patrimônio e a Renda")
CTN_SEED = [
    ("Art. 43",
     "Art. 43. O imposto, de competência da União, sobre a renda e proventos de qualquer natureza tem como fato gerador a aquisição da disponibilidade econômica ou jurídica:\n"
     "I - de renda, assim entendido o produto do capital, do trabalho ou da combinação de ambos;\n"
     "II - de proventos de qualquer natureza, assim entendidos os acréscimos patrimoniais não compreendidos no inciso anterior.\n"
     "§ 1º A incidência do imposto independe da denominação da receita ou do rendimento, da localização, condição jurídica ou nacionalidade da fonte, da origem e da forma de percepção. (Incluído pela Lcp nº 104, de 2001)\n"
     "§ 2º Na hipótese de receita ou de rendimento oriundos do exterior, a lei estabelecerá as condições e o momento em que se dará sua disponibilidade, para fins de incidência do imposto referido neste artigo. (Incluído pela Lcp nº 104, de 2001)"),
    ("Art. 44",
     "Art. 44. A base de cálculo do imposto é o montante, real, arbitrado ou presumido, da renda ou dos proventos tributáveis."),
    ("Art. 45",
     "Art. 45. Contribuinte do imposto é o titular da disponibilidade a que se refere o artigo 43, sem prejuízo de atribuir a lei essa condição ao possuidor, a qualquer título, dos bens produtores de renda ou dos proventos tributáveis.\n"
     "Parágrafo único. A lei pode atribuir à fonte pagadora da renda ou dos proventos tributáveis a condição de responsável pelo imposto cuja retenção e recolhimento lhe caibam."),
]

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
    # keep body only
    m = re.search(r'<body[^>]*>(.*)</body>', doc, re.IGNORECASE | re.DOTALL)
    if m:
        doc = m.group(1)
    doc = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', doc, flags=re.IGNORECASE | re.DOTALL)
    doc = re.sub(r'<br\s*/?>', '\n', doc, flags=re.IGNORECASE)
    doc = re.sub(r'</p>|</div>|</tr>|</h[1-6]>', '\n', doc, flags=re.IGNORECASE)
    doc = re.sub(r'<[^>]+>', '', doc)
    doc = html.unescape(doc)
    doc = doc.replace('\xa0', ' ')
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
            # Seção/Subseção: kept inside the article body (fine-grained)
            continue
        a = ART_RE.match(ln)
        if a:
            flush()
            num = a.group(1)
            suf = (a.group(3) or "").upper()
            cur_art = "Art. " + num + (suf if suf.startswith("-") else "")
            cur_buf = [ln]
        elif cur_art:
            cur_buf.append(ln)
    flush()
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="não baixa nada")
    ap.add_argument("--only", default="", help="lista de keys separadas por vírgula")
    ap.add_argument("--out", default="data.js")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    chunks, structure = [], []
    for key, short, name, sub, icon, url in SOURCES:
        if only and key not in only:
            # keep as placeholder when filtering
            c, a = placeholder(key, name, sub, url)
            chunks += c; structure.append({"source": key, "articles": a}); continue

        if key == "CTN":
            # verified seed (kept even online — short and manually checked)
            for art, text in CTN_SEED:
                chunks.append({"s": key, "a": art, "t": text})
            seed_arts = [{"art": art, "livro": CTN_CTX[0], "titulo": CTN_CTX[1],
                          "capitulo": CTN_CTX[2], "preview": text[:110], "s": key}
                         for art, text in CTN_SEED]
            structure.append({"source": key, "articles": seed_arts})
            continue

        if args.offline:
            c, a = placeholder(key, name, sub, url)
            chunks += c; structure.append({"source": key, "articles": a}); continue

        try:
            print(f"↓ {key}: {url}", file=sys.stderr)
            lines = html_to_text(fetch(url))
            c, a = parse(lines, key)
            if not c:
                raise ValueError("nenhum artigo reconhecido")
            print(f"  ✓ {len(c)} artigos", file=sys.stderr)
            chunks += c; structure.append({"source": key, "articles": a})
            time.sleep(1)  # seja gentil com os servidores
        except Exception as e:
            print(f"  ✗ falhou ({e}) — usando placeholder", file=sys.stderr)
            c, a = placeholder(key, name, sub, url)
            chunks += c; structure.append({"source": key, "articles": a})

    data = {
        "meta": {"date": time.strftime("%Y-%m-%d"), "app": "IR Pro",
                 "note": "Catálogo das legislações de IR/CSLL para estudo. Confira "
                         "sempre o texto oficial vigente no Planalto/Receita Federal."},
        "sources": [{"key": k, "short": sh, "name": n, "sub": s, "icon": ic, "url": u}
                    for (k, sh, n, s, ic, u) in SOURCES],
        "chunks": chunks,
        "structure": structure,
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    out = ("// IR Pro — base de dados das legislações de IR/CSLL.\n"
           "// Gerado por build_data.py. Formato documentado no topo de build_data.py.\n"
           "window.IRPRO_DATA = " + body + ";\n")
    with io.open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\n✓ {args.out}: {len(chunks)} chunks, {len(structure)} fontes", file=sys.stderr)


if __name__ == "__main__":
    main()
