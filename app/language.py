"""Small Portuguese intake/fallback layer; the model handles richer language."""
import re

TRANSLATIONS = {
    'What are your main content goals?': 'Quais são os seus principais objetivos para o conteúdo?',
    'How many Reels would you like each month?': 'Quantos Reels gostaria de produzir por mês?',
    'How many hours of coverage would you like?': 'Quantas horas de cobertura pretende?',
    'Would you like photography, video, or both?': 'Pretende fotografia, vídeo ou ambos?',
    'What type and approximate size of property is it?': 'Qual é o tipo e tamanho aproximado do imóvel?',
    'Do you need property photos, video, or both?': 'Precisa de fotografias do imóvel, vídeo ou ambos?',
    'How many listings need coverage?': 'Quantos imóveis precisam de cobertura?',
    'Do you already have a website? If so, what is its URL?': 'Qual é o endereço do seu site atual, caso já tenha um?',
    'What pages and features does the website need?': 'Que páginas e funcionalidades precisa no site?',
    'What is your existing website URL, or do you need a new site?': 'Qual é o endereço do seu site atual, ou precisa de um site novo?',
    'What should the bot help customers do: answer FAQs, collect leads, or support another workflow?': 'O bot deve responder a perguntas, recolher contactos ou ajudar noutra tarefa?',
    'Which city or island is the production in?': 'Em que cidade ou ilha será a produção?',
    'What type of production do you need?': 'Que tipo de produção precisa?',
    'What music genre or style are you working in?': 'Qual é o género musical ou estilo do projeto?',
    'How many songs need work?': 'Quantas músicas precisam de trabalho?',
    'What dance style or type of talent do you need?': 'Que estilo de dança ou tipo de talento precisa?',
    'How many dancers or performers do you need?': 'Quantos bailarinos ou artistas precisa?',
    'What kind of look, feel, or story do you have in mind for the project?': 'Que estilo visual ou história tem em mente para o projeto?',
    'Do you have a date or timeframe in mind for the project?': 'Tem uma data ou prazo em mente para o projeto?',
    'Where would you like the project to take place?': 'Em que cidade ou local gostaria de realizar o projeto?',
    'What budget would you like the team to work within?': 'Qual é o orçamento estimado para o projeto?',
    'What is the best way for the team to reach you - phone or email?': 'Qual é o melhor telefone ou email para a equipa entrar em contacto?',
    'What name should I include with the project brief?': 'Que nome devo incluir nos detalhes do projeto?',
    'The Masterment team can review the details you shared. You can add anything else whenever you are ready; no booking or availability is confirmed here.': 'A equipa da Masterment pode analisar os detalhes que partilhou. Pode acrescentar mais informações quando quiser; nenhuma reserva ou disponibilidade está confirmada.',
}


def language(history):
    for turn in reversed(history):
        if turn.get('role') != 'user':
            continue
        text = turn['content']
        if re.search(r'\b(?:in english|speak english|respond in english)\b', text, re.I):
            return 'en'
        if re.search(r'\b(?:quero|preciso|olá|obrigad[oa]|fotografia|português|orçamento|escuro|casamento|vídeo|nome é|meu nome|meu site|exemplos|preço|estilo|cidade)\b', text, re.I):
            return 'pt'
    return 'en'


def intake_text(text):
    # Preserve place/name/contact strings; normalize only explicit intake phrases.
    for source, target in [
        (r'\bmeu nome é\b', 'my name is'), (r'\bo meu nome é\b', 'my name is'),
        (r'\bvídeos? musica(?:l|is)\b|\bvideoclipes?\b', 'music video'),
        (r'\bfotografia\b', 'photography'), (r'\bcasamento\b', 'wedding'),
        (r'\bsite\b', 'website'), (r'\bvídeo promocional\b', 'promo video'),
        (r'\bquero\b|\bpreciso de\b', 'I want'), (r'\borçamento\b', 'budget'),
        (r'\bdata\b|\bprazo\b', 'date'), (r'\bestilo visual\b|\bestilo\b', 'visual style'),
        (r'\bcidade\b|\blocal\b', 'location'), (r'\bem\b', 'in'),
        (r'\boutubro\b', 'October'), (r'\bnovembro\b', 'November'),
        (r'\bdezembro\b', 'December'), (r'\bjaneiro\b', 'January'),
        (r'\bfevereiro\b', 'February'), (r'\bmarço\b', 'March'),
        (r'\babril\b', 'April'), (r'\bmaio\b', 'May'), (r'\bjunho\b', 'June'),
        (r'\bjulho\b', 'July'), (r'\bagosto\b', 'August'), (r'\bsetembro\b', 'September'),
        (r'\bqual é o melhor telefone ou email\b', 'what is your phone or email'),
        (r'\bque nome\b', 'what name'),
    ]:
        text = re.sub(source, target, text, flags=re.I)
    # Portuguese day-month notation, preserving the customer's intended date.
    text = re.sub(r'\b(\d{1,2})\s+de\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+de\s+(\d{4}))?',
                  lambda m: m[2] + ' ' + m[1] + (', ' + m[3] if m[3] else ''), text, flags=re.I)
    return text


def localize_question(question):
    return TRANSLATIONS.get(question, 'Pode partilhar mais detalhes sobre o projeto?')
