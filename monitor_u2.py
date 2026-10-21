import hashlib
import json
import os
import re
import requests
from bs4 import BeautifulSoup

# Configurações via Secrets do GitHub
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_IDS_RAW = os.environ.get("CHAT_IDS", "")
CHAT_IDS = [cid.strip() for cid in CHAT_IDS_RAW.split(",") if cid.strip()]

STATE_FILE = "u2_tour_state.json"

# Fontes monitoradas: Sites oficiais, notícias e portais de bilheteria
URLS_MONITORADAS = {
    "U2.com - Tours": "https://www.u2.com/pages/tours",
    "U2.com - News Geral": "https://www.u2.com/news",
    "U2Songs - Notícias e Rumores": "https://www.u2songs.com/news/",
    "Ticketmaster Brasil - Busca U2": "https://www.ticketmaster.com.br/event/u2",
    "Google News - U2 Brasil e Ingressos": "https://news.google.com/rss/search?q=U2+(shows+OR+ingressos+OR+Brasil+OR+MorumBIS+OR+precos)&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "Google News - U2 Argentina e River": "https://news.google.com/rss/search?q=U2+(Argentina+OR+entradas+OR+River+OR+Buenos+Aires)&hl=es-419&gl=AR&ceid=AR:es-419"
}

# Termos de alta prioridade (América do Sul / Brasil / Argentina / Março 2027)
TERMOS_PRIORITARIOS = [
    "brasil", "brazil", "são paulo", "sao paulo", "morumbi", "morumbis",
    "argentina", "buenos aires", "river plate", "allaccess", "ticketmaster",
    "10 de março", "12 de março", "23 de março", "25 de março",
    "10 de marzo", "12 de marzo", "23 de marzo", "25 de marzo",
    "march 10", "march 12", "march 23", "march 25"
]

# Termos ligados a preços e ingressos
TERMOS_INGRESSOS = [
    "ingresso", "ingressos", "entrada", "entradas", "ticket", "tickets",
    "preço", "preco", "preços", "valores", "valor", "precios", "prices",
    "lote", "meia-entrada", "inteira", "pista premium", "arquibancada",
    "pré-venda", "pre-venda", "preventa", "presale", "general sale", "venda geral",
    "esgotado", "sold out"
]

def carregar_estado():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_estado(estado):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

def enviar_telegram(mensagem):
    if not TELEGRAM_BOT_TOKEN or not CHAT_IDS:
        print("Erro: TELEGRAM_BOT_TOKEN ou CHAT_IDS não configurados.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        try:
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                print(f"Alerta enviado com sucesso para: {chat_id}")
            else:
                print(f"Falha ao enviar para {chat_id}: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Exceção no envio para {chat_id}: {e}")

def extrair_trechos_relevantes(texto):
    linhas = [l.strip() for l in texto.split("\n") if len(l.strip()) > 20]
    destaques = []
    
    for linha in linhas:
        linha_lower = linha.lower()
        tem_prioridade = any(t in linha_lower for t in TERMOS_PRIORITARIOS)
        tem_ingresso = any(t in linha_lower for t in TERMOS_INGRESSOS)
        
        if tem_prioridade or tem_ingresso:
            destaque_formatado = re.sub(r'\s+', ' ', linha)[:180]
            if destaque_formatado not in destaques:
                destaques.append(destaque_formatado)
        
        if len(destaques) >= 4:
            break
            
    return destaques

def obter_conteudo_pagina(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser" if not url.endswith((".rss", "=pt-419", "=es-419")) else "xml")
            
            for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
                tag.decompose()
                
            texto_completo = soup.get_text(separator="\n")
            return texto_completo
    except Exception as e:
        print(f"Erro ao acessar {url}: {e}")
    return None

def monitorar():
    estado_anterior = carregar_estado()
    novo_estado = dict(estado_anterior)
    alertas = []

    for nome_fonte, url in URLS_MONITORADAS.items():
        conteudo = obter_conteudo_pagina(url)
        if not conteudo:
            continue

        hash_atual = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
        hash_salvo = estado_anterior.get(nome_fonte)

        if hash_salvo is None:
            novo_estado[nome_fonte] = hash_atual
            print(f"[{nome_fonte}] Primeira leitura registrada.")
        elif hash_salvo != hash_atual:
            novo_estado[nome_fonte] = hash_atual
            
            conteudo_lower = conteudo.lower()
            relevancia_sa = any(t in conteudo_lower for t in TERMOS_PRIORITARIOS)
            relevancia_ingressos = any(t in conteudo_lower for t in TERMOS_INGRESSOS)
            
            trechos = extrair_trechos_relevantes(conteudo)
            alertas.append({
                "fonte": nome_fonte,
                "url": url,
                "alta_prioridade": relevancia_sa and relevancia_ingressos,
                "tem_brasil_argentina": relevancia_sa,
                "tem_ingressos": relevancia_ingressos,
                "trechos": trechos
            })

    if alertas:
        salvar_estado(novo_estado)
        for item in alertas:
            if item["alta_prioridade"]:
                cabecalho = "🔥🚨 <b>ALERTA MÁXIMO: INGRESSOS / SHOWS NO BRASIL OU ARGENTINA!</b>"
            elif item["tem_brasil_argentina"]:
                cabecalho = "🇧🇷🇦🇷 <b>ALERTA: NOTÍCIAS DE SHOWS NA AMÉRICA DO SUL (MARÇO/2027)</b>"
            elif item["tem_ingressos"]:
                cabecalho = "🎟️ <b>ALERTA DE INGRESSOS / VALORES DO U2!</b>"
            else:
                cabecalho = "📢 <b>ATUALIZAÇÃO GERAL: U2 TOUR</b>"

            texto_trechos = ""
            if item["trechos"]:
                texto_trechos = "\n\n<b>Destaques identificados:</b>\n" + "\n".join([f"• <i>{t}...</i>" for t in item["trechos"]])

            msg = (
                f"{cabecalho}\n\n"
                f"<b>Fonte:</b> {item['fonte']}\n"
                f"🔗 {item['url']}"
                f"{texto_trechos}\n\n"
                f"<i>Acesse o link para conferir lotes, datas e valores confirmados.</i>"
            )
            enviar_telegram(msg)
    else:
        if not estado_anterior and novo_estado:
            salvar_estado(novo_estado)
            print("Base inicial salva com sucesso.")
        print("Varredura concluída. Sem novidades no momento.")

if __name__ == "__main__":
    monitorar()
