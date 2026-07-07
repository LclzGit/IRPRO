#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse Planalto/RFB legal text (extracted from PDF) into per-source JSON."""
import re, json, io, sys

HEADING_RE = re.compile(r'^(LIVRO|T[ÍI]TULO|CAP[ÍI]TULO|SUBSE[ÇC][ÃA]O|SE[ÇC][ÃA]O)\b'
                        r'\s*([IVXLCDM0-9]+[ºªA-Z\-]*)?\s*$', re.IGNORECASE)
# Início de artigo: exige "Art" com A MAIÚSCULO (as referências cruzadas usam
# "art." minúsculo, então ficam de fora), tolera a vírgula do OCR ("Art, 11"),
# ordinal opcional, e sufixo "-A" só com hífen colado (evita "Art 1º - O imposto").
ART_RE = re.compile(r'^Art[\.,]?\s*(\d+)(?:[ºªoa°])?(?:-([A-Z]))?(?=[\s\.\,\-º]|$)')

# Linhas de cabeçalho/rodapé do Planalto a ignorar
SKIP = re.compile(
    r'^(Presid[êe]ncia da Rep[úu]blica|Casa Civil|Subchefia|Secretaria Especial|'
    r'Texto compilado|Vig[êe]ncia|Produ[çc][ãa]o de efeitos|Mensagem de veto|'
    r'Regulamento|V[íi]de|Este texto n[ãa]o substitui|https?://|www\.|P[áa]gina \d+|'
    r'\d+/\d+/\d+,? \d+:\d+|\* ?$)', re.IGNORECASE)

def clean_lines(txt):
    out = []
    for ln in txt.split('\n'):
        ln = ln.replace('\xa0', ' ').rstrip()
        ln = re.sub(r'[ \t]+', ' ', ln).strip()
        if ln:
            out.append(ln)
    return out

def is_heading(ln):
    return HEADING_RE.match(ln) is not None

def parse(txt, default_ctx=("", "", ""), monotonic=True):
    # monotonic=True: só inicia novo artigo se o número/sufixo for estritamente
    #   maior (ótimo para leis normais; descarta artigos citados/repetidos).
    # monotonic=False: aceita todo marcador "Art. N" em ordem do documento — use
    #   para leis que REESCREVEM outras (ex.: Lei 12.973), onde os artigos
    #   inseridos em outras leis aparecem intercalados e não devem ser descartados.
    lines = clean_lines(txt)
    livro, titulo, capitulo = default_ctx
    arts = []
    cur = None            # dict being built
    maxkey = None         # maior (num, sufixo) já aceito
    last_num = 0          # número do último artigo aceito
    i = 0
    while i < len(lines):
        ln = lines[i]
        # structural heading (label alone, name often on next line)
        h = HEADING_RE.match(ln)
        if h:
            word = h.group(1).upper()
            name = ln
            nxt = lines[i+1] if i+1 < len(lines) else ""
            # merge the following line as the heading's name when it looks like one
            if nxt and not ART_RE.match(nxt) and not is_heading(nxt) and not SKIP.match(nxt) \
               and len(nxt) < 90 and not nxt.endswith(('.', ';', ':')):
                name = ln + " — " + nxt
                i += 1
            if word.startswith("LIVRO"):
                livro, titulo, capitulo = name, "", ""
            elif word.startswith(("TÍTULO", "TITULO")):
                titulo, capitulo = name, ""
            elif word.startswith(("CAPÍTULO", "CAPITULO")):
                capitulo = name
            else:  # SEÇÃO / SUBSEÇÃO -> keep inside capitulo level marker
                capitulo = (capitulo.split(" · ")[0] if capitulo else "")
                capitulo = name if not capitulo else capitulo  # prefer chapter; seções ficam no texto
            i += 1
            continue
        a = ART_RE.match(ln)
        # Só inicia um novo artigo se o número/sufixo for estritamente maior que
        # o máximo já visto e sem salto absurdo (>30). Isso descarta artigos
        # CITADOS de outras leis (comum em leis que "alteram" outras) e funde as
        # redações repetidas do mesmo artigo que a versão compilada exibe.
        is_new = False
        if a is not None:
            num = int(a.group(1)); suf = (a.group(2) or "").upper()
            key = (num, suf)
            if not monotonic:
                is_new = True
            elif maxkey is None or (key > maxkey and num <= last_num + 30):
                is_new = True
        if is_new:
            if cur:
                arts.append(cur)
            art = "Art. " + str(num) + ("-" + suf if suf else "")
            cur = {"art": art, "livro": livro, "titulo": titulo,
                   "capitulo": capitulo, "buf": [ln]}
            maxkey = key; last_num = num
        elif cur is not None:
            if SKIP.match(ln):
                i += 1; continue
            cur["buf"].append(ln)
        i += 1
    if cur:
        arts.append(cur)
    # finalize
    out = []
    for a in arts:
        text = reflow(a.pop("buf"))
        # drop trailing signature/date block glued to last article
        text = re.sub(r'\n(Bras[íi]lia,.*)$', '', text, flags=re.DOTALL).strip()
        a["text"] = text
        a["preview"] = text[:110]
        out.append(a)
    return out


# início de um novo bloco lógico (parágrafo, inciso, alínea, item)
NEWBLOCK = re.compile(
    r'^(§|Art\b|Par[áa]grafo\b|[IVXLCDM]{1,4}\s*[-–]\s|[a-z]\)\s|\d+\)\s|\d+\s*[-–]\s)')

def reflow(lines):
    out = []
    for ln in lines:
        if out and not NEWBLOCK.match(ln):
            out[-1] += " " + ln
        else:
            out.append(ln)
    return "\n".join(out)

def extract_text(path):
    """Texto de um .pdf (via PyMuPDF) ou de um .txt já extraído."""
    if path.lower().endswith(".txt"):
        return io.open(path, encoding="utf-8").read()
    import fitz  # PyMuPDF: pip install pymupdf
    doc = fitz.open(path)
    return "\n".join(p.get_text() for p in doc)


def slug(key):
    import re as _re
    return _re.sub(r'[^A-Za-z0-9]+', '_', key).strip('_')


if __name__ == "__main__":
    import argparse, os, json
    ap = argparse.ArgumentParser(
        description="Converte o PDF/TXT de uma norma em data/<fonte>.json para o IRCSPro.")
    ap.add_argument("arquivo", help="caminho do .pdf (oficial) ou .txt já extraído")
    ap.add_argument("--key", required=True,
                    help='chave da fonte, igual à do catálogo (ex.: "Lei 15.079/24")')
    ap.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    ap.add_argument("--dry-run", action="store_true", help="mostra estatísticas sem gravar")
    args = ap.parse_args()

    arts = parse(extract_text(args.arquivo))
    if not arts:
        sys.exit("Nenhum artigo reconhecido — verifique se o PDF tem camada de texto (não é imagem).")
    nums = [a["art"] for a in arts]
    print(f"{args.key}: {len(arts)} artigos | {nums[:3]} ... {nums[-3:]}")
    if args.dry_run:
        sys.exit(0)
    recs = [{"art": a["art"], "livro": a["livro"], "titulo": a["titulo"],
             "capitulo": a["capitulo"], "text": a["text"], "preview": a["preview"]}
            for a in arts]
    os.makedirs(args.out_dir, exist_ok=True)
    dest = os.path.join(args.out_dir, slug(args.key) + ".json")
    io.open(dest, "w", encoding="utf-8").write(json.dumps(recs, ensure_ascii=False, indent=1))
    print(f"✓ gravado {dest} ({os.path.getsize(dest)//1024} KB)")
    print("  Agora rode: python3 build_data.py --offline   (para regenerar data.js)")
