import re

SOURCE='https://halykbank.kz/knowledge_base/3286'
GUIDES={
 'transfer': {'ru':'Перевод по номеру телефона','kk':'Телефон нөмірі бойынша аудару', 'steps':[
  ('Откройте приложение Halyk','Halyk қосымшасын ашыңыз','Войдите в своё приложение Halyk. На учебном экране выделена нижняя панель.','Halyk қосымшасына кіріңіз. Оқу экранында төменгі мәзір белгіленген.','Главная','Басты бет'),
  ('Перейдите в «Переводы»','«Аударымдар» бөліміне өтіңіз','В нижнем меню выберите «Переводы», затем перевод по номеру телефона.','Төменгі мәзірден «Аударымдар», содан кейін телефон нөмірі бойынша аударуды таңдаңыз.','Переводы','Аударымдар'),
  ('Выберите получателя','Алушыны таңдаңыз','Укажите номер получателя или выберите контакт. Проверьте имя получателя в приложении.','Алушының нөмірін енгізіңіз немесе контактіні таңдаңыз. Қосымшадағы алушының атын тексеріңіз.','Номер телефона','Телефон нөмірі'),
  ('Проверьте данные','Деректерді тексеріңіз','Укажите сумму и проверьте реквизиты и комиссию. Подтверждайте перевод только в своём приложении. Здесь деньги не переводятся.','Соманы енгізіп, деректемелер мен комиссияны тексеріңіз. Аударымды тек өз қосымшаңызда растаңыз. Мұнда ақша аударылмайды.','Проверить','Тексеру') ]},
 'navigation': {'ru':'Как пользоваться помощником','kk':'Көмекшіні қалай пайдалану керек','steps':[
  ('Включите микрофон','Микрофонды қосыңыз','Нажмите круглую кнопку микрофона и разрешите доступ в браузере.','Микрофон түймесін басып, браузерде рұқсат беріңіз.','Микрофон','Микрофон'),
  ('Задайте вопрос','Сұрақ қойыңыз','Говорите по-русски или по-казахски. В режиме «Авто» язык определяется по вашей речи.','Орысша немесе қазақша сөйлеңіз. «Авто» режимінде тіл сөзіңіз бойынша анықталады.','Авто · RU · KZ','Авто · RU · KZ'),
  ('Текст и история','Мәтін және тарих','Можно написать вопрос внизу. Ваши разговоры доступны на странице «История», где их можно удалить.','Төменде сұрақты жазуға болады. Сөйлесулеріңіз «Тарих» бетінде сақталады, оларды өшіруге болады.','История','Тарих') ]}
}

ENGLISH={
 'transfer':('Transfer by phone number',[
  ('Open the Halyk app','Sign in to your own Halyk app. This is an illustrative guide, not your live bank screen.','Home'),
  ('Choose Transfers','Open Transfers and select a transfer by phone number.','Transfers'),
  ('Choose the recipient','Enter the recipient’s phone number or select a contact. Check their name in your app.','Phone number'),
  ('Review the details','Enter the amount. Check the recipient and any fee. Only confirm in your own banking app; this assistant cannot transfer money.','Review')]),
 'navigation':('Using your assistant',[
  ('Enable your microphone','Press the microphone button in the message bar and allow microphone access.','Microphone'),
  ('Ask a question','Speak Russian, Kazakh or English. Auto mode detects your spoken language.','Auto · RU · KZ · EN'),
  ('Text and history','You can type a question below. Your conversations are saved in History, where you can delete them.','History')])}

def language(text,previous='ru'):
    if re.search(r'\b(yes|no|where|how|hello|hi|thanks|next|back|show|close|stop)\b',text.lower()):return 'other'
    if re.search('[әғқңөұүһі]',text.lower()) or re.search(r'\b(сәлем|рахмет|иә|жоқ|калай|кайда|аудару)\b',text.lower()):return 'kk'
    if re.search(r'\b(да|нет|где|как|привет|покажи|дальше|назад|спасибо)\b',text.lower()):return 'ru'
    return previous if previous in {'ru','kk','other'} else 'ru'

def view(state):
    key=state.tutorial_active
    if not key:return None
    if state.language=='other':
        title,steps=ENGLISH[key]
        return {'id':key,'title':title,'language':'en','index':state.tutorial_step,'source':SOURCE if key=='transfer' else None,
          'steps':[{'title':s[0],'text':s[1],'target':s[2]} for s in steps]}
    lang=state.language; k=1 if lang=='kk' else 0; g=GUIDES[key]
    return {'id':key,'title':g[lang],'language':lang,'index':state.tutorial_step,'source':SOURCE if key=='transfer' else None,
      'steps':[{'title':s[k],'text':s[2+k],'target':s[4+k]} for s in g['steps']]}

def handle(text,state):
    low=text.lower().strip(' .!?');state.language=language(text,state.language);kk=state.language=='kk';en=state.language=='other'
    yes=bool(re.fullmatch(r'(да|давай|покажи|покажите|да покажи|да помоги|хорошо|иә|ия|көрсет|жарайды|yes)',low))
    no=low in {'нет','не надо','жоқ','no','закрыть','стоп','тоқта','close','stop'}
    if state.tutorial_active:
        if no:
            state.tutorial_active=None
            return 'Guide closed. How else can I help?' if en else 'Нұсқаулық жабылды.' if kk else 'Закрыла подсказки. Чем ещё помочь?'
        if low in {'дальше','далее','следующий','келесі','назад','артқа','next','back'}:
            delta=-1 if low in {'назад','артқа','back'} else 1
            state.tutorial_step=max(0,min(len(GUIDES[state.tutorial_active]['steps'])-1,state.tutorial_step+delta))
            return view(state)['steps'][state.tutorial_step]['text']
    if state.tutorial_pending and (yes or no):
        key=state.tutorial_pending;state.tutorial_pending=None
        if no:return 'No problem. I’m here if you need me.' if en else 'Жақсы. Басқа сұрағыңыз бар ма?' if kk else 'Хорошо. Если понадобится, я рядом.'
        state.tutorial_active=key;state.tutorial_step=0
        return view(state)['steps'][0]['text']
    help_intent=re.search(r'где|куда|как (найти|открыть|сделать|перевести|пользоваться)|не (могу|наш[её]л|понимаю)|нажать|покажи|қайда|қалай|таба алма|көрсет|where|how do|show me|cannot find|can.t find',low)
    if help_intent:
        key='transfer' if re.search(r'перев|аудар|получател|transfer',low) else 'navigation'
        state.tutorial_pending=key;state.tutorial_active=None
        return 'Would you like me to show you where to tap, step by step?' if en else 'Қай жерді басу керегін қадамдап көрсетейін бе?' if kk else 'Давайте помогу разобраться. Показать на экране, куда нажимать, шаг за шагом?'
    if low in {'привет','здравствуйте','сәлем','сәлеметсіз бе','hello','hi'}:
        return 'Hello! I’m your AI assistant. How can I help?' if en else 'Сәлем! Мен сіздің AI көмекшіңізбін. Қандай сұрағыңыз бар?' if kk else 'Здравствуйте! Я ваш AI-помощник. Расскажите, с чем помочь?'
    if low in {'спасибо','рахмет','thanks','thank you'}:return 'Happy to help!' if en else 'Көмектесуге дайынмын!' if kk else 'Рада помочь! Обращайтесь, если появятся вопросы.'
    state.tutorial_pending=None
    return None
