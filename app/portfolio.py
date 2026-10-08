"""Curated public examples; unknown titles/credits are never promoted to facts."""
import json
from pathlib import Path
import re

PATH = Path(__file__).resolve().parents[1] / 'knowledge' / 'portfolio.json'


def read_portfolio():
    data = json.loads(PATH.read_text(encoding='utf-8'))
    seen = set()
    projects = []
    for item in data['projects']:
        identifier = item['id']
        if (not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier)
                or item['url'] != 'https://www.youtube.com/watch?v=' + identifier
                or item['source_url'] != 'https://www.youtube.com/@masterment/videos'):
            raise ValueError('Invalid curated portfolio identity')
        if identifier not in seen:
            projects.append(item)
            seen.add(identifier)
    return {**data, 'projects': projects}


def examples(text, knowledge, service=None):
    projects = knowledge.get('portfolio', {}).get('projects', [])
    terms = re.findall(r'[\w#]+', text.casefold())
    scored = [(sum(term in p['title'].casefold() for term in terms if len(term) > 2), p)
              for p in projects]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if service == 'music_video':
        scored = [pair for pair in scored if pair[1]['category'] == 'music_video']
    return [p for _, p in scored[:3]]


def portfolio_reply(history, lead, knowledge):
    text = history[-1]['content']
    # Contact domains such as example.com are not requests for portfolio examples.
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '', text)
    if not re.search(r'portfolio|portfólio|examples?|exemplos?|your work|trabalhos|worked with|collaborat|credits|créditos|\b(?:match|east.{0,3}west|connection|bala|memories)\b', text, re.I):
        return None
    from .language import language
    pt = language(history) == 'pt'
    if re.search(r'alexandra|hulio|\bmatch\b|east.{0,3}west|connection\s*#?\s*2', text, re.I):
        return ('Não tenho uma fonte verificada para confirmar os créditos desse projeto. Veja o canal oficial: '
                if pt else 'I do not have a verified source to confirm those project credits. You can check the official channel: ') + 'https://youtube.com/@masterment'
    if re.search(r'wedding|casamento|events?|eventos?|dance|dança|workshop|commercial|comercial|photograph|fotograf', text, re.I) or lead.get('service_id') in ('wedding', 'event', 'photography'):
        return ('Ainda não tenho um exemplo verificado dessa categoria no catálogo. Veja o portfólio do site: '
                if pt else 'I do not yet have a verified example for that category in the catalog. You can browse the website portfolio: ') + 'https://masterment.services/#work'
    selected = examples(text, knowledge, lead.get('service_id'))
    if not selected:
        return 'https://masterment.services/#work'
    intro = ('Aqui estão exemplos publicados no canal oficial da Masterment:\n'
             if pt else 'Here are examples published on Masterment’s official channel:\n')
    return intro + '\n'.join(p['title'] + ': ' + p['url'] for p in selected)
